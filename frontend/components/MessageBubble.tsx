"use client";

import { useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Copy, Check, Bookmark, Smile, Frown } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { SourceCitation } from "@/lib/api";

function linkifyCitations(text: string): string {
  return text.replace(/\[(\d+)\]/g, (_m, num) => `[${num}](#cite-${num})`);
}

export default function MessageBubble({
  role,
  content,
  sources,
}: {
  role: "user" | "assistant";
  content: string;
  sources?: SourceCitation[];
}) {
  if (role === "user") {
    return (
      <div className="flex justify-end gap-3">
        <div className="max-w-[85%] sm:max-w-[80%]">
          <div className="mb-1 flex items-center justify-end gap-2 text-body1 text-text-faint">
            <span className="text-sub2 text-white">You</span>
          </div>
          <div className="rounded-2xl rounded-tr-sm bg-white/10 px-4 py-3 text-body1 text-white">{content}</div>
        </div>
      </div>
    );
  }

  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [reaction, setReaction] = useState<"up" | "down" | null>(null);
  const sourceRefs = useRef<Record<number, HTMLDivElement | null>>({});

  const sourceById = useMemo(() => {
    const map = new Map<number, SourceCitation>();
    (sources ?? []).forEach((s, i) => map.set(s.id ?? i + 1, s));
    return map;
  }, [sources]);

  const processedContent = useMemo(() => linkifyCitations(content || ""), [content]);

  const goToSource = (id: number) => {
    setExpanded(true);
    requestAnimationFrame(() => {
      const el = sourceRefs.current[id];
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      el?.classList.add("ring-2", "ring-accent");
      setTimeout(() => el?.classList.remove("ring-2", "ring-accent"), 1200);
    });
  };

  const copy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="flex gap-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent">
        <span className="text-sub2 text-white">AI</span>
      </div>

      <div className="min-w-0 flex-1">
        <div className="mb-1 text-sub2 text-white">Response</div>

        <div className="rounded-2xl rounded-tl-sm bg-rail px-4 py-3 sm:px-5 sm:py-4">
          <div className="prose prose-invert prose-sm max-w-none text-body1 leading-relaxed text-white">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children }) => {
                  const citeMatch = href?.match(/^#cite-(\d+)$/);
                  if (citeMatch) {
                    const id = Number(citeMatch[1]);
                    const source = sourceById.get(id);
                    return (
                      <button
                        onClick={() => goToSource(id)}
                        title={source ? `${source.source} — page ${source.page}` : "Source"}
                        className="mx-0.5 inline-flex h-5 min-w-5 -translate-y-0.5 items-center justify-center rounded bg-accent/20 px-1.5 text-xs font-semibold text-accent align-super transition hover:bg-accent/30"
                      >
                        {id}
                      </button>
                    );
                  }
                  return (
                    <a href={href} target="_blank" rel="noreferrer" className="text-accent underline">
                      {children}
                    </a>
                  );
                },
              }}
            >
              {processedContent || "…"}
            </ReactMarkdown>
          </div>

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
            <div className="flex items-center gap-1">
              <button
                onClick={() => setReaction((r) => (r === "up" ? null : "up"))}
                className={`flex h-9 w-9 items-center justify-center rounded-lg transition ${
                  reaction === "up" ? "bg-accent/20 text-accent" : "text-text-faint hover:bg-panel hover:text-white"
                }`}
              >
                <Smile size={17} />
              </button>
              <button
                onClick={() => setReaction((r) => (r === "down" ? null : "down"))}
                className={`flex h-9 w-9 items-center justify-center rounded-lg transition ${
                  reaction === "down" ? "bg-danger/20 text-danger" : "text-text-faint hover:bg-panel hover:text-white"
                }`}
              >
                <Frown size={17} />
              </button>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={copy}
                className="flex h-9 items-center gap-1.5 rounded-lg bg-muted-bg px-3 text-body1 font-medium text-white transition hover:opacity-90"
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                {copied ? "Copied" : "Copy"}
              </button>
              <button className="flex h-9 w-9 items-center justify-center rounded-lg text-text-faint transition hover:bg-panel hover:text-white">
                <Bookmark size={16} />
              </button>
            </div>
          </div>
        </div>

        {sources && sources.length > 0 && (
          <div className="mt-2">
            <button
              onClick={() => setExpanded((v) => !v)}
              className="flex items-center gap-1.5 text-body1 text-text-faint transition hover:text-white"
            >
              {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
              Grounding Context Citations ({sources.length})
            </button>
            {expanded && (
              <div className="mt-2 space-y-2">
                {sources.map((s, i) => {
                  const id = s.id ?? i + 1;
                  return (
                    <div
                      key={id}
                      ref={(el) => {
                        sourceRefs.current[id] = el;
                      }}
                      className="rounded-lg border border-border bg-rail p-3 text-body1 text-text-muted transition"
                    >
                      <p className="mb-1 text-sub2 text-white">
                        [{id}] {s.source} (Page {s.page})
                      </p>
                      <p className="text-body1 italic text-text-faint">&ldquo;{s.excerpt}…&rdquo;</p>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}