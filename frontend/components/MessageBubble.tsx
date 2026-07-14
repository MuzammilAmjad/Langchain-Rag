"use client";

import { useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Copy, Check, Bookmark, Smile, Frown } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { SourceCitation } from "@/lib/api";
import { useTheme } from "@/components/ThemeContext";

function linkifyCitations(text: string): string {
  return text.replace(/\[(\d+)\]/g, (_m, num) => `[${num}](#cite-${num})`);
}

// Formats a citation as "<page>.<chunk>" e.g. page 1 / chunk 1 -> "1.1",
// page 12 / chunk 1 -> "12.1", page 12 / chunk 2 -> "12.2".
// Page numbers are shown as-is (start at 1), chunk numbers restart at 1 per page.
// Using a separator (instead of concatenating digits) keeps the label short
// and unambiguous even for double/triple-digit page numbers.
function buildCitationLabels(sources: SourceCitation[] | undefined): Map<number, string> {
  const map = new Map<number, string>();
  const chunkCounterByPage = new Map<number, number>();

  (sources ?? []).forEach((s, i) => {
    const id = s.id ?? i + 1;
    const page = Number(s.page ?? 1);
    const chunk = (chunkCounterByPage.get(page) ?? 0) + 1;
    chunkCounterByPage.set(page, chunk);
    map.set(id, `${page}.${chunk}`);
  });

  return map;
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
  const { theme } = useTheme();
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  // NOTE: The reaction (smile/frown) and bookmark states are local-only
  // component states and cosmetic for this version of the app. They do not persist
  // to the database, but maintain visual interactive states for the user.
  const [reaction, setReaction] = useState<"up" | "down" | null>(null);
  const [bookmarked, setBookmarked] = useState(false);
  const sourceRefs = useRef<Record<number, HTMLDivElement | null>>({});

  const sourceById = useMemo(() => {
    const map = new Map<number, SourceCitation>();
    (sources ?? []).forEach((s, i) => map.set(s.id ?? i + 1, s));
    return map;
  }, [sources]);

  const citationLabelById = useMemo(() => buildCitationLabels(sources), [sources]);

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

  return (
    <div className="flex gap-3">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent">
        <span className="text-sub2" style={{ color: "#ffffff" }}>AI</span>
      </div>

      <div className="min-w-0 flex-1">
        <div className="mb-1 text-sub2 text-white">Response</div>

        <div className="rounded-2xl rounded-tl-sm bg-rail px-4 py-3 sm:px-5 sm:py-4">
          <div className={`prose prose-sm max-w-none text-body1 leading-relaxed text-white ${theme === "dark" ? "prose-invert" : ""}`}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children }) => {
                  const citeMatch = href?.match(/^#cite-(\d+)$/);
                  if (citeMatch) {
                    const id = Number(citeMatch[1]);
                    const source = sourceById.get(id);
                    const label = citationLabelById.get(id) ?? String(id);
                    return (
                      <button
                        onClick={() => goToSource(id)}
                        title={source ? `${source.source} — page ${source.page}` : "Source"}
                        className="mx-0.5 inline-flex h-[18px] min-w-[24px] -translate-y-0.5 items-center justify-center rounded-md border border-accent/60 bg-accent px-1.5 align-super font-mono text-[10px] font-bold leading-none tracking-tight text-white shadow-sm transition hover:border-accent hover:bg-accent/90 hover:shadow"
                      >
                        {label}
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
                className={`flex h-9 w-9 items-center justify-center rounded-lg transition ${reaction === "up" ? "bg-accent/20 text-accent" : "text-text-faint hover:bg-panel hover:text-white"
                  }`}
                title="Good response (cosmetic)"
              >
                <Smile size={17} />
              </button>
              <button
                onClick={() => setReaction((r) => (r === "down" ? null : "down"))}
                className={`flex h-9 w-9 items-center justify-center rounded-lg transition ${reaction === "down" ? "bg-danger/20 text-danger" : "text-text-faint hover:bg-panel hover:text-white"
                  }`}
                title="Bad response (cosmetic)"
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
              <button
                onClick={() => setBookmarked((b) => !b)}
                className={`flex h-9 w-9 items-center justify-center rounded-lg transition ${bookmarked ? "bg-accent/20 text-accent" : "text-text-faint hover:bg-panel hover:text-white"
                  }`}
                title="Bookmark message (cosmetic — not persisted)"
              >
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
                  const label = citationLabelById.get(id) ?? String(id);
                  return (
                    <div
                      key={id}
                      ref={(el) => {
                        sourceRefs.current[id] = el;
                      }}
                      className="rounded-lg border border-border bg-rail p-3 text-body1 text-text-muted transition"
                    >
                      <p className="mb-1 flex items-center gap-2 text-sub2 text-white">
                        <span className="inline-flex h-[18px] min-w-[24px] items-center justify-center rounded-md border border-accent/60 bg-accent px-1.5 font-mono text-[10px] font-bold leading-none tracking-tight text-white">
                          {label}
                        </span>
                        {s.source} (Page {s.page})
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