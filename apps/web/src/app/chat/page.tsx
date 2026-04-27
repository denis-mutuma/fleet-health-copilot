import { Suspense } from "react";
import ChatClient from "./chat-client";

export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <main className="container page-grid" aria-label="Incident operations chat loading">
          <header className="hero">
            <p className="eyebrow">Operator chat</p>
            <h1>Loading chat workspace...</h1>
            <p className="muted">Preparing sessions, citations, and action tools.</p>
          </header>
        </main>
      }
    >
      <ChatClient />
    </Suspense>
  );
}
