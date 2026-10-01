"use client";
import { useState } from "react";
import { formatMeasure, formatLatencyTick, numericValue } from "@/lib/number-format";
import type { AnalyticsRow } from "@/lib/console-contracts";
export function AnalyticsChart({
  rows,
  measure,
  bucket,
}: {
  rows: AnalyticsRow[];
  bucket: "hour" | "day";
  measure: "duration_p95" | "ttfb_p95" | "requests" | "error_rate" | "cache_hit_rate";
}) {
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const [logScale, setLogScale] = useState(false);
  const latency = measure.startsWith("duration") || measure.startsWith("ttfb");
  const logarithmic = latency && logScale;
  const recorded = [...new Set(rows.map((row) => row.bucket))].sort();
  const step = bucket === "hour" ? 3600000 : 86400000;
  const start = recorded[0] ? Date.parse(recorded[0]) : 0;
  const end = recorded.at(-1) ? Date.parse(recorded.at(-1)!) : -1;
  const times = Array.from(
    { length: Math.max(0, Math.floor((end - start) / step) + 1) },
    (_, index) => new Date(start + index * step).toISOString(),
  );
  const groups = [...new Set(rows.map((row) => row.group ?? "All attempts"))];
  const visible = rows.filter((row) => !hidden.has(row.group ?? "All attempts"));
  const max = visible.reduce(
    (maximum, row) => Math.max(maximum, numericValue(row[measure]) ?? 0),
    logarithmic ? 10 : 1,
  );
  const minimum = visible.reduce((smallest, row) => {
    const value = numericValue(row[measure]);
    return value !== null && value > 0 ? Math.min(smallest, value) : smallest;
  }, 1);
  const floor = 10 ** Math.floor(Math.log10(minimum));
  const ticks = logarithmic ? [floor] : [0, max / 2];
  if (logarithmic) {
    for (let tick = floor * 10; tick < max; tick *= 10) ticks.push(tick);
  }
  ticks.push(max);
  const points = new Map(
    rows.map((row) => [`${Date.parse(row.bucket)}:${row.group ?? "All attempts"}`, row]),
  );
  const x = (index: number) => 100 + (index * 510) / Math.max(1, times.length - 1);
  const y = (value: number) =>
    220 -
    (logarithmic
      ? (Math.log10(value) - Math.log10(floor)) / (Math.log10(max) - Math.log10(floor))
      : value / max) *
      180;
  const unit = measure.includes("rate") ? "%" : measure === "requests" ? "attempts" : "ms / s";
  return (
    <figure className="usage-chart">
      <figcaption>
        {measure.replaceAll("_", " ")} ({unit})
      </figcaption>
      {latency && (
        <label className="check">
          <input
            type="checkbox"
            checked={logScale}
            onChange={(event) => setLogScale(event.target.checked)}
          />
          Log scale
        </label>
      )}
      {logarithmic && (
        <p className="muted">
          Logarithmic latency axis: equal spacing means a tenfold increase. Zero durations appear as
          gaps.
        </p>
      )}
      <svg
        data-axis-maximum={max}
        data-axis-scale={logarithmic ? "log" : "linear"}
        role="img"
        aria-label={`${measure} by UTC time, table below`}
        viewBox="0 0 700 290"
      >
        <line className="chart-axis" x1="100" x2="630" y1="220" y2="220" />
        <line className="chart-axis" x1="100" x2="100" y1="40" y2="220" />
        {ticks.map((value) => (
          <g key={value}>
            <line className="chart-grid" x1="100" x2="630" y1={y(value)} y2={y(value)} />
            <text className="chart-label" x="92" textAnchor="end" y={y(value)}>
              {logarithmic ? formatLatencyTick(value) : formatMeasure(measure, value)}
            </text>
          </g>
        ))}
        <text className="chart-label" x="70" y="245">
          {times[0]?.slice(0, 10)}
        </text>
        <text className="chart-label" x="490" y="245">
          {times.at(-1)?.slice(0, 10)}
        </text>
        <text className="chart-label" x="250" y="270">
          Time (UTC)
        </text>
        {groups.map((group, index) => {
          if (hidden.has(group)) return null;
          let previous: { x: number; y: number } | undefined;
          const dots = times.map((time, i) => {
            const row = points.get(`${Date.parse(time)}:${group}`);
            const value = numericValue(row?.[measure]);
            if (value === null || (logarithmic && value <= 0)) {
              previous = undefined;
              return null;
            }
            const point = { x: x(i), y: y(Number(value)) };
            const old = previous;
            previous = point;
            return (
              <g key={time}>
                {old && (
                  <line
                    className={`chart-series series-${index % 6}`}
                    x1={old.x}
                    y1={old.y}
                    x2={point.x}
                    y2={point.y}
                  />
                )}
                <circle
                  className={`chart-series series-${index % 6}`}
                  cx={point.x}
                  cy={point.y}
                  r="2"
                >
                  <title>
                    {group}: {time} · {formatMeasure(measure, value)}
                  </title>
                </circle>
              </g>
            );
          });
          return <g key={group}>{dots}</g>;
        })}
      </svg>
      <ul className="chart-legend">
        {groups.map((group, index) => (
          <li className={`series-${index % 6}`} key={group}>
            <button
              type="button"
              className="secondary"
              aria-pressed={!hidden.has(group)}
              onClick={() =>
                setHidden((current) => {
                  const next = new Set(current);
                  if (next.has(group)) next.delete(group);
                  else next.add(group);
                  return next;
                })
              }
            >
              {group}
            </button>
          </li>
        ))}
      </ul>
      <p className="muted">Unknown values appear as gaps. Full values are in the table below.</p>
    </figure>
  );
}
