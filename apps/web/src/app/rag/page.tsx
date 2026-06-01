import Link from "next/link";
import RagCorpusTable from "@/app/components/rag-corpus-table";
import { listRagDocumentFamilies, type RagDocumentFamily } from "@/lib/rag";

export const dynamic = "force-dynamic";

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
    <main className="container page-grid" aria-label="Knowledge inventory">
      <header className="hero">
        <p className="eyebrow">Knowledge inventory</p>
        <h1>Runbook corpus control</h1>
        <p>
          Track indexed runbooks, source coverage, and retrieval material used by operator chat.
        </p>
        <div className="report-metadata">
          <span>{documents.length} document families</span>
          <span>{totalChunks} indexed chunks</span>
          <span>{unavailable ? "Backend unavailable" : "Backend connected"}</span>
        </div>
        <div className="actions action-group">
          <Link href="/" className="secondary-button rag-link-button">
            Back to operations
          </Link>
          <Link href="/chat" className="secondary-button rag-link-button">
            Open comms
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
                  <p className="eyebrow">Corpus controls</p>
                  <h2>Runbook readiness checks</h2>
                </div>
              </div>
              <ol className="timeline-list">
                <li>Index current runbooks with source and tag metadata.</li>
                <li>Review chat citations after corpus changes.</li>
                <li>Remove stale or duplicated documents that dilute retrieval.</li>
              </ol>
            </section>
          </section>
        </>
      )}
    </main>
  );
}
