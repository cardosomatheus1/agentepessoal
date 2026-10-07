"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Check, ChevronDown, Monitor, Paperclip, Square, Zap, Sparkles, Brain } from "lucide-react";
import { MODES, type ModeId } from "@/lib/models";

const MODE_ICONS: Record<ModeId, typeof Zap> = {
  rapido: Zap,
  padrao: Sparkles,
  power: Brain,
};

interface Props {
  mode: ModeId;
  onModeChange: (m: ModeId) => void;
  onSend: (text: string) => void;
  onStop: () => void;
  busy: boolean;
  big?: boolean;
}

export function Composer({ mode, onModeChange, onSend, onStop, busy, big }: Props) {
  const [text, setText] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const ta = useRef<HTMLTextAreaElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ta.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = Math.min(el.scrollHeight, 220) + "px";
  }, [text]);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(t);
  }, [toast]);

  const submit = () => {
    const v = text.trim();
    if (!v || busy) return;
    onSend(v);
    setText("");
  };

  const ModeIcon = MODE_ICONS[mode];

  return (
    <div className="relative w-full">
      {toast && (
        <div className="absolute -top-11 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full border border-line bg-surface-2 px-4 py-1.5 text-[13px] text-muted shadow-lg">
          {toast}
        </div>
      )}
      <div
        className="rounded-[28px] border border-line bg-surface shadow-[0_8px_30px_rgba(0,0,0,0.35)] transition-colors focus-within:border-line-strong"
        onClick={() => ta.current?.focus()}
      >
        <textarea
          ref={ta}
          value={text}
          rows={1}
          autoFocus
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={big ? "O que você quer saber?" : "Pergunte qualquer coisa"}
          aria-label="Mensagem"
          className={`block w-full resize-none bg-transparent px-5 text-fg placeholder:text-faint focus:outline-none ${
            big ? "pt-5 pb-3 text-[16px]" : "pt-4 pb-2 text-[15.5px]"
          }`}
        />
        <div className="flex items-center gap-1.5 px-3 pb-3">
          <IconButton label="Anexar arquivo" onClick={() => setToast("Anexos chegam na fase 3")}>
            <Paperclip size={18} />
          </IconButton>

          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setToast("Modo agente chega na fase 2");
            }}
            className="flex h-9 items-center gap-1.5 rounded-full border border-line px-3 text-[13px] text-muted transition-colors hover:bg-surface-hover hover:text-fg"
          >
            <Monitor size={15} />
            Agente
          </button>

          <div className="ml-auto flex items-center gap-1.5">
            <div className="relative" ref={menuRef}>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setMenuOpen((o) => !o);
                }}
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                className="flex h-9 items-center gap-1.5 rounded-full px-3 text-[13px] text-fg transition-colors hover:bg-surface-hover"
              >
                <ModeIcon size={15} className="text-muted" />
                {MODES[mode].label}
                <ChevronDown size={14} className="text-faint" />
              </button>
              {menuOpen && (
                <div
                  role="menu"
                  className="absolute right-0 bottom-11 z-30 w-72 rounded-2xl border border-line bg-surface-2 p-1.5 shadow-2xl"
                >
                  {(Object.keys(MODES) as ModeId[]).map((id) => {
                    const Icon = MODE_ICONS[id];
                    return (
                      <button
                        key={id}
                        role="menuitemradio"
                        aria-checked={id === mode}
                        onClick={(e) => {
                          e.stopPropagation();
                          onModeChange(id);
                          setMenuOpen(false);
                        }}
                        className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-surface-hover"
                      >
                        <Icon size={17} className="shrink-0 text-muted" />
                        <span className="flex-1">
                          <span className="block text-[14px] text-fg">{MODES[id].label}</span>
                          <span className="block text-[12.5px] text-faint">{MODES[id].hint}</span>
                        </span>
                        {id === mode && <Check size={16} className="text-fg" />}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {busy ? (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onStop();
                }}
                aria-label="Parar"
                className="flex h-9 w-9 items-center justify-center rounded-full bg-accent text-accent-fg transition-opacity hover:opacity-85"
              >
                <Square size={13} fill="currentColor" />
              </button>
            ) : (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  submit();
                }}
                disabled={!text.trim()}
                aria-label="Enviar"
                className="flex h-9 w-9 items-center justify-center rounded-full bg-accent text-accent-fg transition-opacity hover:opacity-85 disabled:bg-surface-hover disabled:text-faint"
              >
                <ArrowUp size={18} strokeWidth={2.4} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function IconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className="flex h-9 w-9 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface-hover hover:text-fg"
    >
      {children}
    </button>
  );
}
