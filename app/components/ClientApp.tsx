"use client";

import dynamic from "next/dynamic";

// The chat UI lives entirely on browser state (history, mode, viewport), so it skips prerendering.
const ChatApp = dynamic(() => import("./ChatApp").then((m) => m.ChatApp), {
  ssr: false,
  loading: () => <div className="h-dvh w-full bg-bg" />,
});

export function ClientApp() {
  return <ChatApp />;
}
