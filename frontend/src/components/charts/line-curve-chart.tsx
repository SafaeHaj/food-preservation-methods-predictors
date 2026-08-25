"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function LineCurveChart({
  series,
  xLabel,
}: {
  series: { name: string; color: string; points: number[] }[];
  xLabel?: string;
}) {
  const length = Math.max(...series.map((s) => s.points.length));
  const data = Array.from({ length }, (_, i) => {
    const row: Record<string, number> = { x: i };
    for (const s of series) row[s.name] = s.points[i];
    return row;
  });
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 4, right: 16, left: -8, bottom: xLabel ? 16 : 0 }}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis
          dataKey="x"
          tick={{ fontSize: 10, fill: "var(--chart-axis)" }}
          tickLine={false}
          axisLine={{ stroke: "var(--chart-grid)" }}
          label={xLabel ? { value: xLabel, position: "insideBottom", offset: -8, fontSize: 10, fill: "var(--chart-axis)" } : undefined}
        />
        <YAxis tick={{ fontSize: 10, fill: "var(--chart-axis)" }} tickLine={false} axisLine={false} width={40} />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--popover)", color: "var(--popover-foreground)", boxShadow: "var(--shadow-md)" }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {series.map((s) => (
          <Line
            key={s.name}
            type="monotone"
            dataKey={s.name}
            stroke={s.color}
            strokeWidth={1.75}
            dot={false}
            isAnimationActive
            animationDuration={600}
            animationEasing="ease-out"
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
