"use client";

import { Bot, MessageSquare, Sparkles, Moon, Sun } from "lucide-react";
import { useTheme } from "@/components/ThemeContext";

export default function IconRail() {
  const { theme, toggleTheme } = useTheme();

  return (
    <aside className="flex h-full w-[72px] shrink-0 flex-col items-center gap-3 border-r border-border bg-rail py-4">
      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-panel">
        <Bot size={20} className="text-white" />
      </div>

      <div className="mt-2 flex flex-col gap-2">
        <button
          aria-current="page"
          className="flex h-11 w-11 items-center justify-center rounded-xl bg-accent text-white shadow-sm cursor-pointer"
          title="Chat (Active)"
        >
          <MessageSquare size={19} />
        </button>
      </div>

      <div className="mt-auto flex flex-col items-center gap-3">
        <button
          onClick={toggleTheme}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          className="flex h-11 w-11 items-center justify-center rounded-xl border border-border text-text-muted transition hover:text-white cursor-pointer"
        >
          {theme === "dark" ? <Moon size={18} /> : <Sun size={18} />}
        </button>
        <Sparkles size={16} className="text-text-faint animate-pulse" />
      </div>
    </aside>
  );
}