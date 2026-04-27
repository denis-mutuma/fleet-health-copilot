"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import type { ChatConversation, ChatMessage, ChatSession } from "@/lib/chat";

type ApiErrorResponse = { error?: string };

interface IncidentItem {
  incident_id: string;
  status: string;
  device_id: string;
  summary?: string;
  confidence_score?: number;
}

const QUICK_ACTIONS = [
  { label: "List incidents", prompt: "/list incidents" },
  { label: "Run simulation", prompt: "/simulate" },
  { label: "Checklist", prompt: "/checklist" },
  {
    label: "Report incident",
    prompt: "report incident metric=battery_temp_c device=robot-03 value=74.2 threshold=65"
  }
];

const EMPTY_STATE_SUGGESTIONS = [
  "What causes battery thermal drift?",
  "/list incidents",
  "/simulate",
  "report incident metric=battery_temp_c device=robot-03 value=74.2 threshold=65"
];

async function fetchJson<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    ...init,
    cache: "no-store",
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {})
    }
  });
  const payload = (await response.json().catch(() => null)) as T | ApiErrorResponse | null;
  if (!response.ok) {
    const message =
      payload &&
      typeof payload === "object" &&
      "error" in payload &&
      typeof payload.error === "string"
        ? payload.error
        : "Request failed.";
    throw new Error(message);
  }
  return payload as T;
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`incident-status-badge status-${status}`}>{status}</span>;
}

