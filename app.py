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
UPLOAD_DIR = Path("uploads")
MANIFEST_PATH = UPLOAD_DIR / "active_knowledge_base.json"

st.set_page_config(page_title=APP_TITLE, page_icon="🤖", layout="wide")

# High-fidelity Layout Styling
st.markdown(
    """
    <style>
        /* Base Canvas Background */
        .stApp {
            background-color: #171717 !important;
            color: #ececec !important;
            font-family: Söhne, ui-sans-serif, system-ui, -apple-system, sans-serif;
        }
        
        /* Direct Injection Styling for the Native Left Column Container */
        div[data-testid="column"]:nth-of-type(1) {
            background-color: #202123 !important;
            border: 1px solid #2f3037 !important;
            border-radius: 12px !important;
            padding: 1.5rem !important;
        }
        
        /* Headers */
        .sidebar-header {
            color: #8e8e93;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            margin-bottom: 0.8rem;
            margin-top: 1rem;
        }

        /* Minimalist Small Control Buttons */
        div[data-testid="stButton"] button {
            background-color: #202123 !important;
            color: #ececec !important;
            border: 1px solid #4d4d4f !important;
            border-radius: 8px !important;
            padding: 0.5rem 0.75rem !important;
            font-size: 0.85rem !important;
            transition: all 0.2s ease;
            text-align: left !important;
        }
        div[data-testid="stButton"] button:hover {
            background-color: #2a2b32 !important;
            border-color: #676767 !important;
        }

        /* File Uploader Container Inversion */
        div[data-testid="stFileUploader"] section {
            background-color: #171717 !important;
            border: 1px dashed #4d4d4f !important;
            border-radius: 8px !important;
        }

        /* Main Workspace Alignment Wrapper */
        .main-chat-container {
            max-width: 720px !important;
            margin: 0 auto !important;
            padding-top: 10vh;
        }
        
        /* Landing Typography Layout */
        .chatgpt-landing {
            text-align: center;
            margin-bottom: 2.5rem;
        }
        .chatgpt-landing h1 {
            font-size: 2.2rem;
            font-weight: 600;
            color: #ececec;
            letter-spacing: -0.02em;
            margin-bottom: 0.75rem;
        }
        .chatgpt-landing p {
            color: #b4b4b4;
            font-size: 0.95rem;
        }

        /* Document Citation Styling Blocks */
        .source-box {
            padding: 0.85rem;
            border-radius: 8px;
            background-color: #202123;
            border: 1px solid #2f3037;
            margin-top: 0.5rem;
            color: #b4b4b4;
            font-size: 0.825rem;
        }
        
        /* Screen-Centered Pinned Chat Input Box */
        div[data-testid="stBottom"] {
            background-color: transparent !important;
            left: 20% !important; /* Offset width matching the left action panel layout */
            right: 0 !important;
            margin: 0 auto !important;
            max-width: 720px !important;
            width: 100% !important;
            padding-bottom: 3rem !important;
        }
        div[data-testid="stChatInput"] {
            background-color: #202123 !important;
            border: 1px solid #2f3037 !important;
            border-radius: 14px !important;
            box-shadow: 0 4px 24px rgba(0,0,0,0.3) !important;
        }
        div[data-testid="stChatInput"] textarea {
            color: #ececec !important;
        }
        
        /* Clean standard dashboard headers/side-toggles */
        header, footer, [data-testid="collapsedControl"] {visibility: hidden;}
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


# --- CHATGPT DUAL-TONE PANEL LAYOUT ---
left_panel, right_panel = st.columns([0.9, 3.1], gap="large")


# --- LEFT PANEL: SETUP CONTROL ---
with left_panel:
    st.markdown("<div class='sidebar-header'>SETUP</div>", unsafe_allow_html=True)
    
    uploaded_file = st.file_uploader("Upload PDF book", type=["pdf"], label_visibility="collapsed")
    build_clicked = st.button("✨ Index Document", use_container_width=True)
    clear_clicked = st.button("🗑️ Clear Active Chat", use_container_width=True)

    if clear_clicked:
        st.session_state.messages = []
        st.toast("Chat history wiped.")

    st.markdown("<div class='sidebar-header'>DOCUMENT DETAILS</div>", unsafe_allow_html=True)
    
    if uploaded_file and build_clicked:
        try:
            pdf_path = save_uploaded_pdf(UPLOAD_DIR, uploaded_file)
            signature = file_signature(pdf_path)
            namespace = safe_namespace(uploaded_file.name, content_signature=signature)
            with st.spinner("Processing..."):
                artifacts = build_retriever(pdf_path, namespace)
            st.session_state.artifacts = artifacts
            st.session_state.uploaded_pdf_name = uploaded_file.name
            st.session_state.uploaded_namespace = namespace
            st.session_state.messages = []
            save_knowledge_base_manifest(MANIFEST_PATH, pdf_path, namespace)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
            
    if st.session_state.artifacts is not None:
        short_name = st.session_state.uploaded_pdf_name
        if len(short_name) > 18:
            short_name = short_name[:15] + "..."
            
        st.markdown(
            f"""
            <div style="font-size: 0.78rem; color: #b4b4b4; line-height: 1.5; background-color: #171717; padding: 0.65rem; border-radius: 6px; border: 1px solid #2f3037;">
                📁 <b>Book:</b> {short_name}<br/>
                🔢 <b>Chunks:</b> {st.session_state.artifacts.source_count}<br/>
                {"📚 <b>Pages:</b> " + str(st.session_state.artifacts.page_count) if st.session_state.artifacts.page_count is not None else ""}
            </div>
            """, 
            unsafe_allow_html=True
        )
    else:
        st.caption("Awaiting workbook ingestion...")


# --- RIGHT PANEL: CHAT INTERFACE ---
with right_panel:
    st.markdown("<div class='main-chat-container'>", unsafe_allow_html=True)
    
    if not st.session_state.messages:
        st.markdown(
            """
            <div class="chatgpt-landing">
                <h1>How can I help you today?</h1>
                <p>Begin a conversation rooted explicitly within your uploaded knowledge archive.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # Core Execution Form Elements
    if st.session_state.artifacts is None:
        st.chat_input("Load an active index in the left setup panel to begin...", disabled=True)
    else:
        user_question = st.chat_input("Message your textbook assistant...")
        if user_question:
            st.session_state.messages.append({"role": "user", "content": user_question})
            with st.chat_message("user"):
                st.markdown(user_question)

            chat_history = "\n".join(
                f"{msg['role'].title()}: {msg['content']}" for msg in st.session_state.messages[:-1]
            )
            
            with st.chat_message("assistant"):
                with st.spinner():
                    answer, sources = answer_question(
                        question=user_question,
                        artifacts=st.session_state.artifacts,
                        chat_history=chat_history,
                    )
                st.markdown(answer)
                
                if sources:
                    with st.expander("Grounding Context Citations", expanded=False):
                        for index, source in enumerate(sources, start=1):
                            metadata = source.metadata or {}
                            page_number = metadata.get("page_number", metadata.get("page", "?"))
                            source_name = metadata.get("source", metadata.get("file_path", "PDF"))
                            st.markdown(
                                f"""
                                <div class="source-box">
                                    <strong>{index}. {Path(source_name).name} (Page {page_number})</strong><br/>
                                    <em>"{source.page_content[:300]}..."</em>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                            
            st.session_state.messages.append({"role": "assistant", "content": answer})
            st.rerun()
            
    st.markdown("</div>", unsafe_allow_html=True)