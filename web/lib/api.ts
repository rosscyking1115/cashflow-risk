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
}

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function asAnalysis(res: Response): Promise<Analysis> {
  if (!res.ok) {
    throw new Error(`The analysis service returned ${res.status}. Is the API running?`);
  }
  return (await res.json()) as Analysis;
}

export async function fetchDemo(): Promise<Analysis> {
  return asAnalysis(await fetch(`${BASE}/api/analyze/demo`, { method: "POST" }));
}

// Dev-only token. In production this is replaced by a real login against the IdP;
// here it keeps the dashboard usable when the API runs with dev tokens enabled.
let cachedToken: string | null = null;

async function devToken(): Promise<string> {
  if (cachedToken) return cachedToken;
  const res = await fetch(`${BASE}/api/auth/dev-token`, {
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

export async function uploadInvoices(
  file: File,
  openingBalance: number,
  minimumReserve: number,
): Promise<Analysis> {
  const token = await devToken();
  const form = new FormData();
  form.append("invoices", file);
  form.append("opening_balance", String(openingBalance));
  form.append("minimum_reserve", String(minimumReserve));
  return asAnalysis(
    await fetch(`${BASE}/api/analyze`, {
      method: "POST",
      body: form,
      headers: { Authorization: `Bearer ${token}` },
    }),
  );
}
