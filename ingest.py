from __future__ import annotations

import argparse
from pathlib import Path

from rag import build_retriever, file_signature, load_knowledge_base_manifest, safe_namespace, save_knowledge_base_manifest


DEFAULT_UPLOAD_DIR = Path("uploads")
DEFAULT_MANIFEST_PATH = DEFAULT_UPLOAD_DIR / "active_knowledge_base.json"


def resolve_pdf_path(explicit_path: str | None) -> Path:
    if explicit_path:
        return Path(explicit_path)

    manifest = load_knowledge_base_manifest(DEFAULT_MANIFEST_PATH)
    if manifest:
        manifest_path = Path(manifest["pdf_path"])
        if manifest_path.exists():
            return manifest_path

    pdf_candidates = sorted(DEFAULT_UPLOAD_DIR.glob("*.pdf"), key=lambda candidate: candidate.stat().st_mtime, reverse=True)
    if pdf_candidates:
        return pdf_candidates[0]

    raise FileNotFoundError(
        "No PDF found. Pass --pdf /path/to/book.pdf or upload a PDF into the uploads/ folder first."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a PDF into Pinecone for the book assistant.")
    parser.add_argument("--pdf", help="Path to the PDF to ingest.")
    parser.add_argument("--namespace", help="Optional Pinecone namespace override.")
    args = parser.parse_args()

    pdf_path = resolve_pdf_path(args.pdf)
    namespace = args.namespace or safe_namespace(pdf_path.name, content_signature=file_signature(pdf_path))

    artifacts = build_retriever(pdf_path, namespace, force_rebuild=True)
    save_knowledge_base_manifest(DEFAULT_MANIFEST_PATH, pdf_path, namespace)

    print(f"Ingested {pdf_path.name} into namespace '{namespace}'.")
    print(f"Chunks indexed: {artifacts.source_count}")
    print(f"Pages loaded: {artifacts.page_count}")


if __name__ == "__main__":
    main()