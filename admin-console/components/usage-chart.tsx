"use client";
import { useId } from "react";
import { trendPoint, trendSegments } from "@/lib/usage-trend";

interface Props {
  title: string;
  unit: string;
  days: string[];
  values: (number | null)[];
  marker: "circle" | "square";
}

export function UsageChart({ title, unit, days, values, marker }: Props) {
  const id = useId();
  const maximum = Math.max(1, ...values.filter((value) => value !== null));
  const ticks = [...new Set([0, Math.ceil(maximum / 2), maximum])];
  const unknown = values.filter((value) => value === null).length;
  return <figure className="usage-chart">
    <figcaption>{marker === "circle" ? "●" : "■"} {title}</figcaption>
    <svg viewBox="0 0 560 190" role="img" aria-labelledby={`${id}-title`}
      aria-describedby={`${id}-description`}>
      <title id={`${id}-title`}>{title}</title>
      <desc id={`${id}-description`}>
        {unit} by day in UTC. Unknown values are gaps. Exact values are in the table below.
      </desc>
      <line className="chart-axis" x1="60" y1="140" x2="530" y2="140" />
      <line className="chart-axis" x1="60" y1="35" x2="60" y2="140" />
      {ticks.map((value) => {
        const y = trendPoint(0, value, days.length, maximum)[1];
        return <g key={value}>
          <line className="chart-grid" x1="60" y1={y} x2="530" y2={y} />
          <text className="chart-label" x="52" y={y + 4} textAnchor="end">
            {value.toLocaleString("en-US")}
          </text>
        </g>;
      })}
      {days.map((day, index) => {
        const selected = index === 0 || index === Math.floor(days.length / 2)
          || index === days.length - 1;
        if (!selected) return null;
        const x = trendPoint(index, 0, days.length, maximum)[0];
        const anchor = index === 0 ? "start" : index === days.length - 1 ? "end" : "middle";
        return <text className="chart-label" key={day} x={x} y="158" textAnchor={anchor}>
          {day.slice(5)}
        </text>;
      })}
      <text className="chart-label" x="290" y="182" textAnchor="middle">Day (UTC)</text>
      <text className="chart-label" x="14" y="90" textAnchor="middle"
        transform="rotate(-90 14 90)">{unit}</text>
      {trendSegments(values).map((points, index) =>
        <polyline className="chart-line" key={index} points={points} />)}
      {values.map((value, index) => {
        if (value === null) return null;
        const [x, y] = trendPoint(index, value, values.length, maximum);
        return marker === "circle"
          ? <circle className="chart-point" key={index} cx={x} cy={y} r="3" />
          : <rect className="chart-point" key={index} x={x - 3} y={y - 3}
            width="6" height="6" />;
      })}
    </svg>
    {unknown > 0 && <p className="warning">{unknown} day(s) with unknown totals · gaps in chart</p>}
  </figure>;
}
