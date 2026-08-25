"use client";

import * as React from "react";
import { motion, animate, useReducedMotion } from "framer-motion";
import { RotateCcw, ShieldAlert, Sparkles } from "lucide-react";

import { usePredictionV6 } from "@/components/prediction-v6-store";
import { titleCase, IMAGES } from "@/components/prediction-v6/cheese-search-step";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, type PredictionSupportLevel } from "@/lib/api";

const EASE = [0.16, 1, 0.3, 1] as const;

const SUPPORT_BADGE_VARIANT: Record<string, "success" | "info" | "warning" | "destructive"> = {
  strong: "success", moderate: "info", limited: "warning", experimental: "destructive", unsupported: "destructive",
};

/** How each headline prediction-support level is presented -- "supported"
 * is the only level that renders as a normal, unflagged result. Every other
 * level gets a visible banner ABOVE the hero number and a muted (not
 * destroyed) number treatment, so a low-support prediction can never look
 * identical to a fully-supported one (audit item #6). */
const SUPPORT_LEVEL_META: Record<PredictionSupportLevel, { label: string; tone: "warning" | "destructive"; headline: string }> = {
  supported: { label: "Supported", tone: "warning", headline: "" },
  weak_physical_form: { label: "Weak physical-form support", tone: "warning", headline: "This cheese/physical-form combination is not directly observed in training data." },
  extrapolation: { label: "Numerical extrapolation", tone: "warning", headline: "One or more inputs fall outside the range this specialist was trained on." },
  unsupported_categorical: { label: "Unsupported input", tone: "destructive", headline: "One or more selected values were never seen during training." },
  thin_sample: { label: "Limited training sample", tone: "warning", headline: "This specialist was trained on a small number of examples." },
};

function prettify(v: string | null): string {
  if (!v) return "—";
  return v.replace(/_/g, " ");
}

