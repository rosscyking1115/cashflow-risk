import type { RunSummary } from "@/lib/api";

interface Props {
  runs: RunSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
}

function formatRunDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function HistoryPanel({ runs, activeId, onSelect }: Props) {
  if (runs.length === 0) return null;

  return (
    <section className="rounded-xl border border-hairline bg-surface p-5">
      <h2 className="font-mono text-xs uppercase tracking-[0.18em] text-muted">
        Saved analyses
      </h2>
      <ul className="mt-3 flex flex-wrap gap-2">
        {runs.map((run) => {
          const active = run.id === activeId;
          return (
            <li key={run.id}>
              <button
                onClick={() => onSelect(run.id)}
                aria-pressed={active}
                className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
                  active
                    ? "border-accent bg-accent-soft text-accent-ink"
                    : "border-hairline text-ink hover:bg-paper"
                }`}
              >
                <span className="font-mono text-xs text-muted">
                  {formatRunDate(run.created_at)}
                </span>
                <span className="tabular-nums">runway {run.runway_weeks}/13</span>
                <span
                  aria-hidden
                  className={`h-2 w-2 rounded-full ${run.has_shortfall ? "bg-high" : "bg-low"}`}
                />
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
