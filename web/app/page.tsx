"use client";

import { useCallback, useEffect, useState } from "react";
import { type Analysis, fetchDemo, uploadInvoices } from "@/lib/api";
import { ActionList } from "@/components/ActionList";
import { AuthArea } from "@/components/AuthArea";
import { CashInstrument } from "@/components/CashInstrument";
import { DataIssues } from "@/components/DataIssues";
import { ModeBar } from "@/components/ModeBar";
import { RiskTable } from "@/components/RiskTable";
import { RunwayReadout } from "@/components/RunwayReadout";
import { clerkEnabled } from "@/lib/clerk";

export default function Page() {
  const [data, setData] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (request: Promise<Analysis>) => {
    setLoading(true);
    setError(null);
    try {
      setData(await request);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(fetchDemo());
  }, [load]);

  return (
    <main className="mx-auto max-w-5xl px-5 py-8">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-hairline pb-5">
        <div>
          <h1 className="font-display text-xl font-bold tracking-tight text-ink">
            Cashflow Risk Intelligence
          </h1>
          <p className="mt-0.5 text-sm text-muted">
            Which late payments threaten your runway — and what to do this week.
          </p>
        </div>
        <div className="flex items-center gap-4">
          <ModeBar
            busy={loading}
            onDemo={() => load(fetchDemo())}
            onUpload={(file, opening, reserve) =>
              load(uploadInvoices(file, opening, reserve))
            }
          />
          {clerkEnabled && <AuthArea />}
        </div>
      </header>

      {error && (
        <div className="mt-6 rounded-xl border border-high/30 bg-high-soft p-5">
          <p className="text-sm font-medium text-high">{error}</p>
          <button
            onClick={() => load(fetchDemo())}
            className="mt-2 text-sm font-medium text-accent underline-offset-2 hover:underline"
          >
            Try the demo again
          </button>
        </div>
      )}

      {loading && !data && (
        <p className="mt-10 font-mono text-sm text-muted">Reading the ledger…</p>
      )}

      {data && (
        <div className={`mt-6 space-y-5 ${loading ? "opacity-60" : "rise"}`}>
          <section className="grid gap-8 rounded-xl border border-hairline bg-surface p-6 md:grid-cols-2 md:items-center">
            <RunwayReadout brief={data.brief} />
            <CashInstrument
              weeks={data.weeks}
              minimumReserve={data.minimum_reserve}
              firstShortfallWeek={data.brief.first_shortfall_week}
            />
          </section>

          <div className="grid gap-5 md:grid-cols-2">
            <section className="rounded-xl border border-hairline bg-surface p-6">
              <h2 className="font-mono text-xs uppercase tracking-[0.18em] text-muted">
                Top cash at risk
              </h2>
              <div className="mt-3">
                <RiskTable risks={data.top_risks.slice(0, 6)} />
              </div>
            </section>

            <section className="rounded-xl border border-hairline bg-surface p-6">
              <h2 className="font-mono text-xs uppercase tracking-[0.18em] text-muted">
                What to do this week
              </h2>
              <div className="mt-3">
                <ActionList brief={data.brief} />
              </div>
            </section>
          </div>

          <DataIssues issues={data.data_issues} />

          <footer className="border-t border-hairline pt-4 text-xs leading-relaxed text-muted">
            {data.brief.disclaimer}
          </footer>
        </div>
      )}
    </main>
  );
}
