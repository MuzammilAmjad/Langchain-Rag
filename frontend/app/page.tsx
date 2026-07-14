"use client";

import { useEffect, useState } from "react";
import IconRail from "@/components/IconRail";
import Sidebar from "@/components/Sidebar";
import ChatPanel from "@/components/ChatPanel";
import {
  listDocuments,
  DocumentInfo,
  listConversations,
  createConversation,
  deleteConversation,
  renameConversation,
  ConversationInfo,
} from "@/lib/api";

export default function Home() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const [conversations, setConversations] = useState<ConversationInfo[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null);
  const [loadingConversations, setLoadingConversations] = useState(true);

  const refreshDocuments = async () => {
    try {
      const data = await listDocuments();
      setDocuments(data);
    } catch {
      setDocuments([]);
    } finally {
      setLoadingDocs(false);
    }
  };

  const refreshConversations = async (selectIdToRestore?: number) => {
    try {
      const data = await listConversations();
      setConversations(data);
      if (data.length > 0) {
        let targetId = selectIdToRestore;
        if (!targetId && typeof window !== "undefined") {
          const stored = localStorage.getItem("activeConversationId");
          if (stored) targetId = parseInt(stored, 10);
        }
        const exists = data.some((c) => c.id === targetId);
        if (targetId && exists) {
          setActiveConversationId(targetId);
        } else {
          setActiveConversationId(data[0].id);
          if (typeof window !== "undefined") {
            localStorage.setItem("activeConversationId", data[0].id.toString());
          }
        }
      } else {
        const newConv = await createConversation();
        setConversations([newConv]);
        setActiveConversationId(newConv.id);
        if (typeof window !== "undefined") {
          localStorage.setItem("activeConversationId", newConv.id.toString());
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingConversations(false);
    }
  };

  useEffect(() => {
    refreshDocuments();
    refreshConversations();
  }, []);

  const handleCreateConversation = async () => {
    try {
      const newConv = await createConversation();
      setConversations((prev) => [newConv, ...prev]);
      setActiveConversationId(newConv.id);
      if (typeof window !== "undefined") {
        localStorage.setItem("activeConversationId", newConv.id.toString());
      }
    } catch (err) {
      console.error("Failed to create conversation", err);
    }
  };

  const handleDeleteConversation = async (id: number) => {
    try {
      await deleteConversation(id);
      const updated = conversations.filter((c) => c.id !== id);
      if (updated.length === 0) {
        const newConv = await createConversation();
        setConversations([newConv]);
        setActiveConversationId(newConv.id);
        if (typeof window !== "undefined") {
          localStorage.setItem("activeConversationId", newConv.id.toString());
        }
      } else {
        setConversations(updated);
        if (activeConversationId === id) {
          const nextActive = updated[0].id;
          setActiveConversationId(nextActive);
          if (typeof window !== "undefined") {
            localStorage.setItem("activeConversationId", nextActive.toString());
          }
        }
      }
    } catch (err) {
      console.error("Failed to delete conversation", err);
    }
  };

  const handleRenameConversation = async (id: number, title: string) => {
    try {
      const updated = await renameConversation(id, title);
      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, title: updated.title } : c))
      );
    } catch (err) {
      console.error("Failed to rename conversation", err);
    }
  };

  const handleSelectConversation = (id: number) => {
    setActiveConversationId(id);
    if (typeof window !== "undefined") {
      localStorage.setItem("activeConversationId", id.toString());
    }
  };

  const handleConversationUpdated = async () => {
    // Re-fetch conversations list to update title/relative times
    try {
      const data = await listConversations();
      setConversations(data);
    } catch (err) {
      console.error(err);
    }
  };

  const hasActiveDocument = documents.some((d) => d.active);
  const activeConversation = conversations.find((c) => c.id === activeConversationId);
  const activeConversationTitle = activeConversation?.title ?? "Book Assistant";

  return (
    <div className="relative flex h-screen w-full overflow-hidden bg-rail">
      <div className="hidden lg:flex">
        <IconRail />
        <Sidebar
          documents={documents}
          loadingDocs={loadingDocs}
          onChange={refreshDocuments}
          conversations={conversations}
          activeConversationId={activeConversationId}
          onSelectConversation={handleSelectConversation}
          onDeleteConversation={handleDeleteConversation}
          onCreateConversation={handleCreateConversation}
        />
      </div>

      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setDrawerOpen(false)} />
          <div className="relative z-10 flex h-full">
            <IconRail />
            <Sidebar
              documents={documents}
              loadingDocs={loadingDocs}
              onChange={refreshDocuments}
              onClose={() => setDrawerOpen(false)}
              conversations={conversations}
              activeConversationId={activeConversationId}
              onSelectConversation={handleSelectConversation}
              onDeleteConversation={handleDeleteConversation}
              onCreateConversation={handleCreateConversation}
            />
          </div>
        </div>
      )}

      <ChatPanel
        activeConversationId={activeConversationId}
        activeConversationTitle={activeConversationTitle}
        hasActiveDocument={hasActiveDocument}
        onOpenMenu={() => setDrawerOpen(true)}
        onRenameConversation={handleRenameConversation}
        onDeleteConversation={handleDeleteConversation}
        onConversationUpdated={handleConversationUpdated}
      />
    </div>
  );
}