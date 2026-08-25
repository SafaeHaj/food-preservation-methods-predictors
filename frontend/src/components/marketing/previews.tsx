"use client";

import { ArrowUpRight, Check } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * Static reconstructions of real screens, used only inside the landing page.
 *
 * The numbers below are the actual figures from the current training run
 * (artifacts/metrics.json) so the marketing page never shows invented results.
 * They are intentionally hardcoded rather than fetched: the landing page is
 * public and must render without an API session.
 */

const LEADERBOARD = [
  { model: "XGBoost", r2: "0.953", rmse: "17.61", best: true },
  { model: "LightGBM", r2: "0.953", rmse: "17.64", best: false },
  { model: "Random Forest", r2: "0.939", rmse: "20.12", best: false },
  { model: "Explainable Boosting Machine", r2: "0.937", rmse: "20.32", best: false },
];

export function LeaderboardPreview() {
  return (
    <div className="p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <p className="type-title text-foreground">Model leaderboard</p>
        <p className="type-caption text-subtle-foreground">Ranked by validation RMSE</p>
      </div>
      <table className="w-full">
        <thead>
          <tr className="border-b border-border">
            <th className="pb-1.5 text-left type-caption font-medium tracking-[0.04em] text-subtle-foreground uppercase">
              Model
            </th>
            <th className="pb-1.5 text-right type-caption font-medium tracking-[0.04em] text-subtle-foreground uppercase">
              Val R²
            </th>
            <th className="pb-1.5 text-right type-caption font-medium tracking-[0.04em] text-subtle-foreground uppercase">
              RMSE
            </th>
          </tr>
        </thead>
        <tbody>
          {LEADERBOARD.map((row) => (
            <tr key={row.model} className="border-b border-border last:border-0">
              <td className="py-2 text-[0.8125rem] text-foreground">
                <span className="flex items-center gap-1.5">
                  <span className="truncate">{row.model}</span>
                  {row.best && <Badge variant="accent">Best</Badge>}
                </span>
              </td>
              <td className="py-2 text-right text-[0.8125rem] numeral text-foreground">{row.r2}</td>
              <td className="py-2 text-right text-[0.8125rem] numeral text-muted-foreground">
                {row.rmse} d
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const CANDIDATES = [
  { name: "Nisin coating", days: 34.2, delta: 11.8, pct: 52.7, rank: 1 },
  { name: "Oregano essential oil", days: 29.6, delta: 7.2, pct: 32.1, rank: 2 },
  { name: "Natamycin dip", days: 26.1, delta: 3.7, pct: 16.5, rank: 3 },
];

export function ComparisonPreview() {
  const max = 40;
  return (
    <div className="p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <p className="type-title text-foreground">Treatment vs. control</p>
        <p className="type-caption text-subtle-foreground">Control · 22.4 d</p>
      </div>
      <div className="flex flex-col gap-2.5">
        {CANDIDATES.map((c) => (
          <div key={c.name} className="flex flex-col gap-1">
            <div className="flex items-baseline justify-between gap-3">
              <span className="truncate text-[0.8125rem] text-foreground">{c.name}</span>
              <span className="shrink-0 text-[0.8125rem] numeral text-foreground">
                {c.days.toFixed(1)} d
                <span className="ml-1.5 text-[0.6875rem] text-success">+{c.pct.toFixed(0)}%</span>
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${(c.days / max) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-1.5 border-t border-border pt-2.5">
        <Check className="size-3 text-success" />
        <span className="type-caption text-muted-foreground">
          90% conformal interval reported per prediction
        </span>
      </div>
    </div>
  );
}

const FACTORS = [
  { feature: "food_matrix", value: -23.9 },
  { feature: "storage_temperature_c", value: 1.14 },
  { feature: "indicator_type", value: 0.97 },
  { feature: "indicator_group", value: 0.7 },
  { feature: "primary_ingredient_family", value: 0.48 },
];

export function ExplainPreview() {
  const max = Math.max(...FACTORS.map((f) => Math.abs(f.value)));
  return (
    <div className="p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <p className="type-title text-foreground">Prediction factors</p>
        <p className="type-caption text-subtle-foreground">Local attribution</p>
      </div>
      <div className="flex flex-col gap-2">
        {FACTORS.map((f) => {
          const pct = (Math.abs(f.value) / max) * 50;
          const negative = f.value < 0;
          return (
            <div key={f.feature} className="flex items-center gap-2">
              <span className="w-[40%] shrink-0 truncate type-mono text-[0.6875rem] text-muted-foreground">
                {f.feature}
              </span>
              <div className="relative h-4 flex-1">
                <span className="absolute inset-y-0 left-1/2 w-px bg-border" />
                <span
                  className={cn(
                    "absolute inset-y-[3px] rounded-[2px]",
                    negative ? "bg-destructive/70" : "bg-success/70",
                  )}
                  style={
                    negative
                      ? { right: "50%", width: `${pct}%` }
                      : { left: "50%", width: `${pct}%` }
                  }
                />
              </div>
              <span className="w-12 shrink-0 text-right text-[0.6875rem] numeral text-muted-foreground">
                {f.value > 0 ? "+" : ""}
                {f.value.toFixed(1)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const CATEGORY_ERROR = [
  { category: "soft", mae: 5.0, n: 77, tone: "success" as const },
  { category: "semi_hard", mae: 78.3, n: 21, tone: "warning" as const },
  { category: "hard", mae: 207.1, n: 2, tone: "destructive" as const },
];

export function CategoryErrorPreview() {
  return (
    <div className="p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <p className="type-title text-foreground">Error by cheese category</p>
        <p className="type-caption text-subtle-foreground">External literature set</p>
      </div>
      <div className="flex flex-col gap-2">
        {CATEGORY_ERROR.map((row) => (
          <div
            key={row.category}
            className="flex items-center justify-between rounded-md border border-border px-2.5 py-2"
          >
            <div className="flex items-center gap-2">
              <span className="type-mono text-[0.75rem] text-foreground">{row.category}</span>
              <span className="type-caption text-subtle-foreground">n={row.n}</span>
            </div>
            <Badge variant={row.tone}>MAE {row.mae.toFixed(1)} d</Badge>
          </div>
        ))}
      </div>
      <p className="type-caption mt-3 flex items-start gap-1.5 border-t border-border pt-2.5 text-muted-foreground">
        <ArrowUpRight className="mt-px size-3 shrink-0" />
        Per-category breakdowns surface where a model should not be trusted.
      </p>
    </div>
  );
}
