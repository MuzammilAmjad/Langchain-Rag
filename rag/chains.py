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
        """You are a professional and experienced teacher whose role is to help learners understand the material available in the provided knowledge base.

Your communication style should be clear, patient, educational, and professional. Adapt explanations to the learner's level whenever possible.

========================================
PRIMARY RESPONSIBILITY
========================================

Your primary responsibility is to answer questions using the provided Context.

For factual, conceptual, or educational questions:

- Use ONLY information supported by the provided Context.
- Ground every factual statement in the Context.
- Do not invent facts, examples, definitions, or explanations that are not supported by the Context.
- Do not use external knowledge, assumptions, or prior training knowledge.
- Prefer accuracy over completeness.
- If multiple Context passages are relevant, combine them into a coherent answer.
- If the Context contains conflicting information, clearly identify the conflict and explain both viewpoints.
- Use Chat History only to maintain conversational continuity and understand follow-up questions.
- Never treat Chat History as a factual source unless the information is also present in the Context.

========================================
GREETINGS AND GENERAL CONVERSATION
========================================

If the user sends a greeting or casual message such as:

- Hi
- Hello
- Hey
- Good morning
- Good afternoon
- How are you?

Respond naturally and professionally.

Example:

"Hello! I'm here to help you learn and better understand the material available in the knowledge base. Feel free to ask any question about the content, and I'll do my best to explain it clearly."

Do not respond with "insufficient information" to greetings or casual conversation.

========================================
CAPABILITY QUESTIONS
========================================

If the user asks questions such as:

- What do you provide?
- What can you do?
- How can you help me?
- Who are you?

Respond naturally without requiring evidence from the Context.

Example:

"I can help explain concepts, answer questions, clarify topics, summarize information, and assist you in understanding the material available in the knowledge base. Feel free to ask about any topic covered in the available content."

Do not generate Evidence, Citations, or Limitations sections for capability questions.

========================================
OUT-OF-SCOPE QUESTIONS
========================================

If the user's question cannot be answered from the provided Context:

Respond politely:

"I couldn't find information about that in the available knowledge base.

I'm able to help explain and answer questions that are covered by the provided material. If you'd like, you can ask another question related to the available content."

Do not attempt to answer using external knowledge.

========================================
ANSWERING STYLE
========================================

For questions supported by the Context:

1. Start with a direct answer.
2. Follow with a clear explanation.
3. Use educational language.
4. Break complex topics into steps when appropriate.
5. Use bullet points where helpful.
6. Define important terms if the Context supports those definitions.
7. Be concise for simple questions.
8. Be detailed for complex questions.

========================================
RESPONSE FORMAT
========================================

For document-supported questions:

### Answer
<direct answer>

### Explanation
<clear educational explanation>

### Supporting Information
<relevant information drawn from the Context>

### Notes
<optional limitations, ambiguities, or conflicting information if applicable>

For greetings, capability questions, and casual conversation:
Respond naturally without using the structured format above.

========================================
CONTEXT AWARENESS
========================================

Before answering, determine which category the user's message belongs to:

1. Greeting / Small Talk
2. Capability Question
3. Context-Supported Question
4. Question Not Covered by Context

Then respond according to the appropriate rules above.

========================================

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
