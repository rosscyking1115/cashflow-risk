"use client";

import { useRef, useState } from "react";

interface Props {
  onDemo: () => void;
  onUpload: (file: File, openingBalance: number, minimumReserve: number) => void;
  busy: boolean;
  canUpload?: boolean;
}

export function ModeBar({ onDemo, onUpload, busy, canUpload = true }: Props) {
  const [opening, setOpening] = useState(10000);
  const [reserve, setReserve] = useState(6000);
  const fileRef = useRef<HTMLInputElement>(null);

  const numberField = (label: string, value: number, set: (n: number) => void) => (
    <label className="flex items-center gap-1.5 text-xs text-muted">
      {label}
      <input
        type="number"
        value={value}
        min={0}
        step={500}
        onChange={(e) => set(Number(e.target.value))}
        className="w-24 rounded-md border border-hairline bg-surface px-2 py-1 font-mono text-sm text-ink focus-visible:outline-2 focus-visible:outline-accent"
      />
    </label>
  );

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        onClick={onDemo}
        disabled={busy}
        className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50"
      >
        Demo data
      </button>
      <span className="text-xs text-muted">or upload</span>
      {numberField("Opening £", opening, setOpening)}
      {numberField("Reserve £", reserve, setReserve)}
      <input
        ref={fileRef}
        type="file"
        accept=".csv,text/csv"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onUpload(file, opening, reserve);
          e.target.value = "";
        }}
      />
      <button
        onClick={() => fileRef.current?.click()}
        disabled={busy || !canUpload}
        title={canUpload ? undefined : "Read-only access to this business"}
        className="rounded-md border border-accent px-3 py-1.5 text-sm font-medium text-accent transition-colors hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-50"
      >
        Invoices CSV
      </button>
    </div>
  );
}
