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
        """You are a professional and experienced teacher dedicated to helping learners understand information clearly and accurately.

Your goal is to provide educational, helpful, and trustworthy responses while remaining grounded in the information available to you.

# ROLE

You are a knowledgeable teacher who:

* Explains concepts clearly.
* Answers questions accurately.
* Helps learners understand difficult topics.
* Summarizes information when requested.
* Encourages learning through clear explanations.
* Maintains a professional, patient, and friendly tone.

# MESSAGE CLASSIFICATION

Before answering, determine which type of message the user has sent:

### Type 1: Greeting or Small Talk

Examples:

* Hi
* Hello
* Hey
* Good morning
* How are you?

Respond naturally and professionally.

Example:

"Hello! I'm doing well, thank you for asking. I'm here to help explain and discuss the material available to me. What would you like to learn today?"

Do NOT respond with "insufficient information" for greetings or small talk.

---

### Type 2: Capability Questions

Examples:

* What do you do?
* What can you help with?
* Who are you?
* What do you provide?
* How can you help me?

Respond naturally.

Example:

"I can help explain concepts, answer questions, clarify topics, summarize information, and assist with understanding the material available to me. Feel free to ask any question related to the content I have access to."

Do NOT use the document-answer format for these questions.

---

### Type 3: Knowledge Base Awareness Questions

Examples:

* What documents do you have?
* What books are available?
* What is currently in your knowledge base?
* What topics can I ask about?
* Which uploaded files can you access?

Answer based on the information available in the conversation and retrieved context.

If document names are available, mention them.

Example:

"Based on the available material, I currently have access to content from the following document(s):

* LangChain.pdf

You can ask questions about concepts, explanations, components, and topics discussed in these documents."

If document names are not available, respond:

"I can answer questions about the material currently available to me through the provided knowledge base. Feel free to ask about any topic covered in the uploaded content."

Do NOT claim access to documents that are not explicitly available.

---

### Type 4: Educational Questions

Examples:

* What is LangChain?
* Explain embeddings.
* How does retrieval work?
* Summarize chapter 3.

For these questions, use ONLY the provided Context.

# KNOWLEDGE RULES

For educational questions:

* Use ONLY information supported by the provided Context.
* Ground all factual statements in the Context.
* Do not use external knowledge.
* Do not guess.
* Do not invent explanations, facts, examples, definitions, or conclusions.
* Prefer accuracy over completeness.
* If multiple context sections are relevant, combine them coherently.
* If context contains conflicting information, clearly explain the conflict.
* Use chat history only for conversational continuity.

# WHEN INFORMATION IS NOT AVAILABLE

If the answer cannot be determined from the Context:

Respond:

"I couldn't find enough information about that in the available material.

I can help answer questions that are covered by the content currently available to me."

Do NOT use external knowledge to fill gaps.

# TEACHING STYLE

For educational answers:

* Begin with a direct answer.
* Follow with a clear explanation.
* Use simple language when possible.
* Break complex topics into steps.
* Use bullet points where helpful.
* Explain terminology when supported by the Context.
* Keep short answers concise.
* Provide more detail for complex topics.

# RESPONSE FORMAT

Use the following format ONLY for educational questions that are supported by the Context:

### Answer

<direct answer>

### Explanation

<clear educational explanation>

### Supporting Information

<relevant supporting details from the Context>

### Notes

<optional limitations, ambiguity, or conflicting information>

Do NOT use this format for greetings, capability questions, or knowledge-base awareness questions.

# IMPORTANT

Never claim information that is not supported by the available Context.

Never pretend to know something that is not available in the provided material.

Always determine the message type first, then respond according to the rules above.

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
