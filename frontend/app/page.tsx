"use client";

import { useEffect, useState } from "react";
import IconRail from "@/components/IconRail";
import Sidebar from "@/components/Sidebar";
import ChatPanel from "@/components/ChatPanel";
import { getKnowledgeBase, KnowledgeBase } from "@/lib/api";

export default function Home() {
  const [kb, setKb] = useState<KnowledgeBase>({ active: false });
  const [loadingKb, setLoadingKb] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const refreshKb = async () => {
    try {
      const data = await getKnowledgeBase();
      setKb(data);
    } catch {
      setKb({ active: false });
    } finally {
      setLoadingKb(false);
    }
  };

  useEffect(() => {
    refreshKb();
  }, []);

  return (
    <div className="relative flex h-screen w-full overflow-hidden bg-rail">
      {/* Desktop: rail + sidebar always visible */}
      <div className="hidden lg:flex">
        <IconRail />
        <Sidebar kb={kb} loadingKb={loadingKb} onIndexed={refreshKb} />
      </div>

      {/* Mobile: drawer overlay */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setDrawerOpen(false)} />
          <div className="relative z-10 flex h-full">
            <IconRail />
            <Sidebar
              kb={kb}
              loadingKb={loadingKb}
              onIndexed={() => {
                refreshKb();
                setDrawerOpen(false);
              }}
              onClose={() => setDrawerOpen(false)}
            />
          </div>
        </div>
      )}

      <ChatPanel kb={kb} onOpenMenu={() => setDrawerOpen(true)} />
    </div>
  );
}