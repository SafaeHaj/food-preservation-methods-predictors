"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function HistogramChart({ counts, edges, color = "var(--primary)" }: { counts: number[]; edges: number[]; color?: string }) {
  const data = counts.map((c, i) => ({
    bin: `${edges[i].toFixed(1)}`,
    count: c,
  }));
  return (
    <ResponsiveContainer width="100%" height={230}>
      <BarChart data={data} margin={{ top: 6, right: 10, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis
          dataKey="bin"
          tick={{ fontSize: 10, fill: "var(--chart-axis)" }}
          tickLine={false}
          axisLine={{ stroke: "var(--chart-grid)" }}
          interval={3}
        />
        <YAxis
          tick={{ fontSize: 10, fill: "var(--chart-axis)" }}
          tickLine={false}
          axisLine={false}
          width={44}
          allowDecimals={false}
          tickFormatter={compact}
        />
        <Tooltip
          cursor={{ fill: "color-mix(in srgb, var(--primary) 5%, transparent)" }}
          contentStyle={{ fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--popover)", color: "var(--popover-foreground)", boxShadow: "var(--shadow-md)" }}
          labelFormatter={(v) => `≥ ${v}`}
          formatter={(v) => [Number(v).toLocaleString(), "rows"]}
        />
        <Bar dataKey="count" fill={color} radius={[2, 2, 0, 0]} isAnimationActive animationDuration={600} animationEasing="ease-out" />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** 1200 -> "1.2k". Keeps the y-axis narrow without truncating to a bare "0". */
function compact(v: number) {
  if (Math.abs(v) >= 1000) return `${(v / 1000).toFixed(v % 1000 === 0 ? 0 : 1)}k`;
  return String(v);
}
