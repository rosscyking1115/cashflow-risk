"use client";

import { useEffect, useState } from "react";
import type { Business } from "@/lib/api";

interface Props {
  businesses: Business[];
  activeId: string | null;
  onSwitch: (id: string) => void;
  onInvite: (email: string) => void;
  onRename: (name: string) => void;
}

function label(b: Business): string {
  if (b.name) return b.name;
  return b.role === "owner" ? "My business" : `Client · ${b.business_id.slice(0, 8)}…`;
}

const fieldClass =
  "rounded-md border border-hairline bg-surface px-2 py-1 text-sm text-ink focus-visible:outline-2 focus-visible:outline-accent";
const buttonClass =
  "rounded-md border border-accent px-2.5 py-1 text-sm font-medium text-accent transition-colors hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent";

export function BusinessBar({ businesses, activeId, onSwitch, onInvite, onRename }: Props) {
  const active = businesses.find((b) => b.business_id === activeId);
  const [name, setName] = useState(active?.name ?? "");
  const [email, setEmail] = useState("");

  useEffect(() => {
    setName(active?.name ?? "");
  }, [active?.name, activeId]);

  return (
    <div className="flex flex-wrap items-center gap-3">
      {businesses.length > 1 && (
        <label className="flex items-center gap-1.5 text-xs text-muted">
          Business
          <select value={activeId ?? ""} onChange={(e) => onSwitch(e.target.value)} className={fieldClass}>
            {businesses.map((b) => (
              <option key={b.business_id} value={b.business_id}>
                {label(b)}
              </option>
            ))}
          </select>
        </label>
      )}

      {active?.role === "owner" && (
        <>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) onRename(name.trim());
            }}
            className="flex items-center gap-1.5"
          >
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Name your business"
              className={`${fieldClass} w-44`}
            />
            <button type="submit" className={buttonClass}>
              Save
            </button>
          </form>

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
              className={`${fieldClass} w-48`}
            />
            <button type="submit" className={buttonClass}>
              Invite accountant
            </button>
          </form>
        </>
      )}
    </div>
  );
}
