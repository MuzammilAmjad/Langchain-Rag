from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
import streamlit as st
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec
from pinecone.exceptions import PineconeException

load_dotenv()
logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
LLM_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
EMBEDDING_DIMENSION = int(os.getenv("OPENAI_EMBEDDING_DIMENSION", "1536"))
RETRIEVER_TOP_K = int(os.getenv("RETRIEVER_TOP_K", "4"))


class RagError(RuntimeError):
    """Raised for any recoverable failure in the RAG pipeline, safe to show to the user."""


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


def namespace_vector_count(index, namespace: str) -> int:
    stats = index.describe_index_stats()
    namespaces = stats.get("namespaces", {}) or {}
    namespace_stats = namespaces.get(namespace)
    if not namespace_stats:
        return 0
    return int(namespace_stats.get("vector_count", 0) or 0)


def get_vectorstore(namespace: str) -> PineconeVectorStore:
    return PineconeVectorStore(
        index=get_pinecone_index(),
        embedding=get_embeddings(),
        namespace=namespace,
    )
