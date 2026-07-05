from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from dotenv import load_dotenv
import streamlit as st
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from langchain_text_splitters import TokenTextSplitter
from pinecone import Pinecone, ServerlessSpec
from pinecone.exceptions import PineconeException

load_dotenv()
logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
LLM_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
CHUNK_TOKENS = int(os.getenv("CHUNK_TOKENS", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))
MAX_SOURCE_CHUNKS = int(os.getenv("MAX_SOURCE_CHUNKS", "5"))
EMBEDDING_DIMENSION = int(os.getenv("OPENAI_EMBEDDING_DIMENSION", "1536"))
RETRIEVER_TOP_K = int(os.getenv("RETRIEVER_TOP_K", "4"))


class RagError(RuntimeError):
    """Raised for any recoverable failure in the RAG pipeline, safe to show to the user."""


@dataclass(slots=True)
class RagArtifacts:
    retriever: MultiQueryRetriever
    namespace: str
    source_count: int
    page_count: int


# --------------------------------------------------------------------------
# Namespacing / file handling
# --------------------------------------------------------------------------

def safe_namespace(
    uploaded_name: str,
    scope_id: Optional[str] = None,
    content_signature: Optional[str] = None,
) -> str:
    """Build a Pinecone namespace for an uploaded file.

    `scope_id` (e.g. a user id or Streamlit session id) is folded into the
    hash so two different users uploading a file with the same filename do
    not collide and overwrite each other's vectors. If you are running this
    as a single-user tool you can safely omit scope_id.
    """
    name = Path(uploaded_name).stem.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", name).strip("-") or "book-assistant"
    key_parts = [uploaded_name]
    if scope_id:
        key_parts.insert(0, scope_id)
    if content_signature:
        key_parts.append(content_signature)
    key = ":".join(key_parts)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]
    return f"{cleaned}-{digest}"


def file_signature(file_path: Path) -> str:
    hasher = hashlib.sha1()
    try:
        with file_path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                hasher.update(chunk)
    except OSError as exc:
        raise RagError(f"Could not read uploaded file for hashing: {exc}") from exc
    return hasher.hexdigest()


def ensure_upload_path(upload_dir: Path, uploaded_name: str) -> Path:
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir / Path(uploaded_name).name


def save_uploaded_pdf(upload_dir: Path, uploaded_file) -> Path:
    destination = ensure_upload_path(upload_dir, uploaded_file.name)
    try:
        with destination.open("wb") as target:
            target.write(uploaded_file.getbuffer())
    except OSError as exc:
        raise RagError(f"Could not save uploaded file: {exc}") from exc
    return destination


def save_knowledge_base_manifest(manifest_path: Path, pdf_path: Path, namespace: str) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pdf_path": str(pdf_path),
        "pdf_name": pdf_path.name,
        "namespace": namespace,
        "content_signature": file_signature(pdf_path),
    }
    try:
        manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        raise RagError(f"Could not save knowledge base manifest: {exc}") from exc


def load_knowledge_base_manifest(manifest_path: Path) -> dict[str, str] | None:
    if not manifest_path.exists():
        return None
    try:
        raw_text = manifest_path.read_text(encoding="utf-8").strip()
        if not raw_text:
            return None
        payload = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as exc:
        raise RagError(f"Could not read knowledge base manifest: {exc}") from exc
    if not isinstance(payload, dict):
        raise RagError("Knowledge base manifest is malformed.")
    return {
        "pdf_path": str(payload.get("pdf_path", "")),
        "pdf_name": str(payload.get("pdf_name", "")),
        "namespace": str(payload.get("namespace", "")),
        "content_signature": str(payload.get("content_signature", "")),
    }


# --------------------------------------------------------------------------
# Cached clients
# --------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def get_embeddings() -> OpenAIEmbeddings:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RagError("OPENAI_API_KEY is missing.")
    return OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=api_key,
        dimensions=EMBEDDING_DIMENSION,
    )


