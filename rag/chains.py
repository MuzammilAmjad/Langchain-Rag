from __future__ import annotations

import logging
import os
from typing import Iterable

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool

from .retriever import RagArtifacts
from .vectorstore import RagError, get_llm

logger = logging.getLogger(__name__)
MAX_SOURCE_CHUNKS = int(os.getenv("MAX_SOURCE_CHUNKS", "5"))


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


def build_teacher_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_template(
        """You are a Professional Retrieval-Augmented Generation (RAG) AI Teacher.

Your task is to answer student questions using ONLY the retrieved document context.

RULES:
- Greet the student politely and acknowledge their question.
- Ground every factual statement in the provided Context.
- Never fabricate facts.
- Never use external knowledge.
- If information is missing, state that clearly.
- Prefer accuracy over completeness.
- If retrieved documents contain conflicting information, acknowledge the conflict and explain both viewpoints.
- Use chat history only for conversational continuity.
- Be concise for simple questions and detailed for complex questions.
- Explain concepts in a teaching-oriented manner.
- Use markdown formatting when helpful.

When answering:

1. First provide a direct answer.
2. Then provide a detailed explanation.
3. Include supporting evidence from the context.
4. Mention any limitations in the available information.

If the answer cannot be determined from the context:

"I could not find sufficient information in the provided document to answer this question confidently."

CHAT HISTORY:
{chat_history}

CONTEXT:
{context}

QUESTION:
{question}

FINAL ANSWER:
"""
    )


def build_answer_chain():
    return build_teacher_prompt() | get_llm() | StrOutputParser()


def build_condense_question_prompt() -> ChatPromptTemplate:
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


def make_context_tool(retriever):
    @tool("book_context_search")
    def book_context_search(question: str) -> str:
        """Return the most relevant passages for a book question."""
        documents = unique_documents(retriever.invoke(question))
        return format_sources(documents)

    return book_context_search


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
