"use client";

import { useMemo, useState } from "react";
import { PanelLeftClose, PenSquare, Search, Trash2, X } from "lucide-react";
import { groupByDate, type Conversation } from "@/lib/store";
import { Logo } from "./Logo";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  open: boolean;
  onClose: () => void;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

export function Sidebar({ conversations, activeId, open, onClose, onSelect, onNew, onDelete }: Props) {
  const [query, setQuery] = useState("");
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q
      ? conversations.filter(
          (c) =>
            c.title.toLowerCase().includes(q) ||
            c.messages.some((m) => m.content.toLowerCase().includes(q)),
        )
      : conversations;
    return groupByDate(list);
  }, [conversations, query]);

  return (
    <>
      {/* mobile overlay */}
      <div
        onClick={onClose}
        className={`fixed inset-0 z-30 bg-black/60 transition-opacity md:hidden ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[280px] flex-col border-r border-line bg-bg-side transition-transform duration-200 md:static md:z-auto ${
          open ? "translate-x-0" : "-translate-x-full md:hidden"
        }`}
        aria-label="Conversas"
      >
        <div className="flex h-14 items-center gap-2 px-3">
          <div className="flex items-center gap-2 px-1.5">
            <Logo size={24} />
            <span className="text-[15px] font-semibold tracking-tight">Agente</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar barra lateral"
            className="ml-auto flex h-9 w-9 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface hover:text-fg"
          >
            <PanelLeftClose size={18} className="hidden md:block" />
            <X size={18} className="md:hidden" />
          </button>
        </div>

        <div className="space-y-1 px-3 pb-2">
          <button
            type="button"
            onClick={onNew}
            className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] transition-colors hover:bg-surface"
          >
            <PenSquare size={17} className="text-muted" />
            Nova conversa
          </button>
          <label className="flex items-center gap-3 rounded-xl px-3 py-2 text-[14px] text-muted focus-within:bg-surface">
            <Search size={17} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Buscar"
              className="w-full bg-transparent text-fg placeholder:text-muted focus:outline-none"
            />
          </label>
        </div>

        <nav className="scroll-thin flex-1 overflow-y-auto px-3 pb-4">
          {groups.length === 0 && (
            <p className="px-3 pt-4 text-[13px] text-faint">
              {query ? "Nada encontrado." : "Suas conversas aparecem aqui."}
            </p>
          )}
          {groups.map((g) => (
            <div key={g.label} className="pt-4">
              <div className="px-3 pb-1.5 text-[12px] font-medium text-faint">{g.label}</div>
              {g.items.map((c) => (
                <div
                  key={c.id}
                  className={`group flex items-center rounded-xl transition-colors ${
                    c.id === activeId ? "bg-surface" : "hover:bg-surface/60"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(c.id)}
                    className={`min-w-0 flex-1 truncate px-3 py-2 text-left text-[14px] ${
                      c.id === activeId ? "text-fg" : "text-muted"
                    }`}
                  >
                    {c.title}
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(c.id)}
                    aria-label={`Apagar ${c.title}`}
                    className="mr-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-faint opacity-100 transition-opacity hover:text-danger md:opacity-0 md:group-hover:opacity-100 md:focus:opacity-100"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          ))}
        </nav>
      </aside>
    </>
  );
}
