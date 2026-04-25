"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function SimulateIncidentButton() {
  const router = useRouter();
  const [isPending, setIsPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleClick() {
    setIsPending(true);
    setErrorMessage(null);

    try {
      const response = await fetch("/api/incidents", { method: "POST" });
      if (!response.ok) {
        setErrorMessage("Could not trigger incident simulation.");
        return;
      }

      router.refresh();
    } catch {
      setErrorMessage("Could not trigger incident simulation.");
    } finally {
      setIsPending(false);
    }
  }

  return (
    <div className="actions">
      <button className="button" onClick={handleClick} disabled={isPending}>
        {isPending ? "Simulating..." : "Simulate thermal incident"}
      </button>
      {errorMessage ? <p className="error">{errorMessage}</p> : null}
    </div>
  );
}
