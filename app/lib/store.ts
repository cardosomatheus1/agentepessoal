import type { ModeId } from "./models";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  thinkingMs?: number;
  mode?: ModeId;
  error?: string;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: Message[];
}

// Phase 1 keeps history in the browser; it moves to DynamoDB with the Lambda.
const KEY = "agente.conversations.v1";

export function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Conversation[]) : [];
  } catch {
    return [];
  }
}

export function saveConversations(list: Conversation[]) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    // storage full or blocked: history just won't persist
  }
}

export function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export function titleFrom(text: string) {
  const t = text.replace(/\s+/g, " ").trim();
  return t.length > 48 ? t.slice(0, 47) + "…" : t || "Nova conversa";
}

export function groupByDate(list: Conversation[]) {
  const startOfToday = new Date().setHours(0, 0, 0, 0);
  const day = 86_400_000;
  const groups: { label: string; items: Conversation[] }[] = [
    { label: "Hoje", items: [] },
    { label: "Ontem", items: [] },
    { label: "Últimos 7 dias", items: [] },
    { label: "Mais antigas", items: [] },
  ];
  for (const c of [...list].sort((a, b) => b.updatedAt - a.updatedAt)) {
    if (c.updatedAt >= startOfToday) groups[0].items.push(c);
    else if (c.updatedAt >= startOfToday - day) groups[1].items.push(c);
    else if (c.updatedAt >= startOfToday - 7 * day) groups[2].items.push(c);
    else groups[3].items.push(c);
  }
  return groups.filter((g) => g.items.length);
}
