const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface DocumentInfo {
  namespace: string;
  pdf_name: string;
  source_count: number;
  page_count: number | null;
  active: boolean;
}

export interface SourceCitation {
  id: number;
  source: string;
  page: string | number;
  excerpt: string;
}

export interface ChatMessageT {
  role: "user" | "assistant";
  content: string;
  sources?: SourceCitation[];
}

export async function listDocuments(): Promise<DocumentInfo[]> {
  const res = await fetch(`${API_URL}/api/documents`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load documents");
  return res.json();
}

export async function uploadPdf(file: File): Promise<DocumentInfo> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/api/documents/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "Upload failed");
  }
  return res.json();
}

export async function setDocumentActive(namespace: string, active: boolean): Promise<DocumentInfo> {
  const res = await fetch(`${API_URL}/api/documents/${encodeURIComponent(namespace)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ active }),
  });
  if (!res.ok) throw new Error("Failed to update document");
  return res.json();
}

export async function deleteDocument(namespace: string): Promise<void> {
  const res = await fetch(`${API_URL}/api/documents/${encodeURIComponent(namespace)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete document");
}

export async function getChatHistory(): Promise<ChatMessageT[]> {
  const res = await fetch(`${API_URL}/api/chat/history`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load chat history");
  const rows: { role: string; content: string; sources: SourceCitation[] | null }[] = await res.json();
  return rows.map((r) => ({
    role: r.role as "user" | "assistant",
    content: r.content,
    sources: r.sources ?? undefined,
  }));
}

export async function clearChatHistory(): Promise<void> {
  const res = await fetch(`${API_URL}/api/chat/history`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to clear chat");
}

type StreamEvent =
  | { type: "token"; content: string }
  | { type: "sources"; sources: SourceCitation[] }
  | { type: "error"; message: string }
  | { type: "done" };

export async function streamChat(
  question: string,
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
    body: JSON.stringify({ question }),
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