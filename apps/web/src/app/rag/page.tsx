import Link from "next/link";
import RagCorpusTable from "@/app/components/rag-corpus-table";
import { listRagDocumentFamilies, type RagDocumentFamily } from "@/lib/rag";

export default async function RagPage() {
  let documents: RagDocumentFamily[] = [];
  let unavailable = false;

  try {
    documents = await listRagDocumentFamilies();
  } catch {
    unavailable = true;
  }

  const totalChunks = documents.reduce((sum, item) => sum + item.chunk_count, 0);

  return (
    <main className="container page-grid" aria-label="RAG corpus management">
      <header className="hero">
        <p className="eyebrow">Knowledge workspace</p>
        <h1>Keep retrieval grounded and current.</h1>
        <p>
          Review ingested context, upload new operating knowledge, and keep the corpus that powers
          citations and agent reasoning healthy.
        </p>
        <div className="report-metadata">
          <span>{documents.length} document families</span>
          <span>{totalChunks} indexed chunks</span>
          <span>{unavailable ? "Backend unavailable" : "Backend connected"}</span>
        </div>
        <div className="actions">
          <Link href="/" className="secondary-button rag-link-button">
            Back to dashboard
          </Link>
          <Link href="/chat" className="secondary-button rag-link-button">
            Ask the copilot
          </Link>
        </div>
      </header>

      {unavailable ? (
        <section className="card">
          <p className="error">
            Could not load RAG corpus because the orchestrator is unavailable.
          </p>
        </section>
      ) : (
        <>
          <section className="panel-grid">
            <RagCorpusTable documents={documents} />
            <section className="card">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Coverage</p>
                  <h2>What good corpus hygiene looks like</h2>
                </div>
              </div>
              <ol className="timeline-list">
                <li>Keep current runbooks uploaded with source and tag metadata.</li>
                <li>Review citations in chat after changes to confirm retrieval quality.</li>
                <li>Remove stale or duplicated documents when they dilute relevance.</li>
              </ol>
            </section>
          </section>
        </>
      )}
    </main>
  );
}
