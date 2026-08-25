"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function BarHChart({ data, color = "var(--primary)", height = 240 }: { data: { label: string; value: number }[]; color?: string; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 0 }}>
        <CartesianGrid stroke="var(--chart-grid)" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 10, fill: "var(--chart-axis)" }} tickLine={false} axisLine={{ stroke: "var(--chart-grid)" }} />
        <YAxis dataKey="label" type="category" width={140} tick={{ fontSize: 11, fill: "var(--foreground)" }} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--popover)", color: "var(--popover-foreground)", boxShadow: "var(--shadow-md)" }} />
        <Bar dataKey="value" fill={color} radius={[0, 3, 3, 0]} isAnimationActive animationDuration={500} />
      </BarChart>
    </ResponsiveContainer>
  );
}
