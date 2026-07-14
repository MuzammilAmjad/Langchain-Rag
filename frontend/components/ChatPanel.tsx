"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUp,
  Search,
  MessageSquareText,
  Zap,
  Sparkles,
  Mic,
  Menu,
  X,
  ChevronUp,
  ChevronDown,
  MoreHorizontal,
} from "lucide-react";
import { streamChat, getConversationMessages, ChatMessageT } from "@/lib/api";
import MessageBubble from "@/components/MessageBubble";

export default function ChatPanel({
  activeConversationId,
  activeConversationTitle,
  hasActiveDocument,
  onOpenMenu,
  onRenameConversation,
  onDeleteConversation,
  onConversationUpdated,
}: {
  activeConversationId: number | null;
  activeConversationTitle: string;
  hasActiveDocument: boolean;
  onOpenMenu: () => void;
  onRenameConversation: (id: number, title: string) => Promise<void>;
  onDeleteConversation: (id: number) => Promise<void>;
  onConversationUpdated: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessageT[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const messageRefs = useRef<(HTMLDivElement | null)[]>([]);

  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [matchCursor, setMatchCursor] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (activeConversationId == null) {
      setMessages([]);
      setLoadingHistory(false);
      return;
    }
    setLoadingHistory(true);
    getConversationMessages(activeConversationId)
      .then(setMessages)
      .catch(() => setMessages([]))
      .finally(() => setLoadingHistory(false));
  }, [activeConversationId]);

  useEffect(() => {
    if (!searchOpen) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, searchOpen]);

  const matches = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return [];
    return messages.reduce<number[]>((acc, m, i) => {
      if (m.content.toLowerCase().includes(q)) acc.push(i);
      return acc;
    }, []);
  }, [searchQuery, messages]);

  useEffect(() => setMatchCursor(0), [searchQuery]);

  useEffect(() => {
    if (matches.length === 0) return;
    messageRefs.current[matches[matchCursor]]?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [matchCursor, matches]);

  const send = async () => {
    const question = input.trim();
    if (!question || streaming || !hasActiveDocument || activeConversationId == null) return;

    setMessages((prev) => [...prev, { role: "user", content: question }, { role: "assistant", content: "" }]);
    setInput("");
    setStreaming(true);

    await streamChat(question, activeConversationId, {
      onToken: (t) =>
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { ...next[next.length - 1], content: next[next.length - 1].content + t };
          return next;
        }),
      onSources: (sources) =>
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { ...next[next.length - 1], sources };
          return next;
        }),
      onError: (message) =>
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { ...next[next.length - 1], content: `⚠️ ${message}` };
          return next;
        }),
      onDone: () => {
        onConversationUpdated();
      },
    });

    setStreaming(false);
  };

  const handleRename = () => {
    if (activeConversationId == null) return;
    const newTitle = window.prompt("Rename conversation:", activeConversationTitle);
    if (newTitle !== null && newTitle.trim() !== "") {
      onRenameConversation(activeConversationId, newTitle.trim());
    }
  };

  const handleDelete = async () => {
    if (activeConversationId == null) return;
    if (window.confirm("Are you sure you want to delete this conversation?")) {
      await onDeleteConversation(activeConversationId);
    }
  };

  const handleExport = () => {
    if (messages.length === 0) return;
    const mdContent = messages
      .map((m) => {
        const roleLabel = m.role === "user" ? "### You" : "### Assistant";
        let content = `${roleLabel}\n\n${m.content}\n`;
        if (m.sources && m.sources.length > 0) {
          content += `\n**Sources:**\n` + m.sources.map((s) => `- [${s.id}] ${s.source} (Page ${s.page}): "${s.excerpt}"`).join("\n") + "\n";
        }
        return content;
      })
      .join("\n---\n\n");

    const blob = new Blob([mdContent], { type: "text/markdown;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `${activeConversationTitle.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.md`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <main className="flex h-full flex-1 flex-col bg-panel">
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <button
            onClick={onOpenMenu}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-text-muted hover:text-white lg:hidden cursor-pointer"
          >
            <Menu size={20} />
          </button>
          {searchOpen ? (
            <div className="flex flex-1 items-center gap-2 rounded-xl bg-rail px-3 py-2">
              <Search size={16} className="shrink-0 text-text-faint" />
              <input
                autoFocus
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search this conversation…"
                className="w-full min-w-0 bg-transparent text-body1 text-white placeholder:text-text-faint focus:outline-none"
              />
              {matches.length > 0 && (
                <span className="shrink-0 text-body1 text-text-faint">
                  {matchCursor + 1}/{matches.length}
                </span>
              )}
              <button
                onClick={() => setMatchCursor((c) => (c - 1 + matches.length) % matches.length)}
                disabled={matches.length === 0}
                className="shrink-0 text-text-faint hover:text-white disabled:opacity-30 cursor-pointer"
              >
                <ChevronUp size={16} />
              </button>
              <button
                onClick={() => setMatchCursor((c) => (c + 1) % matches.length)}
                disabled={matches.length === 0}
                className="shrink-0 text-text-faint hover:text-white disabled:opacity-30 cursor-pointer"
              >
                <ChevronDown size={16} />
              </button>
              <button
                onClick={() => {
                  setSearchOpen(false);
                  setSearchQuery("");
                }}
                className="shrink-0 text-text-faint hover:text-white cursor-pointer"
              >
                <X size={16} />
              </button>
            </div>
          ) : (
            <h2 className="truncate text-h1 text-white">{activeConversationTitle}</h2>
          )}
        </div>

        {!searchOpen && (
          <div className="flex shrink-0 items-center gap-2 relative">
            <button
              onClick={() => setSearchOpen(true)}
              className="flex h-10 w-10 items-center justify-center rounded-lg text-text-muted hover:text-white cursor-pointer"
              title="Search conversation"
            >
              <Search size={18} />
            </button>

            <button
              onClick={() => setMenuOpen((o) => !o)}
              className="flex h-10 w-10 items-center justify-center rounded-lg text-text-muted hover:text-white cursor-pointer"
              title="Conversation options"
            >
              <MoreHorizontal size={18} />
            </button>

            {menuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                <div className="absolute right-0 top-11 w-48 rounded-xl bg-panel border border-border shadow-xl py-1.5 z-20">
                  <button
                    onClick={() => {
                      setMenuOpen(false);
                      handleRename();
                    }}
                    className="flex w-full items-center px-4 py-2.5 text-body1 text-white hover:bg-rail transition text-left cursor-pointer"
                  >
                    Rename conversation
                  </button>
                  <button
                    onClick={() => {
                      setMenuOpen(false);
                      handleExport();
                    }}
                    className="flex w-full items-center px-4 py-2.5 text-body1 text-white hover:bg-rail transition text-left cursor-pointer"
                  >
                    Export as Markdown
                  </button>
                  <div className="border-t border-border my-1" />
                  <button
                    onClick={() => {
                      setMenuOpen(false);
                      handleDelete();
                    }}
                    className="flex w-full items-center px-4 py-2.5 text-body1 text-danger hover:bg-rail transition text-left cursor-pointer font-medium"
                  >
                    Delete conversation
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex min-h-full max-w-[760px] flex-col justify-end px-4 pb-6 sm:px-6">
          {loadingHistory ? (
            <div className="flex flex-1 items-center justify-center text-body1 text-text-faint">Loading…</div>
          ) : messages.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-6 text-center">
              <div>
                <h1 className="text-h1">Book Assistant</h1>
                <p className="mt-1 text-body1 text-text-muted">
                  Start by asking a question and let the assistant search your active documents.
                </p>
              </div>
              <div className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
                <InfoCard
                  icon={<MessageSquareText size={16} className="text-accent" />}
                  title="Examples"
                  items={["\"Summarize chapter 2\"", "\"Compare these two documents\"", "\"List the key definitions\""]}
                />
                <InfoCard
                  icon={<Zap size={16} className="text-warn" />}
                  title="Capabilities"
                  items={["Searches every active document", "Cites the exact source & page", "Remembers earlier turns"]}
                />
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-6 pt-10">
              {messages.map((m, i) => {
                const isMatch = matches.includes(i) && matches[matchCursor] === i;
                const isLast = i === messages.length - 1;
                const isEmptyStreamingAssistant =
                  streaming && isLast && m.role === "assistant" && m.content === "";

                return (
                  <div
                    key={i}
                    ref={(el) => {
                      messageRefs.current[i] = el;
                    }}
                    className={`rounded-2xl transition animate-message-in ${isMatch ? "ring-2 ring-accent" : ""}`}
                  >
                    {isEmptyStreamingAssistant ? (
                      <TypingIndicator />
                    ) : (
                      <MessageBubble role={m.role} content={m.content} sources={m.sources} />
                    )}
                  </div>
                );
              })}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </div>

      <div className="mx-auto w-full max-w-[760px] px-4 pb-6 sm:px-6">
        <div
          className={`flex items-center gap-2 rounded-2xl bg-rail p-2 transition-shadow ${streaming ? "ring-1 ring-accent/40" : ""
            }`}
        >
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted-bg text-white ${streaming ? "animate-pulse" : ""
              }`}
          >
            <Sparkles size={16} />
          </div>
          <input
            value={input}
            disabled={!hasActiveDocument}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                send();
              }
            }}
            placeholder={
              hasActiveDocument
                ? streaming
                  ? "Generating response…"
                  : "Ask questions, or type '/' for commands"
                : "Upload and activate a PDF to begin…"
            }
            className="min-w-0 flex-1 bg-transparent px-1 py-2 text-body1 text-white placeholder:text-text-faint focus:outline-none disabled:cursor-not-allowed"
          />
          <button
            disabled
            title="Voice input not available yet"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted-bg text-white opacity-50"
          >
            <Mic size={16} />
          </button>
          <button
            onClick={send}
            disabled={!input.trim() || streaming || !hasActiveDocument}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent text-white transition disabled:cursor-not-allowed disabled:opacity-30"
          >
            {streaming ? (
              <span className="flex h-3 w-3 items-center justify-center">
                <span className="h-2.5 w-2.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
              </span>
            ) : (
              <ArrowUp size={18} />
            )}
          </button>
        </div>
      </div>

      <style jsx global>{`
        @keyframes message-in {
          from {
            opacity: 0;
            transform: translateY(6px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        .animate-message-in {
          animation: message-in 0.25s ease-out;
        }
      `}</style>
    </main>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 rounded-2xl bg-rail px-4 py-3 w-fit">
      <span className="h-2 w-2 rounded-full bg-text-faint animate-bounce [animation-delay:-0.3s]" />
      <span className="h-2 w-2 rounded-full bg-text-faint animate-bounce [animation-delay:-0.15s]" />
      <span className="h-2 w-2 rounded-full bg-text-faint animate-bounce" />
    </div>
  );
}

function InfoCard({ icon, title, items }: { icon: React.ReactNode; title: string; items: string[] }) {
  return (
    <div className="rounded-xl bg-rail p-4 text-left">
      <div className="mb-3 flex items-center gap-2 text-sub2 text-white">
        {icon}
        {title}
      </div>
      <div className="flex flex-col gap-2">
        {items.map((item, i) => (
          <div key={i} className="rounded-lg bg-panel px-3 py-2.5 text-body1 text-text-muted">
            {item}
          </div>
        ))}
      </div>
    </div>
  );
}