import type { Brief } from "@/lib/api";

export function ActionList({ brief }: { brief: Brief }) {
  if (brief.recommended_actions.length === 0) {
    return <p className="text-sm text-muted">Nothing needs action this week.</p>;
  }

  return (
    <ul className="space-y-3">
      {brief.recommended_actions.map((action, i) => (
        <li key={i} className="flex gap-3">
          <span aria-hidden className="mt-px select-none font-mono text-accent">
            &rarr;
          </span>
          <span className="text-sm leading-snug text-ink">{action}</span>
        </li>
      ))}
    </ul>
  );
}
