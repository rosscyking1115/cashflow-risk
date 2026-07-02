// Typed client for the cashflow-risk API. Shapes mirror AnalysisResponse.

export type Band = "low" | "medium" | "high";

export interface Week {
  index: number;
  week_start: string;
  opening_balance: number;
  expected_inflow: number;
  expected_outflow: number;
  closing_balance: number;
}

export interface Risk {
  invoice_id: string;
  customer_id: string;
  probability: number;
  band: Band;
  cash_at_risk: number;
  drivers: string[];
}

export interface Brief {
  headline: string;
  runway_weeks: number;
  has_shortfall: boolean;
  first_shortfall_week: number | null;
  risk_signals: string[];
  recommended_actions: string[];
  disclaimer: string;
}

export interface Issue {
  row: number;
  message: string;
  field: string | null;
  severity: string;
}

export interface Analysis {
  business_id: string;
  as_of: string;
  minimum_reserve: number;
  weeks: Week[];
  top_risks: Risk[];
  brief: Brief;
  data_issues: Issue[];
  run_id: string | null;
}

import { clerkEnabled } from "@/lib/clerk";

declare global {
  interface Window {
    Clerk?: { session?: { getToken: () => Promise<string | null> } };
  }
}

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// The business the user is currently acting on (their own by default, or a
// client's business they've been granted access to). Sent as X-Business-Id.
let activeBusinessId: string | null = null;

export function setActiveBusiness(id: string | null): void {
  activeBusinessId = id;
}

function authHeaders(token: string): Record<string, string> {
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (activeBusinessId) headers["X-Business-Id"] = activeBusinessId;
  return headers;
}

// Free-tier servers sleep after idle and can take ~a minute to wake. Time out
// rather than hang forever, with a message that explains what's happening.
async function timedFetch(url: string, init?: RequestInit, ms = 90_000): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error("The server took too long to respond — it may be waking up. Please try again.");
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

async function asAnalysis(res: Response): Promise<Analysis> {
  if (!res.ok) {
    throw new Error(`The analysis service returned ${res.status}. Is the API running?`);
  }
  return (await res.json()) as Analysis;
}

export async function fetchDemo(): Promise<Analysis> {
  return asAnalysis(await timedFetch(`${BASE}/api/analyze/demo`, { method: "POST" }));
}

// Dev-only token. In production this is replaced by a real login against the IdP;
// here it keeps the dashboard usable when the API runs with dev tokens enabled.
let cachedToken: string | null = null;

async function devToken(): Promise<string> {
  if (cachedToken) return cachedToken;
  const res = await timedFetch(`${BASE}/api/auth/dev-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "demo@local", business_id: "demo-co" }),
  });
  if (!res.ok) {
    throw new Error(
      "Uploading needs sign-in. Start the API in dev mode (CASHFLOW_ENV=dev) to enable a dev token.",
    );
  }
  cachedToken = ((await res.json()) as { access_token: string }).access_token;
  return cachedToken;
}

async function authToken(): Promise<string> {
  if (clerkEnabled) {
    const token = await window.Clerk?.session?.getToken();
    if (!token) throw new Error("Please sign in to analyse your own invoices.");
    return token;
  }
  return devToken();
}

export async function uploadInvoices(
  file: File,
  openingBalance: number,
  minimumReserve: number,
): Promise<Analysis> {
  const token = await authToken();
  const form = new FormData();
  form.append("invoices", file);
  form.append("opening_balance", String(openingBalance));
  form.append("minimum_reserve", String(minimumReserve));
  return asAnalysis(
    await timedFetch(`${BASE}/api/analyze`, {
      method: "POST",
      body: form,
      headers: authHeaders(token),
    }),
  );
}

export interface RunSummary {
  id: string;
  as_of: string;
  runway_weeks: number;
  has_shortfall: boolean;
  created_at: string;
}

export async function fetchRuns(): Promise<RunSummary[]> {
  const token = await authToken();
  const res = await timedFetch(`${BASE}/api/runs`, {
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(`Could not load history (${res.status}).`);
  return (await res.json()) as RunSummary[];
}

export async function fetchRun(id: string): Promise<Analysis> {
  const token = await authToken();
  return asAnalysis(
    await timedFetch(`${BASE}/api/runs/${id}`, {
      headers: authHeaders(token),
    }),
  );
}

export async function downloadRunXlsx(id: string): Promise<void> {
  const token = await authToken();
  const res = await timedFetch(`${BASE}/api/runs/${id}/export.xlsx`, {
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(`Export failed (${res.status}).`);
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `cashflow-${id}.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// Everything the service holds for the signed-in user, as a JSON download
// (data portability / subject access — see docs/privacy-notice.md).
export async function downloadAccountExport(): Promise<void> {
  const token = await authToken();
  const res = await timedFetch(`${BASE}/api/account/export`, { headers: authHeaders(token) });
  if (!res.ok) throw new Error(`Export failed (${res.status}).`);
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = "cashflow-account-export.json";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// Erases all stored data for the signed-in user (right to erasure). The
// sign-in account itself (Clerk) is managed separately via the user menu.
export async function deleteAccountData(): Promise<void> {
  const token = await authToken();
  const res = await timedFetch(`${BASE}/api/account`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(`Delete failed (${res.status}).`);
}

export interface Business {
  business_id: string;
  role: string;
  name: string | null;
}

export async function fetchBusinesses(): Promise<Business[]> {
  const token = await authToken();
  const res = await timedFetch(`${BASE}/api/businesses`, { headers: authHeaders(token) });
  if (!res.ok) throw new Error(`Could not load businesses (${res.status}).`);
  return (await res.json()) as Business[];
}

export async function renameBusiness(businessId: string, name: string): Promise<void> {
  const token = await authToken();
  const res = await timedFetch(`${BASE}/api/businesses/${businessId}`, {
    method: "PUT",
    headers: { ...authHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(`Rename failed (${res.status}).`);
}

export async function inviteMember(
  businessId: string,
  email: string,
  role: string,
): Promise<void> {
  const token = await authToken();
  const res = await timedFetch(`${BASE}/api/businesses/${businessId}/invitations`, {
    method: "POST",
    headers: { ...authHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify({ email, role }),
  });
  if (!res.ok) throw new Error(`Invite failed (${res.status}).`);
}
