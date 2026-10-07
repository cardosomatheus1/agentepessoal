"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowDown, PanelLeftOpen, PenSquare } from "lucide-react";
import { Composer } from "./Composer";
import { Sidebar } from "./Sidebar";
import { AssistantMessage, UserMessage } from "./MessageView";
import { Logo } from "./Logo";
import { DEFAULT_MODE, MODES, type ModeId } from "@/lib/models";
import type { ChatEvent } from "@/lib/chat";
import {
  loadConversations,
  saveConversations,
  titleFrom,
  uid,
  type Conversation,
  type Message,
} from "@/lib/store";

const SUGGESTIONS = [
  "Me ajude a planejar minha semana",
  "Explique um conceito difícil de forma simples",
  "Revise este texto e deixe mais claro",
  "Ideias de projeto para o fim de semana",
];

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
}

function savedMode(): ModeId {
  try {
    const m = localStorage.getItem("agente.mode") as ModeId | null;
    if (m && m in MODES) return m;
  } catch {}
  return DEFAULT_MODE;
}

const isDesktop = () => window.matchMedia("(min-width: 768px)").matches;

// Rendered client-only (see ClientApp), so initializers may read browser state.
export function ChatApp() {
  const [conversations, setConversations] = useState<Conversation[]>(loadConversations);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [mode, setMode] = useState<ModeId>(savedMode);
  const [sidebarOpen, setSidebarOpen] = useState(isDesktop);
  const [streamingId, setStreamingId] = useState<string | null>(null);
  const [atBottom, setAtBottom] = useState(true);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!streamingId) saveConversations(conversations);
  }, [conversations, streamingId]);

  useEffect(() => {
    try {
      localStorage.setItem("agente.mode", mode);
    } catch {}
  }, [mode]);

  const active = conversations.find((c) => c.id === activeId) ?? null;
  const messages = useMemo(() => active?.messages ?? [], [active]);

  const updateMessage = useCallback(
    (convId: string, msgId: string, patch: (m: Message) => Message) => {
      setConversations((list) =>
        list.map((c) =>
          c.id !== convId
            ? c
            : { ...c, messages: c.messages.map((m) => (m.id === msgId ? patch(m) : m)) },
        ),
      );
    },
    [],
  );

  const runStream = useCallback(
    async (convId: string, history: Message[], assistantId: string, modeId: ModeId) => {
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setStreamingId(assistantId);

      // Buffer deltas and flush once per frame to keep rendering smooth.
      let thinking = "";
      let text = "";
      const startedAt = Date.now();
      let thinkingMs: number | undefined;
      let frame = 0;
      const flush = () => {
        frame = 0;
        updateMessage(convId, assistantId, (m) => ({ ...m, thinking: thinking || undefined, content: text, thinkingMs }));
      };
      const schedule = () => {
        if (!frame) frame = requestAnimationFrame(flush);
      };

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mode: modeId,
            messages: history
              .filter((m) => m.content && !m.error)
              .map((m) => ({ role: m.role, content: m.content })),
          }),
          signal: ctrl.signal,
        });
        if (!res.ok || !res.body) throw new Error(`Erro ${res.status} ao falar com o servidor`);

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let nl;
          while ((nl = buf.indexOf("\n")) >= 0) {
            const line = buf.slice(0, nl).trim();
            buf = buf.slice(nl + 1);
            if (!line) continue;
            const ev = JSON.parse(line) as ChatEvent;
            if (ev.t === "thinking") {
              thinking += ev.d;
            } else if (ev.t === "text") {
              if (thinking && thinkingMs === undefined) thinkingMs = Date.now() - startedAt;
              text += ev.d;
            } else if (ev.t === "error") {
              throw new Error(ev.message);
            } else if (ev.t === "done" && ev.stop === "max_tokens") {
              text += "\n\n_(resposta cortada no limite de tamanho)_";
            }
            schedule();
          }
        }
      } catch (err) {
        if (!ctrl.signal.aborted) {
          const msg = err instanceof Error ? err.message : String(err);
          updateMessage(convId, assistantId, (m) => ({ ...m, error: msg }));
        }
      } finally {
        if (frame) cancelAnimationFrame(frame);
        flush();
        setConversations((list) =>
          list.map((c) => (c.id === convId ? { ...c, updatedAt: Date.now() } : c)),
        );
        setStreamingId(null);
        abortRef.current = null;
      }
    },
    [updateMessage],
  );

  const send = (text: string) => {
    if (streamingId) return;
    const userMsg: Message = { id: uid(), role: "user", content: text };
    const assistantMsg: Message = { id: uid(), role: "assistant", content: "", mode };
    let convId = activeId;
    let history: Message[];

    if (!active) {
      convId = uid();
      const conv: Conversation = {
        id: convId,
        title: titleFrom(text),
        createdAt: Date.now(),
        updatedAt: Date.now(),
        messages: [userMsg, assistantMsg],
      };
      history = [userMsg];
      setConversations((list) => [conv, ...list]);
      setActiveId(convId);
    } else {
      history = [...active.messages, userMsg];
      setConversations((list) =>
        list.map((c) =>
          c.id === convId
            ? { ...c, updatedAt: Date.now(), messages: [...c.messages, userMsg, assistantMsg] }
            : c,
        ),
      );
    }
    setAtBottom(true);
    runStream(convId!, history, assistantMsg.id, mode);
  };

  const retry = () => {
    if (!active || streamingId) return;
    const msgs = active.messages;
    const lastUser = msgs.map((m) => m.role).lastIndexOf("user");
    if (lastUser < 0) return;
    const history = msgs.slice(0, lastUser + 1);
    const assistantMsg: Message = { id: uid(), role: "assistant", content: "", mode };
    setConversations((list) =>
      list.map((c) => (c.id === active.id ? { ...c, messages: [...history, assistantMsg] } : c)),
    );
    runStream(active.id, history, assistantMsg.id, mode);
  };

  const stop = () => abortRef.current?.abort();

  const newChat = () => {
    if (streamingId) stop();
    setActiveId(null);
    if (!isDesktop()) setSidebarOpen(false);
  };

  const select = (id: string) => {
    if (streamingId) stop();
    setActiveId(id);
    setAtBottom(true);
    if (!isDesktop()) setSidebarOpen(false);
  };

  const remove = (id: string) => {
    if (streamingId && id === activeId) stop();
    setConversations((list) => list.filter((c) => c.id !== id));
    if (id === activeId) setActiveId(null);
  };

  // Keep the view pinned to the bottom while streaming, unless the user scrolled up.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && atBottom) el.scrollTop = el.scrollHeight;
  }, [messages, atBottom]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  };

  const empty = messages.length === 0;
  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");

  return (
    <div className="flex h-dvh w-full">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onSelect={select}
        onNew={newChat}
        onDelete={remove}
      />

      <main className="relative flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-1 px-3">
          {!sidebarOpen && (
            <HeaderButton label="Abrir barra lateral" onClick={() => setSidebarOpen(true)}>
              <PanelLeftOpen size={19} />
            </HeaderButton>
          )}
          {!empty && (
            <div className="min-w-0 flex-1 truncate px-2 text-[14px] text-muted">{active?.title}</div>
          )}
          <div className="ml-auto">
            {(!sidebarOpen || !empty) && (
              <HeaderButton label="Nova conversa" onClick={newChat}>
                <PenSquare size={18} />
              </HeaderButton>
            )}
          </div>
        </header>

        {empty ? (
          <div className="flex flex-1 flex-col items-center justify-center px-4 pb-[12vh]">
            <div className="w-full max-w-[720px]">
              <div className="mb-8 flex flex-col items-center gap-4 text-center">
                <Logo size={52} />
                <h1 className="text-[28px] font-medium tracking-tight md:text-[32px]">
                  {greeting()}
                </h1>
              </div>
              <Composer
                big
                mode={mode}
                onModeChange={setMode}
                onSend={send}
                onStop={stop}
                busy={!!streamingId}
              />
              <div className="scroll-thin -mx-4 mt-4 flex gap-2 overflow-x-auto px-4 pb-1 md:mx-0 md:flex-wrap md:justify-center md:px-0">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => send(s)}
                    className="shrink-0 rounded-full border border-line px-4 py-2 text-[13.5px] text-muted transition-colors hover:bg-surface hover:text-fg"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <>
            <div ref={scrollRef} onScroll={onScroll} className="scroll-thin flex-1 overflow-y-auto">
              <div className="mx-auto w-full max-w-[760px] space-y-8 px-4 pt-4 pb-10 md:px-6">
                {messages.map((m) =>
                  m.role === "user" ? (
                    <UserMessage key={m.id} message={m} />
                  ) : (
                    <AssistantMessage
                      key={m.id}
                      message={m}
                      streaming={m.id === streamingId}
                      onRetry={m.id === lastAssistant?.id ? retry : undefined}
                    />
                  ),
                )}
              </div>
            </div>

            {!atBottom && (
              <button
                type="button"
                onClick={() => setAtBottom(true)}
                aria-label="Ir para o fim"
                className="absolute bottom-36 left-1/2 flex h-9 w-9 -translate-x-1/2 items-center justify-center rounded-full border border-line bg-surface-2 text-muted shadow-lg hover:text-fg"
              >
                <ArrowDown size={17} />
              </button>
            )}

            <div className="shrink-0 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] md:px-6">
              <div className="mx-auto w-full max-w-[760px]">
                <Composer
                  mode={mode}
                  onModeChange={setMode}
                  onSend={send}
                  onStop={stop}
                  busy={!!streamingId}
                />
                <p className="pt-2 text-center text-[11.5px] text-faint">
                  O assistente pode errar. Confira informações importantes.
                </p>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function HeaderButton({
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
      onClick={onClick}
      aria-label={label}
      title={label}
      className="flex h-9 w-9 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface hover:text-fg"
    >
      {children}
    </button>
  );
}