function IncidentListCard({
  incidents,
  onOpen
}: {
  incidents: IncidentItem[];
  onOpen: (id: string) => void;
}) {
  if (incidents.length === 0) return null;
  return (
    <ul className="chat-incident-list">
      {incidents.map((inc) => (
        <li key={inc.incident_id} className="chat-incident-item">
          <div className="chat-incident-header">
            <button type="button" className="chat-incident-id" onClick={() => onOpen(inc.incident_id)}>
              {inc.incident_id}
            </button>
            <StatusBadge status={inc.status} />
          </div>
          <p className="chat-incident-device">{inc.device_id}</p>
          {inc.summary ? <p className="chat-incident-summary">{inc.summary}</p> : null}
          {inc.confidence_score != null ? (
            <div className="chat-incident-confidence">
              <div
                className="chat-incident-confidence-bar"
                style={{ width: `${Math.round(inc.confidence_score * 100)}%` }}
              />
              <span>{Math.round(inc.confidence_score * 100)}% confidence</span>
            </div>
          ) : null}
          <div className="chat-incident-actions">
            <Link href={`/incidents/${encodeURIComponent(inc.incident_id)}`} className="secondary-button">
              View detail
            </Link>
            <button type="button" className="secondary-button" onClick={() => onOpen(inc.incident_id)}>
              Open
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}

function ChecklistCard({ checklist }: { checklist: string[] }) {
  const [checked, setChecked] = useState<Set<number>>(() => new Set());
  const toggle = (idx: number) =>
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  return (
    <ol className="chat-checklist">
      {checklist.map((step, idx) => (
        <li key={idx} className={`chat-checklist-item ${checked.has(idx) ? "done" : ""}`}>
          <label>
            <input type="checkbox" checked={checked.has(idx)} onChange={() => toggle(idx)} />
            <span>{step}</span>
          </label>
        </li>
      ))}
    </ol>
  );
}

function MessageCard({
  message,
  onOpenIncident
}: {
  message: ChatMessage;
  onOpenIncident: (id: string) => void;
}) {
  const citationsBySource = message.citations.reduce<Record<string, typeof message.citations>>(
    (groups, citation) => {
      const key = citation.source;
      if (!groups[key]) groups[key] = [];
      groups[key].push(citation);
      return groups;
    },
    {}
  );

  const payload = message.action_payload;
  const incidents = (payload?.incidents as IncidentItem[] | undefined) ?? [];
  const checklist = (payload?.checklist as string[] | undefined) ?? [];
  const recommendedActions = (payload?.recommended_actions as string[] | undefined) ?? [];
  const hypotheses = (payload?.root_cause_hypotheses as string[] | undefined) ?? [];

  return (
    <article className={`chat-message ${message.role === "assistant" ? "assistant" : "user"}`}>
      <div className="chat-message-meta">
        <strong>{message.role === "assistant" ? "Copilot" : "Operator"}</strong>
        <span>{new Date(message.created_at).toLocaleTimeString()}</span>
      </div>
      <p>{message.content}</p>

      {/* Incident list */}
      {message.action === "list_incidents" && incidents.length > 0 ? (
        <IncidentListCard incidents={incidents} onOpen={onOpenIncident} />
      ) : null}

      {/* Open incident detail */}
      {message.action === "open_incident" && message.action_status === "success" && payload ? (
        <div className="chat-action-card">
          {hypotheses.length > 0 ? (
            <div className="chat-action-section">
              <p className="chat-action-label">Root cause hypotheses</p>
              <ul className="chat-action-list">{hypotheses.map((h) => <li key={h}>{h}</li>)}</ul>
            </div>
          ) : null}
          {recommendedActions.length > 0 ? (
            <div className="chat-action-section">
              <p className="chat-action-label">Recommended actions</p>
              <ol className="chat-action-list">{recommendedActions.map((a) => <li key={a}>{a}</li>)}</ol>
            </div>
          ) : null}
          {payload.incident_id ? (
            <Link href={`/incidents/${encodeURIComponent(String(payload.incident_id))}`} className="secondary-button">
              View full incident
            </Link>
          ) : null}
        </div>
      ) : null}

      {/* Checklist */}
      {message.action === "checklist" && checklist.length > 0 ? (
        <ChecklistCard checklist={checklist} />
      ) : null}

      {/* Simulate / report success */}
      {(message.action === "simulate" || message.action === "report_incident") &&
        message.action_status === "success" && payload?.incident_id ? (
        <div className="chat-action-card">
          <p className="chat-action-label">Created incident</p>
          <div className="chat-incident-header">
            <span className="chat-incident-id">{String(payload.incident_id)}</span>
            {payload.status ? <StatusBadge status={String(payload.status)} /> : null}
          </div>
          <div className="chat-incident-actions" style={{ marginTop: 8 }}>
            <Link href={`/incidents/${encodeURIComponent(String(payload.incident_id))}`} className="secondary-button">
              View incident
            </Link>
          </div>
        </div>
      ) : null}

      {/* Status update */}
      {message.action === "update_status" && message.action_status === "success" && payload ? (
        <div className="chat-action-card">
          <p className="chat-action-label">Status updated</p>
          <div className="chat-incident-header">
            <span className="chat-incident-id">{String(payload.incident_id)}</span>
            {payload.status ? <StatusBadge status={String(payload.status)} /> : null}
          </div>
        </div>
      ) : null}

      {/* Error */}
      {message.action_status === "error" ? (
        <div className="chat-action-card error">
          <p className="chat-action">Action <code>{message.action}</code> failed.</p>
        </div>
      ) : null}

      {/* RAG citations */}
      {message.citations.length > 0 ? (
        <div className="chat-citations">
          <h4>Citations</h4>
          {Object.entries(citationsBySource).map(([source, entries]) => (
            <div key={`${message.message_id}-${source}`} className="citation-source-group">
              <p className="citation-source-title">{source}</p>
              <ul>
                {entries.map((citation) => (
                  <li key={`${message.message_id}-${citation.document_id}`}>
                    <div>
                      <strong>{citation.title}</strong>
                      <p className="muted">{citation.document_id}</p>
                      <p>{citation.excerpt}</p>
                    </div>
                    <span className="score-pill">{Math.round(citation.score * 100)}%</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function TypingIndicator() {
  return (
    <article className="chat-message assistant chat-typing-indicator" aria-label="Copilot is thinking">
      <div className="chat-message-meta"><strong>Copilot</strong></div>
      <div className="typing-dots"><span /><span /><span /></div>
    </article>
  );
}

function EmptyThreadState({ onSuggest }: { onSuggest: (prompt: string) => void }) {
  return (
    <div className="chat-empty-state">
      <p className="muted">Start a conversation. Try one of these:</p>
      <ul className="chat-suggestions">
        {EMPTY_STATE_SUGGESTIONS.map((s) => (
          <li key={s}>
            <button type="button" className="suggestion-chip" onClick={() => onSuggest(s)}>
              {s}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function sessionLabel(session: ChatSession, index: number): string {
  const date = new Date(session.created_at);
  const timeStr = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `Session ${index + 1} · ${timeStr}`;
}

export default function ChatClient() {
  const searchParams = useSearchParams();
  const incidentIdParam = searchParams.get("incidentId")?.trim() || "";

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>("");
  const [conversation, setConversation] = useState<ChatConversation | null>(null);
  const [prompt, setPrompt] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);

  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [conversation?.messages, loading]);

  async function loadSessions(selectId?: string) {
    const rows = await fetchJson<ChatSession[]>("/api/chat/sessions");
    setSessions(rows);

    const target = selectId || rows[0]?.session_id || "";
    setActiveSessionId(target);
    if (target) {
      const conv = await fetchJson<ChatConversation>(`/api/chat/sessions/${encodeURIComponent(target)}`);
      setConversation(conv);
    } else {
      setConversation(null);
    }
  }

  async function createSession(incidentId?: string) {
    setLoading(true);
    setError("");
    try {
      const created = await fetchJson<ChatSession>("/api/chat/sessions", {
        method: "POST",
        body: JSON.stringify({ incident_id: incidentId ?? null })
      });
      await loadSessions(created.session_id);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not create chat session.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      setLoading(true);
      setError("");
      try {
        if (incidentIdParam) {
          const created = await fetchJson<ChatSession>("/api/chat/sessions", {
            method: "POST",
            body: JSON.stringify({ incident_id: incidentIdParam })
          });
          if (!cancelled) {
            await loadSessions(created.session_id);
          }
          return;
        }

        await loadSessions();
      } catch (requestError) {
        if (!cancelled) {
          setError(requestError instanceof Error ? requestError.message : "Could not load chat.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    bootstrap().catch(() => null);
    return () => {
      cancelled = true;
    };
  }, [incidentIdParam]);

  async function sendPrompt(value: string) {
    if (!activeSessionId || !value.trim()) return;
    setLoading(true);
    setError("");
    try {
      const updated = await fetchJson<ChatConversation>(
        `/api/chat/sessions/${encodeURIComponent(activeSessionId)}/messages`,
        { method: "POST", body: JSON.stringify({ content: value.trim() }) }
      );
      setConversation(updated);
      await loadSessions(activeSessionId);
      setPrompt("");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Could not send chat message.");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      sendPrompt(prompt).catch(() => null);
    }
  }

  function handleOpenIncident(incidentId: string) {
    setPrompt(`/open ${incidentId}`);
  }

  const activeSession = sessions.find((s) => s.session_id === activeSessionId);
  const messages = conversation?.messages ?? [];

  return (
    <main className="container page-grid" aria-label="Incident operations chat">
      <header className="hero">
        <p className="eyebrow">Operator chat</p>
        <h1>Coordinate incidents through grounded conversation.</h1>
        <p>
          Ask evidence-backed questions, report incidents in natural language, inspect citations,
          and execute operational actions without leaving the thread.
        </p>
        <div className="report-metadata">
          <span>{sessions.length} sessions</span>
          <span>{activeSession?.incident_id ? `Scoped to ${activeSession.incident_id}` : "General ops mode"}</span>
          <span>Citations grouped by source</span>
        </div>
        <div className="actions">
          <Link href="/" className="secondary-button rag-link-button">
            Back to dashboard
          </Link>
          <Link href="/rag" className="secondary-button rag-link-button">
            Review knowledge corpus
          </Link>
        </div>
      </header>

      <section className="chat-layout card">
        <aside className="chat-sidebar">
          <div className="chat-sidebar-header">
            <h2>Sessions</h2>
            <button
              className="button secondary-button"
              type="button"
              onClick={() => createSession()}
              disabled={loading}
            >
              New
            </button>
          </div>
          {sessions.length === 0 && !loading ? (
            <p className="muted chat-sidebar-empty">No sessions yet.</p>
          ) : (
            <ul>
              {sessions.map((session, idx) => (
                <li key={session.session_id}>
                  <button
                    type="button"
                    className={`session-button ${session.session_id === activeSessionId ? "active" : ""}`}
                    onClick={() => {
                      setActiveSessionId(session.session_id);
                      fetchJson<ChatConversation>(`/api/chat/sessions/${encodeURIComponent(session.session_id)}`)
                        .then((conv) => setConversation(conv))
                        .catch((requestError) => {
                          setError(requestError instanceof Error ? requestError.message : "Failed to load conversation.");
                        });
                    }}
                  >
                    <strong>{sessionLabel(session, idx)}</strong>
                    <span className="muted">
                      {session.incident_id ? `Incident ${session.incident_id}` : "General ops"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <div className="chat-main">
          <div className="chat-quick-actions">
            {QUICK_ACTIONS.map((item) => (
              <button
                key={item.label}
                type="button"
                className="secondary-button"
                disabled={!activeSessionId || loading}
                onClick={() => setPrompt(item.prompt)}
              >
                {item.label}
              </button>
            ))}
          </div>

          {activeSession ? (
            <p className="muted chat-session-info">
              {activeSession.incident_id ? (
                <>
                  Scoped to incident{" "}
                  <Link href={`/incidents/${encodeURIComponent(activeSession.incident_id)}`}>
                    {activeSession.incident_id}
                  </Link>
                </>
              ) : (
                "General operations session"
              )}
            </p>
          ) : (
            <p className="muted">Create a session to start chatting.</p>
          )}

          <div className="chat-thread" ref={threadRef}>
            {messages.length === 0 && !loading && activeSessionId ? (
              <EmptyThreadState onSuggest={(s) => setPrompt(s)} />
            ) : null}
            {messages.map((message) => (
              <MessageCard key={message.message_id} message={message} onOpenIncident={handleOpenIncident} />
            ))}
            {loading ? <TypingIndicator /> : null}
          </div>

          <form
            className="chat-composer"
            onSubmit={(event) => {
              event.preventDefault();
              sendPrompt(prompt).catch(() => null);
            }}
          >
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              onKeyDown={handleKeyDown}
              rows={3}
              placeholder={
                activeSessionId
                  ? "Ask a question, report incident, or run /simulate… (Ctrl+Enter to send)"
                  : "Create a session to begin"
              }
              disabled={loading || !activeSessionId}
            />
            <button type="submit" className="button" disabled={loading || !activeSessionId || !prompt.trim()}>
              {loading ? "Working…" : "Send"}
            </button>
          </form>

          {error ? <p className="error">{error}</p> : null}
        </div>
      </section>
    </main>
  );
}
