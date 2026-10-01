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
  const recorded = [...new Set(rows.map((row) => row.bucket))].sort();
  const step = bucket === "hour" ? 3600000 : 86400000;
  const start = recorded[0] ? Date.parse(recorded[0]) : 0;
  const end = recorded.at(-1) ? Date.parse(recorded.at(-1)!) : -1;
  const times = Array.from(
    { length: Math.max(0, Math.floor((end - start) / step) + 1) },
    (_, index) => new Date(start + index * step).toISOString(),
  );
  const groups = [...new Set(rows.map((row) => row.group ?? "All attempts"))];
  const max = Math.max(1, ...rows.map((row) => Number(row[measure] ?? 0)));
  const x = (index: number) => 70 + (index * 540) / Math.max(1, times.length - 1);
  const y = (value: number) => 220 - (value * 180) / max;
  const unit = measure.includes("rate") ? "fraction" : measure === "requests" ? "attempts" : "ms";
  return (
    <figure className="usage-chart">
      <figcaption>
        {measure.replaceAll("_", " ")} ({unit})
      </figcaption>
      <svg role="img" aria-label={`${measure} by UTC time, table below`} viewBox="0 0 700 290">
        <line className="chart-axis" x1="70" x2="630" y1="220" y2="220" />
        <line className="chart-axis" x1="70" x2="70" y1="40" y2="220" />
        {[0, 0.5, 1].map((fraction) => (
          <g key={fraction}>
            <line
              className="chart-grid"
              x1="70"
              x2="630"
              y1={y(max * fraction)}
              y2={y(max * fraction)}
            />
            <text className="chart-label" x="8" y={y(max * fraction)}>
              {(max * fraction).toFixed(1)}
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
          let previous: { x: number; y: number } | undefined;
          const dots = times.map((time, i) => {
            const row = rows.find(
              (row) =>
                Date.parse(row.bucket) === Date.parse(time) &&
                (row.group ?? "All attempts") === group,
            );
            const value = row?.[measure];
            if (value == null) {
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
                    {group}: {time} · {value} {unit}
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
            {group}
          </li>
        ))}
      </ul>
      <p className="muted">Unknown values appear as gaps. Full values are in the table below.</p>
    </figure>
  );
}
