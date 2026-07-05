from __future__ import annotations

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from rag import (
    RagArtifacts,
    answer_question,
    build_retriever,
    build_query_artifacts,
    file_signature,
    load_knowledge_base_manifest,
    safe_namespace,
    save_knowledge_base_manifest,
    save_uploaded_pdf,
)

load_dotenv()

APP_TITLE = "Book Assistant RAG Chatbot"
APP_SUBTITLE = "Upload a textbook PDF and ask questions in a teacher-style, student-friendly chat."
UPLOAD_DIR = Path("uploads")
MANIFEST_PATH = UPLOAD_DIR / "active_knowledge_base.json"

st.set_page_config(page_title=APP_TITLE, page_icon="📚", layout="wide")

st.markdown(
    """
    <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(88, 138, 255, 0.18), transparent 28%),
                radial-gradient(circle at top right, rgba(0, 200, 170, 0.14), transparent 24%),
                linear-gradient(180deg, #0b1020 0%, #0f172a 42%, #111827 100%);
            color: #e5e7eb;
        }
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1220px;
        }
        .hero-card, .panel-card {
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(148, 163, 184, 0.18);
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.24);
            backdrop-filter: blur(16px);
            border-radius: 22px;
        }
        .hero-card {
            padding: 1.4rem 1.5rem;
            margin-bottom: 1rem;
        }
        .panel-card {
            padding: 1rem 1.1rem;
            margin-bottom: 1rem;
        }
        .eyebrow {
            text-transform: uppercase;
            letter-spacing: 0.18em;
            font-size: 0.72rem;
            color: #93c5fd;
            margin-bottom: 0.55rem;
        }
        .title {
            font-size: clamp(2rem, 4vw, 3.6rem);
            font-weight: 800;
            line-height: 1.05;
            margin-bottom: 0.6rem;
            color: #f8fafc;
        }
        .subtitle {
            font-size: 1.02rem;
            line-height: 1.7;
            color: #cbd5e1;
            max-width: 860px;
        }
        .metric-row {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.8rem;
            margin-top: 1rem;
        }
        .metric {
            padding: 0.9rem 1rem;
            border-radius: 16px;
            background: rgba(30, 41, 59, 0.78);
            border: 1px solid rgba(148, 163, 184, 0.18);
        }
        .metric-label {
            font-size: 0.8rem;
            color: #94a3b8;
            margin-bottom: 0.35rem;
        }
        .metric-value {
            font-size: 1.05rem;
            font-weight: 700;
            color: #f8fafc;
        }
        .stChatMessage {
            border-radius: 18px;
        }
        .stChatMessage[data-testid="stChatMessage"] {
            background: rgba(15, 23, 42, 0.72);
            border: 1px solid rgba(148, 163, 184, 0.12);
        }
        .stTextInput input, .stTextArea textarea {
            background: rgba(15, 23, 42, 0.75) !important;
            color: #f8fafc !important;
            border: 1px solid rgba(148, 163, 184, 0.2) !important;
        }
        .stButton button {
            background: linear-gradient(135deg, #60a5fa, #34d399) !important;
            color: #0f172a !important;
            border: 0 !important;
            font-weight: 700 !important;
            border-radius: 12px !important;
        }
        .source-box {
            padding: 0.85rem 0.95rem;
            border-radius: 14px;
            background: rgba(15, 23, 42, 0.64);
            border: 1px solid rgba(148, 163, 184, 0.14);
            margin-top: 0.6rem;
        }
        @media (max-width: 900px) {
            .metric-row {
                grid-template-columns: 1fr;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "artifacts" not in st.session_state:
    st.session_state.artifacts = None
if "uploaded_pdf_name" not in st.session_state:
    st.session_state.uploaded_pdf_name = None
if "uploaded_namespace" not in st.session_state:
    st.session_state.uploaded_namespace = None
if "book_summary" not in st.session_state:
    st.session_state.book_summary = None


def _hydrate_existing_knowledge_base() -> None:
    if st.session_state.artifacts is not None:
        return

    manifest = load_knowledge_base_manifest(MANIFEST_PATH)
    if not manifest:
        return

    pdf_path = Path(manifest["pdf_path"])
    namespace = manifest["namespace"]
    if not namespace:
        return

    try:
        artifacts = build_query_artifacts(namespace)
    except Exception:
        return

    st.session_state.artifacts = artifacts
    st.session_state.uploaded_pdf_name = manifest.get("pdf_name") or pdf_path.name
    st.session_state.uploaded_namespace = namespace


_hydrate_existing_knowledge_base()

st.markdown(
    f"""
    <div class="hero-card">
        <div class="eyebrow">LangChain Book Assistant</div>
        <div class="title">{APP_TITLE}</div>
        <div class="subtitle">{APP_SUBTITLE}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### Setup")
    st.caption("Fill the environment variables in `.env` before building the knowledge base.")
    st.write("Required keys:")
    st.code("OPENAI_API_KEY\nPINECONE_API_KEY")

    uploaded_file = st.file_uploader("Upload a PDF book", type=["pdf"])
    build_clicked = st.button("Build or Rebuild Knowledge Base", use_container_width=True)
    clear_clicked = st.button("Clear Chat", use_container_width=True)

    if clear_clicked:
        st.session_state.messages = []
        st.toast("Chat history cleared.")

    if st.session_state.artifacts is not None:
        st.markdown("### Connection")
        st.success("Knowledge base connected")
        st.write(st.session_state.uploaded_pdf_name)
        st.write(st.session_state.uploaded_namespace)
        st.write(f"Chunks indexed: {st.session_state.artifacts.source_count}")
        if st.session_state.artifacts.page_count is not None:
            st.write(f"Loaded pages: {st.session_state.artifacts.page_count}")
    else:
        st.info("No knowledge base connected yet.")

main_col, side_col = st.columns([1.55, 1], gap="large")

with main_col:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
    st.markdown("### Chat")

    if st.session_state.artifacts is None:
        st.info("Connect a knowledge base to start chatting. If you already built one before, it will reconnect automatically.")
    else:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        user_question = st.chat_input("Ask anything from the uploaded book...")
        if user_question:
            st.session_state.messages.append({"role": "user", "content": user_question})
            with st.chat_message("user"):
                st.markdown(user_question)

            chat_history = "\n".join(
                f"{message['role'].title()}: {message['content']}" for message in st.session_state.messages[:-1]
            )
            with st.chat_message("assistant"):
                with st.spinner("Reading the book and preparing a teacher-style answer..."):
                    answer, sources = answer_question(
                        question=user_question,
                        artifacts=st.session_state.artifacts,
                        chat_history=chat_history,
                    )
                    st.markdown(answer)
                    if sources:
                        with st.expander("Show supporting passages", expanded=False):
                            for index, source in enumerate(sources, start=1):
                                metadata = source.metadata or {}
                                page_number = metadata.get("page_number", metadata.get("page", "?"))
                                source_name = metadata.get("source", metadata.get("file_path", "uploaded pdf"))
                                st.markdown(
                                    f"""
                                    <div class="source-box">
                                        <strong>{index}. {source_name}</strong><br/>
                                        Page: {page_number}<br/>
                                        {source.page_content[:900]}
                                    </div>
                                    """,
                                    unsafe_allow_html=True,
                                )

            st.session_state.messages.append({"role": "assistant", "content": answer})
    st.markdown("</div>", unsafe_allow_html=True)

with side_col:
    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='panel-card'>", unsafe_allow_html=True)
    st.markdown("### Status")
    if uploaded_file and build_clicked:
        try:
            pdf_path = save_uploaded_pdf(UPLOAD_DIR, uploaded_file)
            signature = file_signature(pdf_path)
            namespace = safe_namespace(uploaded_file.name, content_signature=signature)
            with st.spinner("Building your book knowledge base..."):
                artifacts = build_retriever(pdf_path, namespace)
            st.session_state.artifacts = artifacts
            st.session_state.uploaded_pdf_name = uploaded_file.name
            st.session_state.uploaded_namespace = namespace
            st.session_state.messages = []
            save_knowledge_base_manifest(MANIFEST_PATH, pdf_path, namespace)
            st.success(f"Knowledge base built for {uploaded_file.name}")
            st.success("Knowledge base connected")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    elif build_clicked and not uploaded_file:
        st.warning("Choose a PDF first.")
    elif st.session_state.artifacts is None:
        st.info("No knowledge base loaded yet.")
    else:
        st.success("Knowledge base connected")
        st.write("Ready for questions.")

    st.markdown("### Design goals")
    st.write("Dynamic upload-driven workflow")
    st.write("Clear student-friendly answers")
    st.write("Retrieval grounded in the book")
    st.markdown("</div>", unsafe_allow_html=True)
