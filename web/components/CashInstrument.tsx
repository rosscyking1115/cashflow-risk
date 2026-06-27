import type { Week } from "@/lib/api";
import { formatGBP, formatWeekStart } from "@/lib/format";

interface Props {
  weeks: Week[];
  minimumReserve: number;
  firstShortfallWeek: number | null;
}

// The signature element: a 13-week cash trajectory drawn as an instrument, with
// the minimum-reserve line and (on a shortfall) the breach week marked.
export function CashInstrument({ weeks, minimumReserve, firstShortfallWeek }: Props) {
  const W = 760;
  const H = 260;
  const padL = 18;
  const padR = 18;
  const padT = 26;
  const padB = 38;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const n = weeks.length;

  const values = weeks.map((w) => w.closing_balance);
  let yMin = Math.min(...values, minimumReserve);
  let yMax = Math.max(...values, minimumReserve);
  if (yMin === yMax) {
    yMin -= 1;
    yMax += 1;
  }
  const pad = (yMax - yMin) * 0.12;
  yMin -= pad;
  yMax += pad;

  const x = (i: number) => padL + (n <= 1 ? 0 : i * (plotW / (n - 1)));
  const y = (v: number) => padT + plotH * (1 - (v - yMin) / (yMax - yMin));
  const baseY = padT + plotH;

  const linePoints = weeks.map((w, i) => `${x(i)},${y(w.closing_balance)}`);
  const areaPath = `M ${x(0)},${baseY} L ${linePoints.join(" L ")} L ${x(n - 1)},${baseY} Z`;
  const reserveY = y(minimumReserve);
  const breachIdx = firstShortfallWeek != null ? firstShortfallWeek - 1 : null;
  const ticks = [0, 4, 8, 12].filter((i) => i < n);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-auto w-full"
      role="img"
      aria-label={`13-week cash projection. ${
        breachIdx != null
          ? `Reserve breached in week ${firstShortfallWeek}.`
          : "Stays above the minimum reserve throughout."
      }`}
    >
      <defs>
        <linearGradient id="cashGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.22" />
          <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* minimum reserve line */}
      <line
        x1={padL}
        x2={W - padR}
        y1={reserveY}
        y2={reserveY}
        stroke="var(--color-muted)"
        strokeWidth="1"
        strokeDasharray="2 4"
      />
      <text
        x={W - padR}
        y={reserveY - 6}
        textAnchor="end"
        fontSize="11"
        fill="var(--color-muted)"
        fontFamily="var(--font-mono)"
      >
        reserve {formatGBP(minimumReserve)}
      </text>

      <path d={areaPath} fill="url(#cashGrad)" />
      <polyline
        points={linePoints.join(" ")}
        fill="none"
        stroke="var(--color-accent)"
        strokeWidth="2.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />

      {/* breach marker */}
      {breachIdx != null && (
        <g>
          <line
            x1={x(breachIdx)}
            x2={x(breachIdx)}
            y1={padT - 8}
            y2={baseY}
            stroke="var(--color-high)"
            strokeWidth="1.5"
            strokeDasharray="3 3"
          />
          <circle cx={x(breachIdx)} cy={y(values[breachIdx])} r="4.5" fill="var(--color-high)" />
          <text
            x={x(breachIdx)}
            y={padT - 12}
            textAnchor="middle"
            fontSize="11"
            fontWeight="600"
            fill="var(--color-high)"
            fontFamily="var(--font-mono)"
          >
            week {firstShortfallWeek}
          </text>
        </g>
      )}

      {/* x ticks */}
      {ticks.map((i) => (
        <text
          key={i}
          x={x(i)}
          y={H - 14}
          textAnchor="middle"
          fontSize="11"
          fill="var(--color-muted)"
          fontFamily="var(--font-mono)"
        >
          {formatWeekStart(weeks[i].week_start)}
        </text>
      ))}
    </svg>
  );
}