@st.cache_resource(show_spinner=False)
def get_llm() -> ChatOpenAI:
    """Single cached LLM client, reused for MultiQuery rephrasing and answer generation."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RagError("OPENAI_API_KEY is missing.")
    return ChatOpenAI(
        model=LLM_MODEL,
        openai_api_key=api_key,
        temperature=0.2,
    )


@st.cache_resource(show_spinner=False)
def get_pinecone_index():
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise RagError("PINECONE_API_KEY is missing.")

    index_name = os.getenv("PINECONE_INDEX_NAME", "book-assistant-index")
    cloud = os.getenv("PINECONE_CLOUD", "aws")
    region = os.getenv("PINECONE_REGION", "us-east-1")

    try:
        client = Pinecone(api_key=api_key)
        existing_names = client.list_indexes().names()
        if index_name not in existing_names:
            client.create_index(
                name=index_name,
                dimension=EMBEDDING_DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(cloud=cloud, region=region),
            )
        return client.Index(index_name)
    except PineconeException as exc:
        raise RagError(f"Could not initialize Pinecone index: {exc}") from exc


def namespace_has_vectors(index, namespace: str) -> bool:
    stats = index.describe_index_stats()
    namespaces = stats.get("namespaces", {}) or {}
    namespace_stats = namespaces.get(namespace)
    if not namespace_stats:
        return False
    return namespace_stats.get("vector_count", 0) > 0


def get_vectorstore(namespace: str) -> PineconeVectorStore:
    return PineconeVectorStore(
        index=get_pinecone_index(),
        embedding=get_embeddings(),
        namespace=namespace,
    )


# --------------------------------------------------------------------------
# Loading / splitting
# --------------------------------------------------------------------------

def load_pdf_documents(pdf_path: Path) -> list[Document]:
    try:
        loader = PyPDFLoader(str(pdf_path))
        return loader.load()
    except Exception as exc:  # PyPDFLoader raises varied low-level errors
        raise RagError(f"Could not read PDF '{pdf_path.name}': {exc}") from exc


def split_documents(documents: list[Document]) -> list[Document]:
    """Split raw pages into simple token-based chunks."""
    splitter = TokenTextSplitter(
        chunk_size=CHUNK_TOKENS,
        chunk_overlap=CHUNK_OVERLAP,
    )
    return splitter.split_documents(documents)


# --------------------------------------------------------------------------
# Retriever construction
# --------------------------------------------------------------------------

def build_retriever(pdf_path: Path, namespace: str, force_rebuild: bool = False) -> RagArtifacts:
    """Build (or reuse) the retriever for a given namespace.

    Set `force_rebuild=False` and check `st.session_state` at the call site
    to avoid re-embedding the same PDF on every Streamlit rerun -- this
    function always does a full delete+rebuild when called, by design, so
    the caller is responsible for only calling it once per new upload.
    """
    raw_documents = load_pdf_documents(pdf_path)
    chunks = split_documents(raw_documents)

    vectorstore = get_vectorstore(namespace=namespace)
    index = get_pinecone_index()

    if not force_rebuild and namespace_has_vectors(index, namespace):
        raw_documents = load_pdf_documents(pdf_path)
        chunks = split_documents(raw_documents)
        multi_query_retriever = MultiQueryRetriever.from_llm(
            retriever=vectorstore.as_retriever(search_kwargs={"k": RETRIEVER_TOP_K}),
            llm=get_llm(),
            include_original=True,
        )
        return RagArtifacts(
            retriever=multi_query_retriever,
            namespace=namespace,
            source_count=len(chunks),
            page_count=len(raw_documents),
        )

    try:
        if force_rebuild and namespace_has_vectors(index, namespace):
            index.delete(delete_all=True, namespace=namespace)
    except PineconeException as exc:
        raise RagError(f"Could not clear existing vectors: {exc}") from exc

    try:
        vectorstore.add_documents(chunks)
    except Exception as exc:
        raise RagError(f"Could not index document into Pinecone: {exc}") from exc

    multi_query_retriever = MultiQueryRetriever.from_llm(
        retriever=vectorstore.as_retriever(search_kwargs={"k": RETRIEVER_TOP_K}),
        llm=get_llm(),
        include_original=True,
    )

    return RagArtifacts(
        retriever=multi_query_retriever,
        namespace=namespace,
        source_count=len(chunks),
        page_count=len(raw_documents),
    )


def get_or_build_retriever(pdf_path: Path, namespace: str) -> RagArtifacts:
    """Streamlit-friendly entry point: skips rebuilding if this namespace
    was already indexed earlier in the session."""
    indexed = st.session_state.setdefault("indexed_namespaces", {})
    if namespace in indexed:
        return indexed[namespace]

    artifacts = build_retriever(pdf_path, namespace)
    indexed[namespace] = artifacts
    return artifacts


# --------------------------------------------------------------------------
# Source formatting
# --------------------------------------------------------------------------

def unique_documents(documents: Iterable[Document]) -> list[Document]:
    seen: set[tuple[str, str]] = set()
    ordered_docs: list[Document] = []
    for document in documents:
        metadata = document.metadata or {}
        source = str(metadata.get("source", metadata.get("file_path", "uploaded-pdf")))
        page = str(metadata.get("page_number", metadata.get("page", "")))
        key = (source, page + document.page_content[:160])
        if key in seen:
            continue
        seen.add(key)
        ordered_docs.append(document)
    return ordered_docs


def format_sources(documents: Iterable[Document], max_sources: int = MAX_SOURCE_CHUNKS) -> str:
    docs = unique_documents(documents)
    excerpts: list[str] = []
    for index, document in enumerate(docs[:max_sources], start=1):
        metadata = document.metadata or {}
        page = metadata.get("page_number", metadata.get("page", "?"))
        source = metadata.get("source", metadata.get("file_path", "uploaded pdf"))
        text = document.page_content.strip().replace("\n", " ")
        excerpts.append(f"[{index}] Source: {source} | Page: {page}\n{text[:1200]}")
    return "\n\n".join(excerpts)


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------

def build_teacher_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        """You are an AI Teacher helping a student understand a document.

