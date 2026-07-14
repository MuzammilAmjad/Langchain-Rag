"use client";

import { useEffect, useState } from "react";
import IconRail from "@/components/IconRail";
import Sidebar from "@/components/Sidebar";
import ChatPanel from "@/components/ChatPanel";
import { listDocuments, DocumentInfo } from "@/lib/api";

export default function Home() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);

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

  useEffect(() => {
    refreshDocuments();
  }, []);

  const hasActiveDocument = documents.some((d) => d.active);

  return (
    <div className="relative flex h-screen w-full overflow-hidden bg-rail">
      <div className="hidden lg:flex">
        <IconRail />
        <Sidebar documents={documents} loadingDocs={loadingDocs} onChange={refreshDocuments} />
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
            />
          </div>
        </div>
      )}

      <ChatPanel hasActiveDocument={hasActiveDocument} onOpenMenu={() => setDrawerOpen(true)} />
    </div>
  );
}