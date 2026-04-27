"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { RagDocumentFamily } from "@/lib/rag";

type RagCorpusTableProps = {
  documents: RagDocumentFamily[];
};

export default function RagCorpusTable({ documents }: RagCorpusTableProps) {
  const router = useRouter();
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const sorted = useMemo(
    () => [...documents].sort((a, b) => b.document_id.localeCompare(a.document_id)),
    [documents]
  );

  async function handleDelete(documentId: string) {
    setPendingDeleteId(documentId);
    setErrorMessage(null);

    try {
      const response = await fetch(`/api/rag/documents/${encodeURIComponent(documentId)}`, {
        method: "DELETE"
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { error?: string } | null;
        setErrorMessage(payload?.error ?? "Could not delete RAG document.");
        return;
      }

      router.refresh();
    } catch {
      setErrorMessage("Could not delete RAG document.");
    } finally {
      setPendingDeleteId(null);
    }
  }

  return (
    <section className="card" aria-label="RAG corpus">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Knowledge corpus</p>
          <h2>RAG documents</h2>
        </div>
        <span className="muted">{sorted.length} documents</span>
      </div>

      {sorted.length === 0 ? (
        <p className="muted">No RAG documents ingested yet.</p>
      ) : (
        <div className="rag-table-wrapper">
          <table className="rag-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Title</th>
                <th>Source</th>
                <th>Chunks</th>
                <th>Tags</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((document) => (
                <tr key={document.document_id}>
                  <td>{document.document_id}</td>
                  <td>{document.title}</td>
                  <td>{document.source}</td>
                  <td>{document.chunk_count}</td>
                  <td>{document.tags.join(", ") || "-"}</td>
                  <td>
                    <button
                      className="secondary-button rag-delete-button"
                      onClick={() => handleDelete(document.document_id)}
                      disabled={pendingDeleteId === document.document_id}
                    >
                      {pendingDeleteId === document.document_id ? "Deleting..." : "Delete"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {errorMessage ? <p className="error">{errorMessage}</p> : null}
    </section>
  );
}
