"use client";

import { memo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, ChevronRight, Copy, RotateCcw, AlertCircle } from "lucide-react";
import type { Message } from "@/lib/store";
import { MODES } from "@/lib/models";

const Markdown = memo(function Markdown({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noreferrer">
            {children}
          </a>
        ),
      }}
    >
      {text}
    </ReactMarkdown>
  );
});

export function UserMessage({ message }: { message: Message }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap rounded-3xl rounded-br-lg bg-surface-2 px-5 py-3 text-[15.5px] leading-relaxed">
        {message.content}
      </div>
    </div>
  );
}

export function AssistantMessage({
  message,
  streaming,
  onRetry,
}: {
  message: Message;
  streaming: boolean;
  onRetry?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const waiting = streaming && !message.content && !message.thinking;
  const thinkingLive = streaming && !message.content && !!message.thinking;

  return (
    <div className="group">
      {(message.thinking || thinkingLive) && (
        <ThinkingBlock
          text={message.thinking ?? ""}
          live={thinkingLive}
          ms={message.thinkingMs}
        />
      )}

      {waiting && <div className="shimmer text-[15px]">Pensando…</div>}

      {message.content && (
        <div className={`prose-chat ${streaming ? "caret" : ""}`}>
          <Markdown text={message.content} />
        </div>
      )}

      {message.error && (
        <div className="mt-3 flex items-start gap-2 rounded-2xl border border-danger/30 bg-danger/5 px-4 py-3 text-[14px] text-danger">
          <AlertCircle size={17} className="mt-0.5 shrink-0" />
          <span className="break-words">{message.error}</span>
        </div>
      )}

      {!streaming && (message.content || message.error) && (
        <div className="mt-2 flex items-center gap-1 text-faint opacity-100 transition-opacity md:opacity-0 md:group-hover:opacity-100 md:focus-within:opacity-100">
          {message.content && (
            <ActionButton
              label={copied ? "Copiado" : "Copiar"}
              onClick={() => {
                navigator.clipboard?.writeText(message.content).then(() => {
                  setCopied(true);
                  setTimeout(() => setCopied(false), 1500);
                });
              }}
            >
              {copied ? <Check size={15} /> : <Copy size={15} />}
            </ActionButton>
          )}
          {onRetry && (
            <ActionButton label="Gerar de novo" onClick={onRetry}>
              <RotateCcw size={15} />
            </ActionButton>
          )}
          {message.mode && (
            <span className="ml-1 text-[12px]">{MODES[message.mode]?.label}</span>
          )}
        </div>
      )}
    </div>
  );
}

function ThinkingBlock({ text, live, ms }: { text: string; live: boolean; ms?: number }) {
  const [open, setOpen] = useState(false);
  const secs = ms ? Math.max(1, Math.round(ms / 1000)) : null;
  const label = live ? "Pensando…" : secs ? `Pensou por ${secs}s` : "Raciocínio";

  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex items-center gap-1.5 rounded-full py-1 text-[14px] text-muted transition-colors hover:text-fg"
      >
        <ChevronRight size={15} className={`transition-transform ${open ? "rotate-90" : ""}`} />
        <span className={live ? "shimmer" : ""}>{label}</span>
      </button>
      {(open || live) && text && (
        <div
          className={`mt-1.5 ml-[7px] border-l border-line pl-4 text-[13.5px] leading-relaxed whitespace-pre-wrap text-faint ${
            live && !open ? "max-h-24 overflow-hidden [mask-image:linear-gradient(to_bottom,transparent,black_40%)]" : ""
          }`}
        >
          {live && !open ? text.slice(-400) : text}
        </div>
      )}
    </div>
  );
}

function ActionButton({
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
      className="flex h-8 w-8 items-center justify-center rounded-full transition-colors hover:bg-surface-2 hover:text-fg"
    >
      {children}
    </button>
  );
}
