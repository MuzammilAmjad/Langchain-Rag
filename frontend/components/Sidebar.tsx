"use client";

import { useRef, useState } from "react";
import { Plus, MoreHorizontal, FileText, Layers, BookOpen, Trash2, X } from "lucide-react";
import { uploadPdf, setDocumentActive, deleteDocument, DocumentInfo, ConversationInfo } from "@/lib/api";

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return "Just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHour < 24) return `${diffHour}h ago`;
  if (diffDay === 1) return "Yesterday";
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function Sidebar({
  documents,
  loadingDocs,
  onChange,
  onClose,
  conversations,
  activeConversationId,
  onSelectConversation,
  onDeleteConversation,
  onCreateConversation,
}: {
  documents: DocumentInfo[];
  loadingDocs: boolean;
  onChange: () => void;
  onClose?: () => void;
  conversations: ConversationInfo[];
  activeConversationId: number | null;
  onSelectConversation: (id: number) => void;
  onDeleteConversation: (id: number) => void;
  onCreateConversation: () => void;
}) {
  const [indexing, setIndexing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [libraryMenuOpen, setLibraryMenuOpen] = useState(false);
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
      {/* New Chat Button */}
      <div>
        <button
          onClick={onCreateConversation}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-accent py-3 px-4 text-sub1 font-medium text-white transition hover:opacity-90 active:scale-[0.98] cursor-pointer"
        >
          <Plus size={18} />
          New Chat
        </button>
      </div>

      {/* Conversations List */}
      <div className="flex flex-1 flex-col min-h-0">
        <div className="mb-2 flex items-center justify-between px-1">
          <h2 className="text-sub2 text-text-muted uppercase tracking-wider">Recent Chats</h2>
          {onClose && (
            <button
              onClick={onClose}
              className="text-text-muted hover:text-white lg:hidden cursor-pointer"
              title="Close sidebar"
            >
              <X size={16} />
            </button>
          )}
        </div>
        <div className="flex-1 overflow-y-auto space-y-1 pr-1">
          {conversations.length === 0 ? (
            <p className="px-2 py-3 text-body1 text-text-faint italic">No conversations yet.</p>
          ) : (
            conversations.map((c) => (
              <div
                key={c.id}
                onClick={() => onSelectConversation(c.id)}
                className={`group relative flex items-center justify-between rounded-xl px-3 py-2.5 cursor-pointer transition ${
                  c.id === activeConversationId
                    ? "bg-panel text-white border border-border/20 shadow-sm"
                    : "text-text-muted hover:bg-panel/40 hover:text-white"
                }`}
              >
                <div className="flex flex-col min-w-0 pr-6">
                  <span className="truncate text-sub1 font-medium">{c.title || "New chat"}</span>
                  <span className="text-label1 text-text-faint">{formatRelativeTime(c.updated_at)}</span>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteConversation(c.id);
                  }}
                  className="absolute right-2 opacity-0 group-hover:opacity-100 text-text-faint hover:text-danger p-1 rounded transition-opacity active:scale-95 cursor-pointer"
                  title="Delete chat"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Library Section */}
      <div className="border-t border-border pt-4 flex flex-col h-[280px] shrink-0 min-h-0">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sub1 text-white flex items-center gap-2">
            <BookOpen size={16} className="text-text-faint" />
            My Library
          </h2>
          <div className="relative flex items-center gap-1.5">
            <button
              onClick={() => inputRef.current?.click()}
              disabled={indexing}
              title="Upload a PDF"
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-white transition hover:opacity-90 disabled:opacity-50 cursor-pointer"
            >
              <Plus size={16} />
            </button>
            <button
              onClick={() => setLibraryMenuOpen((o) => !o)}
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-panel text-text-muted hover:text-white transition cursor-pointer"
              title="Library options"
            >
              <MoreHorizontal size={16} />
            </button>

            {libraryMenuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setLibraryMenuOpen(false)} />
                <div className="absolute right-0 top-9 w-44 rounded-xl bg-panel border border-border shadow-xl py-1 z-20">
                  <button
                    onClick={() => {
                      onChange();
                      setLibraryMenuOpen(false);
                    }}
                    className="flex w-full items-center px-3 py-2 text-body1 text-white hover:bg-rail transition text-left cursor-pointer"
                  >
                    Refresh Library
                  </button>
                  <button
                    disabled
                    className="flex w-full items-center px-3 py-2 text-body1 text-text-muted cursor-not-allowed text-left"
                  >
                    Settings (Upcoming)
                  </button>
                </div>
              </>
            )}
          </div>
        </div>

        <input ref={inputRef} type="file" accept="application/pdf" className="hidden" onChange={handleFileChange} />

        {indexing && <p className="text-body1 text-text-muted mb-2 animate-pulse">Indexing…</p>}
        {error && <p className="text-body1 text-danger mb-2">{error}</p>}

        <div className="flex-1 space-y-2 overflow-y-auto pr-1">
          {loadingDocs ? (
            <p className="px-1 text-body1 text-text-faint">Loading…</p>
          ) : documents.length === 0 ? (
            <p className="px-1 text-body1 text-text-faint leading-relaxed">
              Upload a PDF above to build your knowledge base.
            </p>
          ) : (
            documents.map((doc) => (
              <div key={doc.namespace} className="rounded-xl bg-panel p-3 border border-border/10">
                <div className="mb-1.5 flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <FileText size={14} className="shrink-0 text-text-faint" />
                    <span className="truncate text-sub2 font-semibold text-white" title={doc.pdf_name}>
                      {doc.pdf_name}
                    </span>
                  </div>
                  <button
                    onClick={() => remove(doc.namespace)}
                    title="Delete document"
                    className="shrink-0 text-text-faint hover:text-danger transition cursor-pointer"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>

                <div className="mb-2 flex flex-col gap-1 text-body1 text-text-muted">
                  <div className="flex items-center gap-1.5">
                    <Layers size={12} className="text-text-faint" />
                    {doc.source_count} chunks
                  </div>
                  {doc.page_count != null && (
                    <div className="flex items-center gap-1.5">
                      <BookOpen size={12} className="text-text-faint" />
                      {doc.page_count} pages
                    </div>
                  )}
                </div>

                <label className="flex cursor-pointer items-center gap-2 text-body1 text-text-muted hover:text-white transition">
                  <input
                    type="checkbox"
                    checked={doc.active}
                    onChange={(e) => toggleActive(doc.namespace, e.target.checked)}
                    className="h-3.5 w-3.5 accent-accent cursor-pointer"
                  />
                  Search index
                </label>
              </div>
            ))
          )}
        </div>
      </div>
    </aside>
  );
}