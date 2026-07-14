"""
One-time migration: reads the old uploads/active_knowledge_base.json
(from the pre-multi-document app) and inserts a matching row into the
new `documents` table, so you don't have to re-upload the PDF.

Run once from the repo root:
    python migrate_manifest.py
"""
from __future__ import annotations

import json
from pathlib import Path

from db import Document, SessionLocal, init_db
from rag import file_signature, get_pinecone_index, load_pdf_documents, namespace_vector_count

MANIFEST_PATH = Path("uploads/active_knowledge_base.json")


def main() -> None:
    if not MANIFEST_PATH.exists():
        print(f"No manifest found at {MANIFEST_PATH} — nothing to migrate.")
        return

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    namespace = manifest.get("namespace")
    pdf_name = manifest.get("pdf_name")
    pdf_path = Path(manifest.get("pdf_path", ""))

    if not namespace or not pdf_name:
        print("Manifest is missing namespace/pdf_name — nothing to migrate.")
        return

    init_db()
    index = get_pinecone_index()
    source_count = namespace_vector_count(index, namespace)

    if source_count == 0:
        print(f"Namespace '{namespace}' has no vectors in Pinecone — nothing to migrate.")
        return

    page_count = None
    if pdf_path.exists():
        try:
            page_count = len(load_pdf_documents(pdf_path))
        except Exception:
            pass  # fine to leave unknown

    signature = file_signature(pdf_path) if pdf_path.exists() else manifest.get("content_signature", "")

    with SessionLocal() as db:
        existing = db.get(Document, namespace)
        if existing:
            print(f"'{pdf_name}' is already in the documents table — skipping.")
            return

        db.add(
            Document(
                namespace=namespace,
                pdf_name=pdf_name,
                content_signature=signature,
                source_count=source_count,
                page_count=page_count,
                active=True,
            )
        )
        db.commit()

    print(f"Migrated '{pdf_name}' (namespace={namespace}, chunks={source_count}, pages={page_count}).")


if __name__ == "__main__":
    main()