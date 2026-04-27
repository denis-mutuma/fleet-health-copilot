import { Suspense } from "react";
import ChatClient from "./chat-client";

export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <main className="container" aria-label="Incident operations chat loading">
          <section className="card">
            <p className="muted">Loading chat workspace...</p>
          </section>
        </main>
      }
    >
      <ChatClient />
    </Suspense>
  );
}
