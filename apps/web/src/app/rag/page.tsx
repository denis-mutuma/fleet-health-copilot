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

  return (
    <main className="container" aria-label="RAG corpus management">
      <header className="hero">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Operations</p>
            <h1>RAG Corpus Management</h1>
          </div>
          <Link href="/" className="secondary-button rag-link-button">
            Back to dashboard
          </Link>
        </div>
        <p>
          Review and remove ingested knowledge documents used by retrieval and agent reasoning.
        </p>
      </header>

      {unavailable ? (
        <section className="card">
          <p className="error">
            Could not load RAG corpus because the orchestrator is unavailable.
          </p>
        </section>
      ) : (
        <RagCorpusTable documents={documents} />
      )}
    </main>
  );
}
