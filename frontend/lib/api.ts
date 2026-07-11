const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface KnowledgeBase {
  active: boolean;
  pdf_name?: string;
  namespace?: string;
  source_count?: number;
  page_count?: number | null;
}

export interface SourceCitation {
  id: number;
  source: string;
  page: string | number;
  excerpt: string;
}

export interface MessageVersion {
  content: string;
  sources?: SourceCitation[];
}

export interface ChatMessageT {
  role: "user" | "assistant";
  content: string; // for user messages only
  versions?: MessageVersion[]; // for assistant messages only
  versionIndex?: number;
}

export async function getKnowledgeBase(): Promise<KnowledgeBase> {
  const res = await fetch(`${API_URL}/api/knowledge-base`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load knowledge base status");
  return res.json();
}

export async function uploadPdf(file: File): Promise<KnowledgeBase> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/api/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "Upload failed");
  }
  return res.json();
}

type StreamEvent =
  | { type: "token"; content: string }
  | { type: "sources"; sources: SourceCitation[] }
  | { type: "error"; message: string }
  | { type: "done" };

export async function streamChat(
  question: string,
  history: { role: string; content: string }[],
  handlers: {
    onToken: (t: string) => void;
    onSources: (s: SourceCitation[]) => void;
    onError: (m: string) => void;
    onDone: () => void;
  }
) {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history }),
  });

  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => ({}));
    handlers.onError(body.detail ?? "Chat request failed");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      const jsonStr = line.slice(5).trim();
      if (!jsonStr) continue;

      let event: StreamEvent;
      try {
        event = JSON.parse(jsonStr);
      } catch {
        continue;
      }

      if (event.type === "token") handlers.onToken(event.content);
      else if (event.type === "sources") handlers.onSources(event.sources);
      else if (event.type === "error") handlers.onError(event.message);
      else if (event.type === "done") handlers.onDone();
    }
  }
}