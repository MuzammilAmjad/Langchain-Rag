from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.documents import Document as LCDocument
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import Document, Message, get_session, init_db
from rag import (
    RagError,
    MAX_SOURCE_CHUNKS,
    RETRIEVER_TOP_K,
    build_answer_chain,
    build_condense_question_prompt,
    build_retriever,
    file_signature,
    format_sources,
    get_llm,
    get_pinecone_index,
    get_vectorstore,
    safe_namespace,
    save_uploaded_pdf,
    unique_documents,
)

load_dotenv()
init_db()

UPLOAD_DIR = Path("uploads")

app = FastAPI(title="Book Assistant RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # add your deployed frontend origin too
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tracks which namespaces have been indexed this process, purely so upload
# responses can report fresh counts immediately. Retrieval itself talks to
# Pinecone directly per namespace (see _retrieve_across_documents) — no
# retriever object needs to be cached.


class _UploadAdapter:
    """Wraps a FastAPI UploadFile so it satisfies the .name/.getbuffer()
    interface that save_uploaded_pdf() (written for Streamlit's
    UploadedFile) expects, without touching rag/retriever.py."""

    def __init__(self, filename: str, content: bytes):
        self.name = filename
        self._content = content

    def getbuffer(self) -> bytes:
        return self._content


class ChatRequest(BaseModel):
    question: str


class DocumentOut(BaseModel):
    namespace: str
    pdf_name: str
    source_count: int
    page_count: Optional[int]
    active: bool

    class Config:
        from_attributes = True


# --- Document library -------------------------------------------------


@app.get("/api/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_session)):
    return db.query(Document).order_by(Document.uploaded_at.desc()).all()


@app.post("/api/documents/upload", response_model=DocumentOut)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_session)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    content = await file.read()
    adapter = _UploadAdapter(file.filename, content)

    try:
        pdf_path = save_uploaded_pdf(UPLOAD_DIR, adapter)
        signature = file_signature(pdf_path)
        namespace = safe_namespace(file.filename, content_signature=signature)
        artifacts = build_retriever(pdf_path, namespace)
    except RagError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        # The PDF only needed to exist long enough to chunk + index it —
        # the vectors are what persists (in Pinecone), so don't rely on
        # this file surviving a redeploy.
        try:
            pdf_path.unlink(missing_ok=True)
        except Exception:
            pass

    doc = db.get(Document, namespace)
    if doc is None:
        doc = Document(
            namespace=namespace,
            pdf_name=file.filename,
            content_signature=signature,
            source_count=artifacts.source_count,
            page_count=artifacts.page_count,
            active=True,
        )
        db.add(doc)
    else:
        doc.source_count = artifacts.source_count
        doc.page_count = artifacts.page_count
    db.commit()
    db.refresh(doc)
    return doc


class DocumentPatch(BaseModel):
    active: bool


@app.patch("/api/documents/{namespace}", response_model=DocumentOut)
def set_document_active(namespace: str, patch: DocumentPatch, db: Session = Depends(get_session)):
    doc = db.get(Document, namespace)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    doc.active = patch.active
    db.commit()
    db.refresh(doc)
    return doc


@app.delete("/api/documents/{namespace}")
def delete_document(namespace: str, purge_vectors: bool = True, db: Session = Depends(get_session)):
    doc = db.get(Document, namespace)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    if purge_vectors:
        try:
            get_pinecone_index().delete(delete_all=True, namespace=namespace)
        except Exception:
            pass  # namespace may already be empty/gone — non-fatal

    db.delete(doc)
    db.commit()
    return {"deleted": namespace}


# --- Chat history -------------------------------------------------------


@app.get("/api/chat/history")
def get_chat_history(db: Session = Depends(get_session)):
    messages = db.query(Message).order_by(Message.created_at.asc()).all()
    return [
        {"role": m.role, "content": m.content, "sources": m.sources, "created_at": m.created_at.isoformat()}
        for m in messages
    ]


@app.delete("/api/chat/history")
def clear_chat_history(db: Session = Depends(get_session)):
    db.query(Message).delete()
    db.commit()
    return {"cleared": True}


# --- Chat (multi-namespace retrieval) ------------------------------------


def _condense_question(question: str, chat_history: str) -> str:
    if not chat_history.strip():
        return question
    chain = build_condense_question_prompt() | get_llm() | StrOutputParser()
    try:
        return chain.invoke({"question": question, "chat_history": chat_history}).strip()
    except Exception:
        return question


def _retrieve_across_documents(query: str, namespaces: list[str]) -> list[LCDocument]:
    """Runs similarity search against each active document's Pinecone
    namespace separately (namespaces can't be queried together in one
    call), tags each hit with which document it came from, then merges
    and ranks everything together by similarity score."""
    scored: list[tuple[LCDocument, float]] = []

    for namespace in namespaces:
        try:
            vectorstore = get_vectorstore(namespace)
            hits = vectorstore.similarity_search_with_score(query, k=RETRIEVER_TOP_K)
        except Exception:
            continue
        for doc, score in hits:
            doc.metadata = {**(doc.metadata or {}), "namespace": namespace}
            scored.append((doc, score))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [doc for doc, _ in scored[:MAX_SOURCE_CHUNKS]]


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _stream_answer(question: str, history_text: str, active_namespaces: list[str], db: Session):
    if not active_namespaces:
        yield _sse({"type": "error", "message": "No active documents to search. Upload or activate at least one."})
        return

    try:
        retrieval_query = _condense_question(question, history_text)
        documents = _retrieve_across_documents(retrieval_query, active_namespaces)
    except Exception as exc:
        yield _sse({"type": "error", "message": f"Retrieval failed: {exc}"})
        return

    deduped_docs = unique_documents(documents)
    context = format_sources(deduped_docs)
    chain = build_answer_chain()

    full_answer = ""
    try:
        async for chunk in chain.astream(
            {"question": question, "chat_history": history_text, "context": context}
        ):
            if chunk:
                full_answer += chunk
                yield _sse({"type": "token", "content": chunk})
    except Exception as exc:
        yield _sse({"type": "error", "message": f"Answer generation failed: {exc}"})
        return

    doc_names = {d.namespace: d.pdf_name for d in db.query(Document).all()}
    sources = [
        {
            "id": index,
            "source": doc_names.get((doc.metadata or {}).get("namespace"), (doc.metadata or {}).get("source", "PDF")),
            "page": (doc.metadata or {}).get("page_number", (doc.metadata or {}).get("page", "?")),
            "excerpt": doc.page_content[:300],
        }
        for index, doc in enumerate(deduped_docs, start=1)
    ]
    yield _sse({"type": "sources", "sources": sources})
    yield _sse({"type": "done"})

    db.add(Message(role="user", content=question))
    db.add(Message(role="assistant", content=full_answer, sources=sources))
    db.commit()


@app.post("/api/chat")
async def chat(request: ChatRequest, db: Session = Depends(get_session)):
    active_docs = db.query(Document).filter(Document.active.is_(True)).all()
    active_namespaces = [d.namespace for d in active_docs]

    history_rows = db.query(Message).order_by(Message.created_at.asc()).all()
    history_text = "\n".join(f"{m.role.title()}: {m.content}" for m in history_rows)

    return StreamingResponse(
        _stream_answer(request.question, history_text, active_namespaces, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )