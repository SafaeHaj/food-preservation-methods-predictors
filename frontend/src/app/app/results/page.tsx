"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { FlaskConical, Trophy, TrendingUp } from "lucide-react";

import { usePredictionStore } from "@/components/prediction-store";
import { PageBody, PageHeader, Reveal, SectionLabel } from "@/components/page-shell";
import { KpiCard } from "@/components/kpi-card";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { buttonVariants } from "@/components/ui/button";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Cell } from "recharts";

export default function ResultsPage() {
  const { lastPrediction } = usePredictionStore();

  if (!lastPrediction) {
    return (
      <PageBody>
        <PageHeader title="Results" description="Ranked candidate comparison from your most recent prediction." />
        <Card className="surface">
          <CardContent className="flex flex-col items-center gap-3 py-20 text-center">
            <div className="mb-1 flex h-14 w-14 items-center justify-center rounded-full border border-border bg-secondary/50">
              <FlaskConical className="h-6 w-6 text-muted-foreground" />
            </div>
            <p className="text-sm font-medium text-foreground">No prediction yet</p>
            <p className="max-w-sm text-xs leading-relaxed text-muted-foreground">Go to the Prediction page, fill in a control and at least one candidate, then click Predict.</p>
            <Link href="/app/prediction" className={buttonVariants({ className: "mt-3" })}>Go to Prediction</Link>
          </CardContent>
        </Card>
      </PageBody>
    );
  }

  const { control, candidates } = lastPrediction;
  const best = candidates[0];

  const comparisonData = [
    { name: "Control", value: control.prediction_days },
    ...candidates.map((c) => ({ name: c.candidate_name, value: c.predicted_candidate_shelf_life })),
  ];
  const improvementData = candidates.map((c) => ({ name: c.candidate_name, value: c.absolute_improvement_days }));

  return (
    <PageBody>
      <PageHeader title="Results" description="Ranked candidate comparison from your most recent prediction." />

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <KpiCard label="Control shelf life" numericValue={control.prediction_days} decimals={1} suffix=" d" icon={<FlaskConical className="h-4 w-4" />} animateIn />
        <KpiCard label="Best candidate" numericValue={best.predicted_candidate_shelf_life} decimals={1} suffix=" d" icon={<Trophy className="h-4 w-4" />} tone="success" animateIn sub={best.candidate_name} />
        <KpiCard
          label="Best improvement"
          numericValue={best.absolute_improvement_days}
          decimals={1}
          suffix=" d"
          icon={<TrendingUp className="h-4 w-4" />}
          tone="primary"
          animateIn
          sub={best.relative_improvement_pct !== null ? `${best.relative_improvement_pct >= 0 ? "+" : ""}${best.relative_improvement_pct.toFixed(1)}%` : "n/a"}
        />
      </div>

      <SectionLabel>Ranking</SectionLabel>
      <Card className="surface mb-8">
        <CardHeader><CardTitle className="text-sm">Ranked candidates</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Rank</TableHead>
                <TableHead>Candidate</TableHead>
                <TableHead>Model</TableHead>
                <TableHead className="text-right">Predicted (d)</TableHead>
                <TableHead className="text-right">Control (d)</TableHead>
                <TableHead className="text-right">Δ days</TableHead>
                <TableHead className="text-right">Δ %</TableHead>
                <TableHead className="text-right">Ratio</TableHead>
                <TableHead className="text-right">Lower 90%</TableHead>
                <TableHead className="text-right">Upper 90%</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {candidates.map((c, i) => (
                <motion.tr
                  key={c.candidate_name}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2, delay: i * 0.05 }}
                  className={i === 0 ? "bg-accent/50" : "row-interactive"}
                >
                  <TableCell>
                    <span
                      className={
                        "inline-flex h-5 w-5 items-center justify-center rounded-full font-mono text-[10px] tabular-nums " +
                        (i === 0
                          ? "bg-primary text-primary-foreground"
                          : "bg-secondary text-muted-foreground")
                      }
                    >
                      {c.rank}
                    </span>
                  </TableCell>
                  <TableCell className={i === 0 ? "font-semibold text-primary" : "font-medium"}>{c.candidate_name}</TableCell>
                  <TableCell className="text-muted-foreground">{c.model_label}</TableCell>
                  <TableCell className="text-right tabular-nums">{c.predicted_candidate_shelf_life.toFixed(1)}</TableCell>
                  <TableCell className="text-right tabular-nums">{c.predicted_control_shelf_life.toFixed(1)}</TableCell>
                  <TableCell className={"text-right tabular-nums " + (c.absolute_improvement_days >= 0 ? "text-success" : "text-destructive")}>
                    {c.absolute_improvement_days >= 0 ? "+" : ""}{c.absolute_improvement_days.toFixed(1)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{c.relative_improvement_pct !== null ? `${c.relative_improvement_pct >= 0 ? "+" : ""}${c.relative_improvement_pct.toFixed(1)}%` : "n/a"}</TableCell>
                  <TableCell className="text-right tabular-nums">{c.shelf_life_ratio !== null ? c.shelf_life_ratio.toFixed(2) : "n/a"}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">{c.lower_bound.toFixed(1)}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">{c.upper_bound.toFixed(1)}</TableCell>
                </motion.tr>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Reveal>
        <SectionLabel>Comparison</SectionLabel>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card className="surface">
            <CardHeader>
              <CardTitle className="text-sm">Control vs. candidates</CardTitle>
              <CardDescription>Predicted shelf life in days, control shown in grey.</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={270}>
                <BarChart data={comparisonData} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={{ stroke: "var(--border)" }} />
                  <YAxis tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} width={32} />
                  <Tooltip cursor={{ fill: "color-mix(in srgb, var(--primary) 5%, transparent)" }} contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid var(--border)", boxShadow: "var(--shadow-md)" }} />
                  <Bar dataKey="value" radius={[3, 3, 0, 0]} isAnimationActive animationDuration={650} animationEasing="ease-out">
                    {comparisonData.map((d, i) => <Cell key={i} fill={i === 0 ? "var(--muted-foreground)" : "var(--primary)"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
          <Card className="surface">
            <CardHeader>
              <CardTitle className="text-sm">Improvement vs. control (days)</CardTitle>
              <CardDescription>Green extends shelf life; red shortens it.</CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={270}>
                <BarChart data={improvementData} margin={{ top: 8, right: 16, left: -8, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={{ stroke: "var(--border)" }} />
                  <YAxis tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} width={32} />
                  <Tooltip cursor={{ fill: "color-mix(in srgb, var(--primary) 5%, transparent)" }} contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid var(--border)", boxShadow: "var(--shadow-md)" }} />
                  <Bar dataKey="value" radius={[3, 3, 0, 0]} isAnimationActive animationDuration={650} animationEasing="ease-out">
                    {improvementData.map((d, i) => <Cell key={i} fill={d.value >= 0 ? "var(--success)" : "var(--destructive)"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      </Reveal>
    </PageBody>
  );
}
