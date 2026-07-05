from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import TokenTextSplitter
from pinecone.exceptions import PineconeException

from .vectorstore import (
    RETRIEVER_TOP_K,
    RagError,
    get_llm,
    get_pinecone_index,
    get_vectorstore,
    namespace_has_vectors,
    namespace_vector_count,
)


CHUNK_TOKENS = int(os.getenv("CHUNK_TOKENS", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))


@dataclass(slots=True)
class RagArtifacts:
    retriever: MultiQueryRetriever
    namespace: str
    source_count: int
    page_count: Optional[int]


def safe_namespace(
    uploaded_name: str,
    scope_id: Optional[str] = None,
    content_signature: Optional[str] = None,
) -> str:
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


def load_pdf_documents(pdf_path: Path) -> list[Document]:
    try:
        loader = PyPDFLoader(str(pdf_path))
        return loader.load()
    except Exception as exc:
        raise RagError(f"Could not read PDF '{pdf_path.name}': {exc}") from exc


def split_documents(documents: list[Document]) -> list[Document]:
    splitter = TokenTextSplitter(
        chunk_size=CHUNK_TOKENS,
        chunk_overlap=CHUNK_OVERLAP,
    )
    return splitter.split_documents(documents)


def build_query_artifacts(namespace: str) -> RagArtifacts:
    vectorstore = get_vectorstore(namespace=namespace)
    index = get_pinecone_index()

    if not namespace_has_vectors(index, namespace):
        raise RagError(
            f"No indexed knowledge base found for namespace '{namespace}'. Run ingest.py first."
        )

    multi_query_retriever = MultiQueryRetriever.from_llm(
        retriever=vectorstore.as_retriever(search_kwargs={"k": RETRIEVER_TOP_K}),
        llm=get_llm(),
        include_original=True,
    )

    return RagArtifacts(
        retriever=multi_query_retriever,
        namespace=namespace,
        source_count=namespace_vector_count(index, namespace),
        page_count=None,
    )


def build_retriever(pdf_path: Path, namespace: str, force_rebuild: bool = False) -> RagArtifacts:
    vectorstore = get_vectorstore(namespace=namespace)
    index = get_pinecone_index()

    if not force_rebuild and namespace_has_vectors(index, namespace):
        return build_query_artifacts(namespace)

    raw_documents = load_pdf_documents(pdf_path)
    chunks = split_documents(raw_documents)

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
    import streamlit as st

    indexed = st.session_state.setdefault("indexed_namespaces", {})
    if namespace in indexed:
        return indexed[namespace]

    artifacts = build_retriever(pdf_path, namespace)
    indexed[namespace] = artifacts
    return artifacts