function useCountUp(target: number, decimals = 0) {
  const [value, setValue] = React.useState(0);
  const reduce = useReducedMotion();
  React.useEffect(() => {
    if (reduce) { setValue(target); return; }
    const controls = animate(0, target, { duration: 0.8, ease: EASE, onUpdate: setValue });
    return () => controls.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);
  return decimals > 0 ? value.toFixed(decimals) : Math.round(value).toLocaleString();
}

export function PredictionV6Result() {
  const { state, dispatch } = usePredictionV6();
  const [factors, setFactors] = React.useState<{ feature: string; contribution: number }[] | null>(null);

  const { result, entry, baseCheeseName, physicalForm } = state;

  React.useEffect(() => {
    if (!result || !entry) return;
    const row = result.candidates[0]?.row;
    if (!row) return;
    api.explainLocalV6({ cheese_category: entry.cheeseCategory, model_task: state.modelTask, row, top_k: 6 })
      .then((r) => setFactors(r.factors))
      .catch(() => setFactors(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result]);

  const treated = state.treatment.ingredientName !== "none";
  const candidate = result?.candidates[0];
  const displayed = candidate ? (treated ? candidate.predicted_candidate_shelf_life : candidate.predicted_control_shelf_life) : 0;
  // useCountUp must run unconditionally (Rules of Hooks) -- the early return
  // below happens after every hook call, not before.
  const days = useCountUp(displayed, 1);

  if (!result || !entry || !baseCheeseName || !candidate) return null;

  const isSafety = state.modelTask === "safety_endpoint";
  const image = IMAGES[baseCheeseName];
  const support = result.support;
  const isSupported = support.level === "supported";
  const meta = SUPPORT_LEVEL_META[support.level];

  // The specific, itemized reasons behind a non-"supported" level -- shown
  // in the banner so the user sees exactly what's unsupported, not just a
  // generic warning. Sourced entirely from the backend's own assessment,
  // never re-derived here.
  const supportReasons: string[] = [];
  if (support.model) {
    for (const u of support.model.unseen_categoricals) {
      supportReasons.push(`'${u.feature}' = '${u.value}' was never seen during training.`);
    }
    for (const e of support.model.extrapolations) {
      supportReasons.push(e.detail);
    }
  }
  if (support.physical_form && support.physical_form.level !== "strong") {
    supportReasons.push(support.physical_form.explanation);
  }
  if (support.routing.level === "thin_sample" && support.routing.reason) {
    supportReasons.push(support.routing.reason);
  }

  return (
    <div className="mx-auto max-w-3xl pt-8 pb-24">
      {!isSupported && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: EASE }}
          className={`mb-6 rounded-xl border px-5 py-4 ${meta.tone === "destructive" ? "border-destructive/30 bg-destructive/8" : "border-warning/30 bg-warning/8"}`}
        >
          <div className="flex items-start gap-2.5">
            <ShieldAlert className={`mt-0.5 size-4 shrink-0 ${meta.tone === "destructive" ? "text-destructive" : "text-warning"}`} />
            <div className="min-w-0">
              <p className={`type-ui font-semibold ${meta.tone === "destructive" ? "text-destructive" : "text-warning"}`}>{meta.label}</p>
              <p className="type-caption mt-0.5 text-muted-foreground">{meta.headline}</p>
              {supportReasons.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {supportReasons.map((r, i) => (
                    <li key={i} className="type-caption text-muted-foreground">&middot; {r}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </motion.div>
      )}

      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: EASE }} className="text-center">
        {isSafety && (
          <div className="mx-auto mb-4 flex w-fit items-center gap-1.5 rounded-full border border-warning/30 bg-warning/8 px-3 py-1">
            <ShieldAlert className="size-3 text-warning" />
            <span className="type-caption font-medium text-warning">Safety-focused estimate, not a challenge-growth model</span>
          </div>
        )}
        <p className="type-eyebrow text-subtle-foreground">Predicted shelf life</p>
        <div className={`numeral mt-2 text-6xl font-semibold tracking-tight sm:text-7xl ${isSupported ? "text-foreground" : "text-muted-foreground"}`}>
          {days} <span className="type-h2 text-muted-foreground">days</span>
        </div>
        {!isSupported && (
          <p className="type-caption mt-2 text-muted-foreground">This number is shown for reference only &mdash; see the notice above before relying on it.</p>
        )}
      </motion.div>

      {treated && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: EASE, delay: 0.12 }}
          className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-3"
        >
          <ResultCard label="Untreated baseline" value={`${candidate.predicted_control_shelf_life.toFixed(1)} d`} />
          <ResultCard
            label="Expected extension"
            value={`${candidate.absolute_improvement_days >= 0 ? "+" : ""}${candidate.absolute_improvement_days.toFixed(1)} d`}
            tone={candidate.absolute_improvement_days >= 0 ? "success" : "destructive"}
          />
          <ResultCard
            label="Relative improvement"
            value={candidate.relative_improvement_pct !== null ? `${candidate.relative_improvement_pct >= 0 ? "+" : ""}${candidate.relative_improvement_pct.toFixed(1)}%` : "n/a"}
            tone={candidate.relative_improvement_pct !== null && candidate.relative_improvement_pct >= 0 ? "success" : "destructive"}
          />
        </motion.div>
      )}

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: EASE, delay: 0.2 }} className="mt-8">
        <Card className="surface">
          <CardContent className="grid grid-cols-2 gap-4 py-4 sm:grid-cols-4">
            <MetaField label="Cheese profile" value={`${titleCase(baseCheeseName)} · ${entry.cheeseCategory.replace("_", "-")} · ${prettify(physicalForm)}`} />
            <MetaField label="Prediction endpoint" value={prettify(state.indicatorType)} />
            <MetaField label="Specialist" value={`${entry.cheeseCategory.replace("_", "-")} model`} />
            <div className="space-y-1">
              <div className="type-caption text-muted-foreground">Physical-form support</div>
              {support.physical_form && (
                <Badge variant={SUPPORT_BADGE_VARIANT[support.physical_form.level] ?? "outline"} size="sm">{support.physical_form.label}</Badge>
              )}
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {candidate.warnings.length > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }} className="mt-3 space-y-1.5">
          {candidate.warnings.map((w, i) => (
            <p key={i} className="type-caption text-muted-foreground">&middot; {w}</p>
          ))}
        </motion.div>
      )}

      {factors && factors.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: EASE, delay: 0.32 }} className="mt-8">
          <Card className="surface">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Sparkles className="size-3.5 text-primary" />
                <CardTitle className="text-sm">What influenced this prediction?</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-2.5">
              {factors.map((f) => (
                <div key={f.feature} className="flex items-center gap-3">
                  <span className="type-caption w-40 shrink-0 truncate text-muted-foreground">{prettify(f.feature)}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                    <div
                      className={`h-full rounded-full ${f.contribution >= 0 ? "bg-success" : "bg-destructive"}`}
                      style={{ width: `${Math.min(100, (Math.abs(f.contribution) / Math.max(...factors.map((x) => Math.abs(x.contribution)))) * 100)}%` }}
                    />
                  </div>
                  <span className={`type-caption w-16 shrink-0 text-right tabular-nums ${f.contribution >= 0 ? "text-success" : "text-destructive"}`}>
                    {f.contribution >= 0 ? "+" : ""}{f.contribution.toFixed(1)}d
                  </span>
                </div>
              ))}
            </CardContent>
          </Card>
        </motion.div>
      )}

      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }} className="mt-8 flex justify-center">
        <Button variant="outline" onClick={() => dispatch({ type: "reset" })}>
          <RotateCcw className="size-3.5" /> Evaluate another cheese
        </Button>
      </motion.div>
    </div>
  );
}

function ResultCard({ label, value, tone }: { label: string; value: string; tone?: "success" | "destructive" }) {
  return (
    <div className="surface-interactive flex flex-col gap-1.5 p-4 text-center">
      <span className="type-eyebrow text-subtle-foreground">{label}</span>
      <span className={`numeral text-2xl font-semibold ${tone === "success" ? "text-success" : tone === "destructive" ? "text-destructive" : "text-foreground"}`}>
        {value}
      </span>
    </div>
  );
}

function MetaField({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <div className="type-caption text-muted-foreground">{label}</div>
      <div className="type-caption font-medium text-foreground">{value}</div>
    </div>
  );
}
