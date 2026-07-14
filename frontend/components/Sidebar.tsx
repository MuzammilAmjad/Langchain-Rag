"use client";

import { useRef, useState } from "react";
import { Plus, MoreHorizontal, FileText, Layers, BookOpen, Trash2, X } from "lucide-react";
import { uploadPdf, setDocumentActive, deleteDocument, DocumentInfo } from "@/lib/api";

export default function Sidebar({
  documents,
  loadingDocs,
  onChange,
  onClose,
}: {
  documents: DocumentInfo[];
  loadingDocs: boolean;
  onChange: () => void;
  onClose?: () => void;
}) {
  const [indexing, setIndexing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setIndexing(true);
    setError(null);
    try {
      await uploadPdf(file);
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setIndexing(false);
    }
  };

  const toggleActive = async (namespace: string, active: boolean) => {
    try {
      await setDocumentActive(namespace, active);
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update document");
    }
  };

  const remove = async (namespace: string) => {
    try {
      await deleteDocument(namespace);
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete document");
    }
  };

  return (
    <aside className="flex h-full w-[320px] shrink-0 flex-col gap-4 border-r border-border bg-rail p-5">
      <div className="flex items-center justify-between">
        <h1 className="text-h1">My Library</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => inputRef.current?.click()}
            disabled={indexing}
            title="Upload a PDF"
            className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-white transition hover:opacity-90 disabled:opacity-50"
          >
            <Plus size={18} />
          </button>
          <button className="flex h-10 w-10 items-center justify-center rounded-lg bg-panel text-text-muted">
            <MoreHorizontal size={18} />
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="flex h-10 w-10 items-center justify-center rounded-lg bg-panel text-text-muted lg:hidden"
            >
              <X size={18} />
            </button>
          )}
        </div>
      </div>

      <input ref={inputRef} type="file" accept="application/pdf" className="hidden" onChange={handleFileChange} />

      {indexing && <p className="text-body1 text-text-muted">Indexing…</p>}
      {error && <p className="text-body1 text-danger">{error}</p>}

      <div className="flex-1 space-y-2 overflow-y-auto">
        {loadingDocs ? (
          <p className="px-1 text-body1 text-text-faint">Loading…</p>
        ) : documents.length === 0 ? (
          <p className="px-1 text-body1 text-text-faint">
            Upload a PDF above to build your knowledge base.
          </p>
        ) : (
          documents.map((doc) => (
            <div key={doc.namespace} className="rounded-xl bg-panel p-4">
              <div className="mb-2 flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <FileText size={15} className="shrink-0 text-text-faint" />
                  <span className="truncate text-sub1 text-white">{doc.pdf_name}</span>
                </div>
                <button
                  onClick={() => remove(doc.namespace)}
                  title="Delete document"
                  className="shrink-0 text-text-faint hover:text-danger"
                >
                  <Trash2 size={15} />
                </button>
              </div>

              <div className="mb-3 flex flex-col gap-1.5 text-body1 text-text-muted">
                <div className="flex items-center gap-2">
                  <Layers size={13} className="text-text-faint" />
                  {doc.source_count} chunks indexed
                </div>
                {doc.page_count != null && (
                  <div className="flex items-center gap-2">
                    <BookOpen size={13} className="text-text-faint" />
                    {doc.page_count} pages
                  </div>
                )}
              </div>

              <label className="flex cursor-pointer items-center gap-2 text-body1 text-text-muted">
                <input
                  type="checkbox"
                  checked={doc.active}
                  onChange={(e) => toggleActive(doc.namespace, e.target.checked)}
                  className="h-4 w-4 accent-accent"
                />
                Include in chat search
              </label>
            </div>
          ))
        )}
      </div>
    </aside>
  );
}