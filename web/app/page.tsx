"use client";

import { useCallback, useEffect, useState } from "react";
import {
  type Analysis,
  type Business,
  type RunSummary,
  deleteAccountData,
  downloadAccountExport,
  downloadRunXlsx,
  fetchAuditTrail,
  fetchBusinesses,
  fetchDemo,
  fetchRun,
  fetchRuns,
  inviteMember,
  renameBusiness,
  setActiveBusiness as selectBusiness,
  uploadInvoices,
} from "@/lib/api";
import { AccountControls } from "@/components/AccountControls";
import { ActionList } from "@/components/ActionList";
import { AuditTrail } from "@/components/AuditTrail";
import { AuthArea } from "@/components/AuthArea";
import { BusinessBar } from "@/components/BusinessBar";
import { CashInstrument } from "@/components/CashInstrument";
import { DataIssues } from "@/components/DataIssues";
import { HistoryPanel } from "@/components/HistoryPanel";
import { ModeBar } from "@/components/ModeBar";
import { RiskTable } from "@/components/RiskTable";
import { RunwayReadout } from "@/components/RunwayReadout";
import { clerkEnabled } from "@/lib/clerk";

export default function Page() {
  const [data, setData] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // null = history unavailable (signed out / demo); [] = signed in, none yet.
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [businesses, setBusinesses] = useState<Business[]>([]);
  const [activeBusiness, setActiveBusiness] = useState<string | null>(null);

  // Demo runs on generated data. The banner that says so is driven by this, so
  // it must be set by every path that replaces the analysis.
  const [isDemo, setIsDemo] = useState(true);

  const load = useCallback(async (request: Promise<Analysis>, demo: boolean) => {
    setIsDemo(demo);
    setLoading(true);
    setError(null);
    setSlow(false);
    const slowTimer = setTimeout(() => setSlow(true), 4000);
    try {
      setData(await request);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      clearTimeout(slowTimer);
      setSlow(false);
      setLoading(false);
    }
  }, []);

  const refreshHistory = useCallback(async () => {
    try {
      setRuns(await fetchRuns());
    } catch {
      setRuns(null); // not authenticated — hide the panel
    }
  }, []);

  const refreshBusinesses = useCallback(async () => {
    try {
      const list = await fetchBusinesses();
      setBusinesses(list);
      if (list.length > 0) {
        selectBusiness(list[0].business_id);
        setActiveBusiness(list[0].business_id);
      }
    } catch {
      setBusinesses([]); // signed out / demo
    }
  }, []);

  useEffect(() => {
    void (async () => {
      await load(fetchDemo(), true);
      await refreshBusinesses();
      await refreshHistory();
    })();
  }, [load, refreshBusinesses, refreshHistory]);

  const handleUpload = async (file: File, opening: number, reserve: number) => {
    await load(uploadInvoices(file, opening, reserve), false);
    await refreshHistory();
  };

  const handleSwitch = async (id: string) => {
    selectBusiness(id);
    setActiveBusiness(id);
    setNotice(null);
    const list = await fetchRuns().catch(() => [] as RunSummary[]);
    setRuns(list);
    if (list.length > 0) await load(fetchRun(list[0].id), false);
  };

  const handleInvite = async (email: string) => {
    if (!activeBusiness) return;
    try {
      await inviteMember(activeBusiness, email, "accountant");
      setNotice(`Invitation sent to ${email}. They'll get access when they sign in.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invite failed.");
    }
  };

  const handleRename = async (name: string) => {
    if (!activeBusiness) return;
    try {
      await renameBusiness(activeBusiness, name);
      await refreshBusinesses();
      setNotice(`Business renamed to “${name}”.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rename failed.");
    }
  };

  const handleExport = async (runId: string) => {
    try {
      await downloadRunXlsx(runId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed.");
    }
  };

  const handleAccountExport = async () => {
    try {
      await downloadAccountExport();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed.");
    }
  };

  const handleAccountDelete = async () => {
    try {
      await deleteAccountData();
      // everything server-side is gone; reset the UI to the signed-in blank slate
      setRuns([]);
      setNotice("All your stored data has been deleted.");
      await refreshBusinesses();
      await load(fetchDemo(), true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed.");
    }
  };

  const activeRole = businesses.find((b) => b.business_id === activeBusiness)?.role ?? "owner";
  const canUpload = activeRole === "owner";

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
            canUpload={canUpload}
            onDemo={() => void load(fetchDemo(), true)}
            onUpload={handleUpload}
          />
          {clerkEnabled && <AuthArea />}
        </div>
      </header>

      {clerkEnabled && businesses.length > 0 && (
        <div className="mt-4">
          <BusinessBar
            businesses={businesses}
            activeId={activeBusiness}
            onSwitch={handleSwitch}
            onInvite={handleInvite}
            onRename={handleRename}
          />
        </div>
      )}

      {isDemo && (
        <div className="mt-4 rounded-xl border border-hairline bg-surface p-4">
          <p className="text-sm text-ink">
            <span className="font-semibold">Synthetic demo data.</span> Every figure
            below — the runway, the shortfall, the amounts and the risk scores — is
            produced by a seeded generator. No real business, customer or payment is
            represented here.
          </p>
          <p className="mt-1.5 text-xs text-muted">
            Risk scores rank which invoices to chase first. They are not calibrated
            probabilities, and on this data no fitted model beat its rules
            counterpart once look-ahead was removed from the evaluation.
          </p>
        </div>
      )}

      {notice && (
        <div className="mt-4 rounded-xl border border-low/40 bg-low-soft p-4">
          <p className="text-sm text-low">{notice}</p>
        </div>
      )}

      {slow && (
        <div className="mt-6 rounded-xl border border-hairline bg-surface p-4">
          <p className="font-mono text-sm text-muted">
            Waking the server — the free tier sleeps after a while, so the first
            request can take up to a minute…
          </p>
        </div>
      )}

      {error && (
        <div className="mt-6 rounded-xl border border-high/30 bg-high-soft p-5">
          <p className="text-sm font-medium text-high">{error}</p>
          <button
            onClick={() => void load(fetchDemo(), true)}
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
          {runs && (
            <HistoryPanel
              runs={runs}
              activeId={data.run_id ?? null}
              onSelect={(id) => void load(fetchRun(id), false)}
            />
          )}

          {data.run_id && (
            <div className="flex justify-end">
              <button
                onClick={() => data.run_id && handleExport(data.run_id)}
                className="rounded-md border border-hairline px-3 py-1.5 text-sm font-medium text-ink transition-colors hover:bg-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              >
                Export to Excel
              </button>
            </div>
          )}

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

          {runs !== null && <AuditTrail onLoad={fetchAuditTrail} />}

          {runs !== null && (
            <AccountControls onExport={handleAccountExport} onDelete={handleAccountDelete} />
          )}
        </div>
      )}
    </main>
  );
}
