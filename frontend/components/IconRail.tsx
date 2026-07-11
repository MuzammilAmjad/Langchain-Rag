"use client";

import { useState } from "react";
import { Bot, MessageSquare, Sparkles, Moon, Sun } from "lucide-react";

export default function IconRail() {
  const [dark, setDark] = useState(true);

  return (
    <aside className="flex h-full w-[72px] shrink-0 flex-col items-center gap-3 border-r border-border bg-rail py-4">
      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-panel">
        <Bot size={20} className="text-white" />
      </div>

      <div className="mt-2 flex flex-col gap-2">
        <button className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent text-white">
          <MessageSquare size={19} />
        </button>
      </div>

      <div className="mt-auto flex flex-col items-center gap-3">
        <button
          onClick={() => setDark((v) => !v)}
          title="Theme (visual only for now)"
          className="flex h-11 w-11 items-center justify-center rounded-xl border border-border text-text-muted transition hover:text-white"
        >
          {dark ? <Moon size={18} /> : <Sun size={18} />}
        </button>
        <Sparkles size={16} className="text-text-faint" />
      </div>
    </aside>
  );
}