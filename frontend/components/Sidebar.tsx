"use client";

import { useRef, useState } from "react";
import { Plus, MoreHorizontal, FileText, Layers, BookOpen, Pin, X } from "lucide-react";
import { uploadPdf, KnowledgeBase } from "@/lib/api";

export default function Sidebar({
  kb,
  loadingKb,
  onIndexed,
  onClose,
}: {
  kb: KnowledgeBase;
  loadingKb: boolean;
  onIndexed: () => void;
  onClose?: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [indexing, setIndexing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleIndex = async () => {
    if (!file) return;
    setIndexing(true);
    setError(null);
    try {
      await uploadPdf(file);
      onIndexed();
      setFile(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Indexing failed");
    } finally {
      setIndexing(false);
    }
  };

  return (
    <aside className="flex h-full w-[320px] shrink-0 flex-col gap-4 border-r border-border bg-rail p-5">
      <div className="flex items-center justify-between">
        <h1 className="text-h1">My Book</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => inputRef.current?.click()}
            title="Upload a PDF"
            className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-white transition hover:opacity-90"
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

      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />

      <div className="flex items-center gap-2 rounded-xl bg-panel p-1">
        <div className="flex flex-1 items-center gap-2 rounded-lg bg-rail px-3 py-2.5 text-sub2 text-accent">
          <FileText size={16} />
          DOCUMENT
        </div>
      </div>

      {file && (
        <div className="rounded-xl border border-border bg-panel p-3">
          <p className="text-body1 text-white">{file.name}</p>
          <button
            onClick={handleIndex}
            disabled={indexing}
            className="mt-2 w-full rounded-lg bg-accent px-3 py-2.5 text-sub2 text-white transition hover:opacity-90 disabled:opacity-50"
          >
            {indexing ? "Indexing…" : "Index Document"}
          </button>
          {error && <p className="mt-2 text-body1 text-danger">{error}</p>}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {loadingKb ? (
          <p className="px-1 text-body1 text-text-faint">Loading…</p>
        ) : kb.active ? (
          <div className="rounded-xl bg-panel p-4">
            <div className="mb-1 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Pin size={14} className="text-warn" />
                <span className="text-sub1 text-white">{kb.pdf_name}</span>
              </div>
              <span className="text-body1 text-text-faint">Active</span>
            </div>
            <div className="mt-3 flex flex-col gap-2 text-body1 text-text-muted">
              <div className="flex items-center gap-2">
                <Layers size={14} className="text-text-faint" />
                {kb.source_count} chunks indexed
              </div>
              {kb.page_count != null && (
                <div className="flex items-center gap-2">
                  <BookOpen size={14} className="text-text-faint" />
                  {kb.page_count} pages
                </div>
              )}
            </div>
          </div>
        ) : (
          <p className="px-1 text-body1 text-text-faint">
            Upload a PDF above to build your knowledge base.
          </p>
        )}
      </div>
    </aside>
  );
}