Answer only from the provided context. If the context does not contain
enough information to answer confidently, say so explicitly instead of
guessing -- do not use outside knowledge.

Chat history:
{chat_history}

Context:
{context}

Question:
{question}

Answer:
"""
    )


def build_answer_chain():
    """Small LCEL answer chain used after retrieval has produced context."""
    return build_teacher_prompt() | get_llm() | StrOutputParser()


def build_condense_question_prompt() -> ChatPromptTemplate:
    """Used to rewrite a follow-up question into a standalone question,
    so retrieval quality doesn't degrade on multi-turn conversations."""
    return ChatPromptTemplate.from_template(
        """Given the chat history and a follow-up question, rewrite the
follow-up question to be a standalone question that captures all
necessary context from the history. If the follow-up question is
already standalone, return it unchanged. Return only the rewritten
question, nothing else.

Chat history:
{chat_history}

Follow-up question:
{question}

Standalone question:
"""
    )


def make_context_tool(retriever: MultiQueryRetriever):
    """Wrap retrieval in a LangChain tool so the same logic can be reused in agents."""

    @tool("book_context_search")
    def book_context_search(question: str) -> str:
        """Return the most relevant passages for a book question."""
        documents = unique_documents(retriever.invoke(question))
        return format_sources(documents)

    return book_context_search


# --------------------------------------------------------------------------
# Answering
# --------------------------------------------------------------------------

def _condense_question(question: str, chat_history: str) -> str:
    if not chat_history.strip():
        return question
    llm = get_llm()
    chain = build_condense_question_prompt() | llm | StrOutputParser()
    try:
        return chain.invoke({"question": question, "chat_history": chat_history}).strip()
    except Exception as exc:
        logger.warning("Question condensation failed, falling back to raw question: %s", exc)
        return question


def answer_question(
    question: str,
    artifacts: RagArtifacts,
    chat_history: str = "",
) -> tuple[str, list[Document]]:
    """Retrieve once, answer once. Docs returned for display are exactly
    the docs used to build the answer's context -- no drift between what
    the user sees cited and what the model actually saw."""

    # Make retrieval aware of prior turns for pronoun/follow-up questions.
    retrieval_query = _condense_question(question, chat_history)

    try:
        documents = artifacts.retriever.invoke(retrieval_query)
    except Exception as exc:
        raise RagError(f"Retrieval failed: {exc}") from exc

    deduped_docs = unique_documents(documents)
    context = make_context_tool(artifacts.retriever).func(retrieval_query)
    chain = build_answer_chain()

    try:
        response = chain.invoke(
            {"question": question, "chat_history": chat_history, "context": context}
        )
    except Exception as exc:
        raise RagError(f"Answer generation failed: {exc}") from exc

    return response, deduped_docs