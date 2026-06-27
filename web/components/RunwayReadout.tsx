import type { Brief } from "@/lib/api";

export function RunwayReadout({ brief }: { brief: Brief }) {
  const shortfall = brief.has_shortfall;

  return (
    <div>
      <p className="font-mono text-xs uppercase tracking-[0.18em] text-muted">
        Cash runway
      </p>
      <div className="mt-2 flex items-baseline gap-2">
        <span
          className={`font-display text-6xl font-bold tabular-nums ${
            shortfall ? "text-high" : "text-ink"
          }`}
        >
          {shortfall ? `Wk ${brief.first_shortfall_week}` : brief.runway_weeks}
        </span>
        {!shortfall && <span className="font-display text-2xl text-muted">/ 13</span>}
      </div>
      <p className="mt-1 text-sm text-muted">
        {shortfall
          ? "until your reserve is breached"
          : "weeks above your minimum reserve"}
      </p>
      <p className="mt-5 max-w-md text-lg leading-snug text-ink">{brief.headline}</p>
    </div>
  );
}
