import { useId } from "react";
import { fmt } from "../theme.js";

// SVG line chart with optional gradient area fill and faint grid.
// series: [{ data, color, width?, dash?, opacity?, area? }]
export default function Chart({ series, height = 200, axis = true }) {
  const uid = useId();
  const W = 640;
  const H = height;
  const PT = 8;      // top padding
  const PB = 6;      // bottom padding
  const PL = 4;
  const PR = axis ? 46 : 4; // room for axis labels

  const all = series.flatMap((s) => s.data.filter((v) => v != null));
  if (all.length === 0) return null;
  const min = Math.min(...all);
  const max = Math.max(...all);
  const len = Math.max(...series.map((s) => s.data.length));

  const x = (i) => PL + (i / Math.max(len - 1, 1)) * (W - PL - PR);
  const y = (v) => H - PB - ((v - min) / (max - min || 1)) * (H - PT - PB);

  const linePath = (arr) =>
    arr
      .map((v, i) =>
        v == null ? null : `${i === 0 || arr[i - 1] == null ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`
      )
      .filter(Boolean)
      .join(" ");

  const areaPath = (arr) => {
    let first = -1;
    let last = -1;
    arr.forEach((v, i) => {
      if (v != null) {
        if (first < 0) first = i;
        last = i;
      }
    });
    if (first < 0) return "";
    return `${linePath(arr)} L${x(last).toFixed(1)},${H - PB} L${x(first).toFixed(1)},${H - PB} Z`;
  };

  const gridYs = [0.25, 0.5, 0.75].map((f) => PT + f * (H - PT - PB));
  const axisDigits = max >= 1000 ? 0 : 2;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
      <defs>
        {series.map(
          (s, k) =>
            s.area && (
              <linearGradient key={k} id={`${uid}-g${k}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity="0.22" />
                <stop offset="100%" stopColor={s.color} stopOpacity="0" />
              </linearGradient>
            )
        )}
      </defs>

      {gridYs.map((gy, k) => (
        <line key={k} x1={PL} y1={gy} x2={W - PR + (axis ? 4 : 0)} y2={gy}
          stroke="var(--border)" strokeWidth="1" />
      ))}

      {series.map(
        (s, k) =>
          s.area && <path key={`a${k}`} d={areaPath(s.data)} fill={`url(#${uid}-g${k})`} />
      )}

      {series.map((s, k) => (
        <path
          key={k}
          d={linePath(s.data)}
          fill="none"
          stroke={s.color}
          strokeWidth={s.width ?? 1.2}
          strokeDasharray={s.dash}
          strokeLinecap="round"
          strokeLinejoin="round"
          opacity={s.opacity ?? 0.92}
        />
      ))}

      {axis && (
        <>
          <text x={W - PR + 8} y={y(max) + 4} fill="var(--text-3)" fontSize="9.5"
            fontFamily="var(--mono)">{fmt(max, axisDigits)}</text>
          <text x={W - PR + 8} y={y(min) + 4} fill="var(--text-3)" fontSize="9.5"
            fontFamily="var(--mono)">{fmt(min, axisDigits)}</text>
        </>
      )}
    </svg>
  );
}
