"use client";

import { useState } from "react";
import type { Business } from "@/lib/api";

interface Props {
  businesses: Business[];
  activeId: string | null;
  onSwitch: (id: string) => void;
  onInvite: (email: string) => void;
}

function label(b: Business): string {
  return b.role === "owner" ? "My business" : `Client · ${b.business_id.slice(0, 8)}…`;
}

export function BusinessBar({ businesses, activeId, onSwitch, onInvite }: Props) {
  const [email, setEmail] = useState("");
  const active = businesses.find((b) => b.business_id === activeId);

  return (
    <div className="flex flex-wrap items-center gap-3">
      {businesses.length > 1 && (
        <label className="flex items-center gap-1.5 text-xs text-muted">
          Business
          <select
            value={activeId ?? ""}
            onChange={(e) => onSwitch(e.target.value)}
            className="rounded-md border border-hairline bg-surface px-2 py-1 text-sm text-ink focus-visible:outline-2 focus-visible:outline-accent"
          >
            {businesses.map((b) => (
              <option key={b.business_id} value={b.business_id}>
                {label(b)}
              </option>
            ))}
          </select>
        </label>
      )}

      {active?.role === "owner" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const value = email.trim();
            if (value) {
              onInvite(value);
              setEmail("");
            }
          }}
          className="flex items-center gap-1.5"
        >
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="accountant@firm.com"
            className="w-48 rounded-md border border-hairline bg-surface px-2 py-1 text-sm text-ink focus-visible:outline-2 focus-visible:outline-accent"
          />
          <button
            type="submit"
            className="rounded-md border border-accent px-2.5 py-1 text-sm font-medium text-accent transition-colors hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            Invite accountant
          </button>
        </form>
      )}
    </div>
  );
}
