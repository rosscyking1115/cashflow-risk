"use client";

import { useState } from "react";
import type { AuditEvent } from "@/lib/api";

interface Props {
  onLoad: () => Promise<AuditEvent[]>;
}

// Plain-English labels for audit actions; unknown actions fall back to the raw
// action string so new event types are never silently hidden.
function label(e: AuditEvent): string {
  const rows = e.detail?.rows;
  switch (e.action) {
    case "run.create":
      return typeof rows === "number" ? `Ran an analysis (${rows} rows)` : "Ran an analysis";
    case "run.export":
      return "Exported a run to Excel";
    case "account.export":
      return "Exported account data";
    case "member.invite":
      return `Invited a ${e.detail?.role ?? "member"}`;
    case "member.add":
      return `Added a ${e.detail?.role ?? "member"}`;
    case "business.rename":
      return "Renamed the business";
    default:
      return e.action;
  }
}

function when(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// The activity log for the active business — loaded on first expand, so the
// dashboard doesn't pay for it on every visit.
export function AuditTrail({ onLoad }: Props) {
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleToggle = async (open: boolean) => {
    if (!open || events !== null) return;
    try {
      setEvents(await onLoad());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the activity log.");
    }
  };

  return (
    <details
      className="mt-4 rounded-xl border border-hairline bg-surface p-4"
      onToggle={(e) => void handleToggle((e.target as HTMLDetailsElement).open)}
    >
      <summary className="cursor-pointer font-mono text-xs uppercase tracking-[0.18em] text-muted">
        Activity log
      </summary>
      <div className="mt-3">
        {error && <p className="text-sm text-high">{error}</p>}
        {!error && events === null && <p className="text-sm text-muted">Loading…</p>}
        {events !== null && events.length === 0 && (
          <p className="text-sm text-muted">No activity yet.</p>
        )}
        {events !== null && events.length > 0 && (
          <ul className="space-y-1.5">
            {[...events].reverse().map((e, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-x-3 text-sm">
                <span className="font-mono text-xs text-muted">{when(e.created_at)}</span>
                <span className="text-ink">{label(e)}</span>
                <span className="text-xs text-muted" title={e.actor_user_id}>
                  by {e.actor_user_id.slice(0, 12)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}
