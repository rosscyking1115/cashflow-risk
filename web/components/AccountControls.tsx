"use client";

import { useState } from "react";

interface Props {
  onExport: () => Promise<void>;
  onDelete: () => Promise<void>;
}

const linkClass =
  "text-sm text-muted underline decoration-hairline underline-offset-4 transition-colors hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

// Self-serve data rights (see docs/privacy-notice.md): export everything we
// hold as JSON, or erase it. Delete is two-step — arm, then confirm — so a
// stray click can never destroy an account.
export function AccountControls({ onExport, onDelete }: Props) {
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
      setArmed(false);
    }
  };

  return (
    <div className="mt-10 flex flex-wrap items-center gap-4 border-t border-hairline pt-4">
      <span className="text-xs uppercase tracking-wide text-muted">Your data</span>
      <button className={linkClass} disabled={busy} onClick={() => void run(onExport)}>
        Export my data (JSON)
      </button>
      {armed ? (
        <span className="flex items-center gap-2">
          <span className="text-sm text-high">Delete all stored data? This cannot be undone.</span>
          <button
            className="rounded-md border border-high bg-high-soft px-2.5 py-1 text-sm font-medium text-high focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-high"
            disabled={busy}
            onClick={() => void run(onDelete)}
          >
            Yes, delete everything
          </button>
          <button className={linkClass} disabled={busy} onClick={() => setArmed(false)}>
            Cancel
          </button>
        </span>
      ) : (
        <button className={linkClass} disabled={busy} onClick={() => setArmed(true)}>
          Delete my data…
        </button>
      )}
    </div>
  );
}
