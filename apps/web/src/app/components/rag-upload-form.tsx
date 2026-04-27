"use client";

import { useState } from "react";

type UploadResult = {
  document_id: string;
  chunk_count: number;
  indexed_chunks: number;
  retrieval_backend: string;
  embedding_model: string;
  llm_model: string;
};

export default function RagUploadForm() {
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState("runbook");
  const [tags, setTags] = useState("battery,thermal");
  const [title, setTitle] = useState("");
  const [chunkSize, setChunkSize] = useState("1200");
  const [chunkOverlap, setChunkOverlap] = useState("200");
  const [isPending, setIsPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);
    setResult(null);

    if (!file) {
      setErrorMessage("Choose a document to upload.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file, file.name);
    formData.append("source", source);
    if (title.trim()) {
      formData.append("title", title.trim());
    }
    if (tags.trim()) {
      formData.append("tags", tags.trim());
    }
    if (chunkSize.trim()) {
      formData.append("chunk_size_chars", chunkSize.trim());
    }
    if (chunkOverlap.trim()) {
      formData.append("chunk_overlap_chars", chunkOverlap.trim());
    }

    setIsPending(true);
    try {
      const response = await fetch("/api/rag/upload", {
        method: "POST",
        body: formData
      });
      const payload = (await response.json().catch(() => null)) as
        | UploadResult
        | { error?: string }
        | null;

      if (!response.ok) {
        setErrorMessage(
          payload && typeof payload === "object" && "error" in payload && typeof payload.error === "string"
            ? payload.error
            : "Could not ingest document."
        );
        return;
      }

      setResult(payload as UploadResult);
      setFile(null);
    } catch {
      setErrorMessage("Could not ingest document.");
    } finally {
      setIsPending(false);
    }
  }

  return (
    <section className="upload-card" aria-label="RAG document upload">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Knowledge ingestion</p>
          <h2>Upload RAG document</h2>
        </div>
      </div>

      <form className="upload-form" onSubmit={handleSubmit}>
        <label className="upload-field">
          Source
          <select value={source} onChange={(event) => setSource(event.target.value)}>
            <option value="runbook">runbook</option>
            <option value="incident">incident</option>
            <option value="manual">manual</option>
            <option value="note">note</option>
          </select>
        </label>

        <label className="upload-field">
          Title override (optional)
          <input
            type="text"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Use filename when empty"
          />
        </label>

        <label className="upload-field">
          Tags
          <input
            type="text"
            value={tags}
            onChange={(event) => setTags(event.target.value)}
            placeholder="battery,thermal"
          />
        </label>

        <div className="upload-inline-fields">
          <label className="upload-field">
            Chunk size
            <input
              type="number"
              min={200}
              max={20000}
              value={chunkSize}
              onChange={(event) => setChunkSize(event.target.value)}
            />
          </label>
          <label className="upload-field">
            Overlap
            <input
              type="number"
              min={0}
              max={5000}
              value={chunkOverlap}
              onChange={(event) => setChunkOverlap(event.target.value)}
            />
          </label>
        </div>

        <label className="upload-field">
          Document file
          <input
            key={file ? file.name : "empty"}
            type="file"
            accept=".txt,.md,.markdown,.json,.jsonl,.csv,.log,.html,.htm,.pdf,.docx"
            onChange={(event) => {
              const selected = event.target.files?.[0] ?? null;
              setFile(selected);
            }}
          />
        </label>

        <button type="submit" className="button" disabled={isPending}>
          {isPending ? "Uploading..." : "Upload and index"}
        </button>
      </form>

      {errorMessage ? <p className="error">{errorMessage}</p> : null}

      {result ? (
        <p className="upload-result" role="status">
          Indexed {result.indexed_chunks}/{result.chunk_count} chunks for {result.document_id} using {result.embedding_model} and {result.llm_model} ({result.retrieval_backend}).
        </p>
      ) : null}
    </section>
  );
}
