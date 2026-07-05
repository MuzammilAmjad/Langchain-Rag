# Book Assistant RAG Chatbot

 A Streamlit-based RAG chatbot for students that indexes uploaded PDFs and answers in a teacher-style tone using LangChain, OpenAI embeddings, Pinecone, ParentDocumentRetriever, MultiQueryRetriever, and an OpenAI chat model.

## Flow

Ingestion flow: PDF -> PyPDFLoader -> TokenTextSplitter -> OpenAI Embeddings (text-embedding-3-small) -> Pinecone

Query flow: Streamlit UI -> PineconeVectorStore -> MultiQueryRetriever -> OpenAI Chat Model (gpt-4o-mini) -> Teacher-Style Answer

The retrieval step is now wrapped in a LangChain `@tool`, and answer generation uses a small LCEL chain so the code stays simple while still being easy to extend into agents later.

## Setup

1. Create and activate the virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in your API keys.
4. Run the app:

```bash
streamlit run app.py
```

### One-time ingestion

Before deploying or after uploading a new PDF, run:

```bash
python ingest.py --pdf /path/to/book.pdf
```

If you already uploaded a PDF through the app, `python ingest.py` will reuse the latest PDF found in `uploads/`.

### Railway deployment

Add these variables in Railway instead of committing `.env`:

```bash
OPENAI_API_KEY=xxxxx
PINECONE_API_KEY=xxxxx
PINECONE_INDEX_NAME=book-assistant-index
PINECONE_CLOUD=aws
PINECONE_REGION=us-east-1
```

The app uses `Procfile` to launch Streamlit on Railway.

## Notes

- The app creates a Pinecone index if it does not already exist.
- Uploaded PDFs are stored locally in `uploads/` before parsing.
- The PDF parser uses `PyPDFLoader`, so Tesseract is not required.
- The answer prompt is tuned for clear, supportive, student-friendly explanations.
