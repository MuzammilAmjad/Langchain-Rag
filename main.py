from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel

from rag import (
    RagArtifacts,
    RagError,
    MAX_SOURCE_CHUNKS,
    build_answer_chain,
    build_condense_question_prompt,
    build_query_artifacts,
    build_retriever,
    file_signature,
    format_sources,
    get_llm,
    load_knowledge_base_manifest,
    safe_namespace,
    save_knowledge_base_manifest,
    save_uploaded_pdf,
    unique_documents,
)

load_dotenv()

UPLOAD_DIR = Path("uploads")
MANIFEST_PATH = UPLOAD_DIR / "active_knowledge_base.json"

app = FastAPI(title="Book Assistant RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # add your deployed frontend origin too
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- In-memory app state (single active knowledge base, mirrors the old
# st.session_state usage in app.py) ---
class _State:
    artifacts: Optional[RagArtifacts] = None
    pdf_name: Optional[str] = None
    namespace: Optional[str] = None


state = _State()


class _UploadAdapter:
    """Wraps a FastAPI UploadFile so it satisfies the .name/.getbuffer()
    interface that save_uploaded_pdf() (written for Streamlit's
    UploadedFile) expects, without touching rag/retriever.py."""

    def __init__(self, filename: str, content: bytes):
        self.name = filename
        self._content = content

    def getbuffer(self) -> bytes:
        return self._content


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[ChatMessage] = []


def _hydrate_from_manifest() -> None:
    if state.artifacts is not None:
        return
    manifest = load_knowledge_base_manifest(MANIFEST_PATH)
    if not manifest or not manifest.get("namespace"):
        return
    try:
        artifacts = build_query_artifacts(manifest["namespace"])
    except RagError:
        return
    state.artifacts = artifacts
    state.pdf_name = manifest.get("pdf_name") or Path(manifest["pdf_path"]).name
    state.namespace = manifest["namespace"]


@app.on_event("startup")
def on_startup() -> None:
    _hydrate_from_manifest()


@app.get("/api/knowledge-base")
def get_knowledge_base():
    _hydrate_from_manifest()
    if state.artifacts is None:
        return {"active": False}
    return {
        "active": True,
        "pdf_name": state.pdf_name,
        "namespace": state.namespace,
        "source_count": state.artifacts.source_count,
        "page_count": state.artifacts.page_count,
    }


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    content = await file.read()
    adapter = _UploadAdapter(file.filename, content)

    try:
        pdf_path = save_uploaded_pdf(UPLOAD_DIR, adapter)
        signature = file_signature(pdf_path)
        namespace = safe_namespace(file.filename, content_signature=signature)
        artifacts = build_retriever(pdf_path, namespace)
        save_knowledge_base_manifest(MANIFEST_PATH, pdf_path, namespace)
    except RagError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    state.artifacts = artifacts
    state.pdf_name = file.filename
    state.namespace = namespace

    return {
        "active": True,
        "pdf_name": state.pdf_name,
        "namespace": state.namespace,
        "source_count": artifacts.source_count,
        "page_count": artifacts.page_count,
    }


def _condense_question(question: str, chat_history: str) -> str:
    if not chat_history.strip():
        return question
    chain = build_condense_question_prompt() | get_llm() | StrOutputParser()
    try:
        return chain.invoke({"question": question, "chat_history": chat_history}).strip()
    except Exception:
        return question


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _stream_answer(question: str, history_text: str):
    if state.artifacts is None:
        yield _sse({"type": "error", "message": "No knowledge base is indexed yet."})
        return

    try:
        retrieval_query = _condense_question(question, history_text)
        documents = state.artifacts.retriever.invoke(retrieval_query)
    except Exception as exc:
        yield _sse({"type": "error", "message": f"Retrieval failed: {exc}"})
        return

    deduped_docs = unique_documents(documents)
    # cited_docs must match exactly what format_sources numbered [1], [2], ...
    # so the model's inline [n] brackets line up with the sources sent to the UI.
    cited_docs = deduped_docs[:MAX_SOURCE_CHUNKS]
    context = format_sources(deduped_docs)
    chain = build_answer_chain()

    try:
        async for chunk in chain.astream(
            {"question": question, "chat_history": history_text, "context": context}
        ):
            if chunk:
                yield _sse({"type": "token", "content": chunk})
    except Exception as exc:
        yield _sse({"type": "error", "message": f"Answer generation failed: {exc}"})
        return

    sources = [
        {
            "id": index,
            "source": (doc.metadata or {}).get("source", (doc.metadata or {}).get("file_path", "PDF")),
            "page": (doc.metadata or {}).get("page_number", (doc.metadata or {}).get("page", "?")),
            "excerpt": doc.page_content[:300],
        }
        for index, doc in enumerate(cited_docs, start=1)
    ]
    yield _sse({"type": "sources", "sources": sources})
    yield _sse({"type": "done"})


@app.post("/api/chat")
async def chat(request: ChatRequest):
    if state.artifacts is None:
        raise HTTPException(status_code=409, detail="No knowledge base is indexed yet.")

    history_text = "\n".join(f"{m.role.title()}: {m.content}" for m in request.history)

    return StreamingResponse(
        _stream_answer(request.question, history_text),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )