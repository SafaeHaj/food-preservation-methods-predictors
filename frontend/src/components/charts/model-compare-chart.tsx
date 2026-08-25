"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ModelSummary } from "@/lib/api";

export function ModelCompareChart({ models }: { models: ModelSummary[] }) {
  const data = models.map((m) => ({
    name: m.label.length > 14 ? m.label.slice(0, 13) + "…" : m.label,
    "Validation RMSE": Number(m.validation_rmse.toFixed(3)),
    "Test RMSE": Number(m.test_rmse.toFixed(3)),
  }));
  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 11, fill: "var(--chart-axis)" }} tickLine={false} axisLine={{ stroke: "var(--chart-grid)" }} />
        <YAxis tick={{ fontSize: 10, fill: "var(--chart-axis)" }} tickLine={false} axisLine={false} width={36} />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--popover)", color: "var(--popover-foreground)", boxShadow: "var(--shadow-md)" }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar dataKey="Validation RMSE" fill="var(--primary)" radius={[3, 3, 0, 0]} isAnimationActive animationDuration={550} />
        <Bar dataKey="Test RMSE" fill="var(--chart-2)" radius={[3, 3, 0, 0]} isAnimationActive animationDuration={550} />
      </BarChart>
    </ResponsiveContainer>
  );
}
