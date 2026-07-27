import type { Band, Risk } from "@/lib/api";
import { formatGBP, formatPercent } from "@/lib/format";

const bandStyle: Record<Band, string> = {
  high: "bg-high-soft text-high",
  medium: "bg-medium-soft text-medium",
  low: "bg-low-soft text-low",
};

const bandLabel: Record<Band, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

export function RiskTable({ risks }: { risks: Risk[] }) {
  if (risks.length === 0) {
    return <p className="text-sm text-muted">No open invoices to assess.</p>;
  }

  return (
    <ul className="divide-y divide-hairline">
      {risks.map((r) => (
        <li key={r.invoice_id} className="flex items-center justify-between gap-4 py-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm font-medium text-ink">{r.invoice_id}</span>
              <span
                className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${bandStyle[r.band]}`}
              >
                {bandLabel[r.band]}
              </span>
            </div>
            <p className="mt-0.5 truncate text-xs text-muted">{r.drivers[0]}</p>
          </div>
          <div className="shrink-0 text-right">
            <div className="font-mono text-sm font-semibold text-ink">
              {formatGBP(r.cash_at_risk)}
            </div>
            <div
              className="text-xs text-muted"
              title="A relative ranking score, not a calibrated probability. Use it to order which invoices to chase, not to read the odds."
            >
              risk {formatPercent(r.probability)}
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
