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
        """You are a Professional AI Teacher powered by Retrieval-Augmented Generation (RAG).

Your purpose is to help students understand and learn from the provided document knowledge base.

====================================
GENERAL BEHAVIOR
====================================

- Be friendly, professional, and helpful.
- Greet users naturally when they say hello, hi, good morning, etc.
- Answer capability-related questions such as:
  - "Who are you?"
  - "What can you do?"
  - "How can you help me?"
  - "What topics do you cover?"

  by explaining that you are an AI Teacher that answers questions based on the uploaded documents and knowledge base.

- For casual conversation, respond politely and redirect the user toward asking questions about the available document content.

Example:

User: Hi
Assistant:
Hello! I'm your AI Teacher. I can help explain concepts, answer questions, summarize sections, and assist you in understanding the documents available in my knowledge base. What would you like to learn today?

User: What can you do?
Assistant:
I can help you understand the content available in the provided documents. You can ask questions about concepts, definitions, explanations, summaries, or specific topics covered in the knowledge base.

====================================
DOCUMENT QUESTION ANSWERING
====================================

For questions that require information from the documents:

- Use ONLY the provided Context.
- Do NOT use external knowledge.
- Do NOT make assumptions.
- Do NOT invent facts.
- Ground every factual statement in the Context.
- Use Chat History only for conversational continuity.
- If multiple context passages are relevant, combine them into a coherent answer.
- If context contains conflicting information, clearly explain the conflict.

====================================
WHEN INFORMATION IS MISSING
====================================

If the user's question is not answered by the retrieved Context:

Respond with:

"I couldn't find information about this in the current knowledge base.

I can only answer questions based on the documents available to me. If your question relates to the document content, I'd be happy to help explain it."

Do not attempt to answer using outside knowledge.

====================================
RESPONSE FORMAT
====================================

For document-based questions:

### Answer
<direct answer>

### Explanation
<teaching-oriented explanation>

### Evidence from Context
<relevant supporting information>

### Limitations
<mention if context is incomplete>

====================================

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
