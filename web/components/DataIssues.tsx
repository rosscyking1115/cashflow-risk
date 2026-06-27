import type { Issue } from "@/lib/api";

export function DataIssues({ issues }: { issues: Issue[] }) {
  if (issues.length === 0) return null;

  const errors = issues.filter((i) => i.severity === "error").length;
  const warnings = issues.length - errors;

  return (
    <section className="rounded-xl border border-hairline bg-surface p-5">
      <h2 className="font-mono text-xs uppercase tracking-[0.18em] text-muted">
        Data quality &middot; {errors} error{errors !== 1 ? "s" : ""}, {warnings} warning
        {warnings !== 1 ? "s" : ""}
      </h2>
      <ul className="mt-3 space-y-1.5">
        {issues.slice(0, 8).map((issue, i) => (
          <li key={i} className="text-xs text-muted">
            <span className={issue.severity === "error" ? "text-high" : "text-medium"}>
              {issue.severity}
            </span>
            {issue.row > 0 ? ` · row ${issue.row}` : ""} &mdash; {issue.message}
          </li>
        ))}
      </ul>
    </section>
  );
}
