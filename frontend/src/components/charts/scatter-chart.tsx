"use client";

import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ReferenceLine } from "recharts";

export function ActualVsPredictedChart({ points, color = "var(--primary)" }: { points: { y_true: number; y_pred: number }[]; color?: string }) {
  const max = Math.max(1, ...points.map((p) => Math.max(p.y_true, p.y_pred))) * 1.05;
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ScatterChart margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
        <CartesianGrid stroke="var(--chart-grid)" />
        <XAxis type="number" dataKey="y_true" name="Actual" domain={[0, max]} tick={{ fontSize: 10, fill: "var(--chart-axis)" }} tickLine={false} axisLine={{ stroke: "var(--chart-grid)" }} label={{ value: "Actual (days)", position: "insideBottom", offset: -4, fontSize: 10, fill: "var(--chart-axis)" }} />
        <YAxis type="number" dataKey="y_pred" name="Predicted" domain={[0, max]} tick={{ fontSize: 10, fill: "var(--chart-axis)" }} tickLine={false} axisLine={false} label={{ value: "Predicted (days)", angle: -90, position: "insideLeft", fontSize: 10, fill: "var(--chart-axis)" }} />
        <ReferenceLine segment={[{ x: 0, y: 0 }, { x: max, y: max }]} stroke="var(--destructive)" strokeDasharray="4 4" />
        <Tooltip cursor={{ strokeDasharray: "3 3" }} contentStyle={{ fontSize: 12, borderRadius: 6, border: "1px solid var(--border)", background: "var(--popover)", color: "var(--popover-foreground)", boxShadow: "var(--shadow-md)" }} />
        <Scatter data={points} fill={color} fillOpacity={0.55} isAnimationActive animationDuration={500} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}
