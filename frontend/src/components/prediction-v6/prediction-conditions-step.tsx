"use client";

import * as React from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { ArrowLeft, Loader2, FlaskConical, Thermometer, PackageOpen, Activity, TestTube2, ShieldAlert } from "lucide-react";
import { toast } from "sonner";

import { usePredictionV6, NO_TREATMENT } from "@/components/prediction-v6-store";
import { titleCase, IMAGES } from "@/components/prediction-v6/cheese-search-step";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, type SchemaV6Data, type ModelTask } from "@/lib/api";

const EASE = [0.16, 1, 0.3, 1] as const;

function prettify(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  return String(v).replace(/_/g, " ");
}
function PrettyValue({ map }: { map?: Record<string, string> }) {
  return <SelectValue>{(v: unknown) => (map && typeof v === "string" && map[v]) || prettify(v)}</SelectValue>;
}

function SectionHeading({
  icon: Icon, number, title, description,
}: { icon: React.ComponentType<{ className?: string }>; number: number; title: string; description?: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="relative flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/12 text-primary">
        <Icon className="size-4" />
        <span className="absolute -right-1 -bottom-1 flex size-4 items-center justify-center rounded-full border border-border bg-card font-mono text-[0.5625rem] text-subtle-foreground">{number}</span>
      </span>
      <div className="min-w-0">
        <CardTitle className="text-sm">{title}</CardTitle>
        {description && <CardDescription className="mt-0.5">{description}</CardDescription>}
      </div>
    </div>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}{required && <span className="ml-0.5 text-destructive">*</span>}
      </Label>
      {children}
    </div>
  );
}

export function PredictionConditionsStep() {
  const { state, dispatch } = usePredictionV6();
  const reduce = useReducedMotion();
  const [submitting, setSubmitting] = React.useState(false);
  const { generalSchema, safetySchema, entry, physicalForm, baseCheeseName } = state;

  if (!generalSchema || !entry || !physicalForm || !baseCheeseName) return null;

  const activeSchema: SchemaV6Data = state.modelTask === "safety_endpoint" && safetySchema ? safetySchema : generalSchema;
  const isSafety = state.modelTask === "safety_endpoint";

  // indicator_type -> task comes from the backend's single authoritative
  // source (/api/v6/routing, wrapping SpecialistRegistry.indicator_task_map)
  // rather than being re-derived here by merging two schemas -- this is the
  // exact same lookup train_specialists.py's model_task column encodes, with
  // no second, independently-maintained copy of the same scientific rule.
  const [indicatorTaskMap, setIndicatorTaskMap] = React.useState<Record<string, ModelTask> | null>(null);
  React.useEffect(() => {
    let cancelled = false;
    api.routingV6(entry.cheeseCategory).then((r) => {
      if (!cancelled) setIndicatorTaskMap(r.indicator_task_map);
    });
    return () => { cancelled = true; };
  }, [entry.cheeseCategory]);

  function onIndicatorTypeChange(indicatorType: string) {
    if (!generalSchema) return;
    const task = indicatorTaskMap?.[indicatorType] ?? "general_shelf_life";
    const schemaForTask = task === "safety_endpoint" && safetySchema ? safetySchema : generalSchema;
    dispatch({
      type: "selectEndpoint",
      group: schemaForTask.categorical_modes.indicator_group ?? state.indicatorGroup ?? "",
      indicatorType,
      unit: schemaForTask.categorical_modes.indicator_unit ?? state.indicatorUnit ?? "",
      task,
    });
  }

  function onIngredientChange(name: string) {
    if (name === "none") {
      dispatch({ type: "setTreatment", patch: { ...NO_TREATMENT } });
      return;
    }
    dispatch({
      type: "setTreatment",
      patch: {
        ingredientName: name,
        treatmentType: activeSchema.categorical_options.treatment_type.find((t) => t !== "none") ?? "single_preservative",
        applicationMethod: activeSchema.categorical_options.application_method.find((t) => t !== "none") ?? "surface_spray",
        concentration: activeSchema.numeric_ranges.canonical_concentration_value?.median || 1,
        concentrationUnit: "ppm",
      },
    });
  }

  const requiredMissing =
    state.storageTemperatureC === null || !state.packagingType || !state.indicatorGroup || !state.indicatorType || !state.indicatorUnit ||
    state.indicatorThreshold === null || state.initialIndicatorValue === null;

  async function handleSubmit() {
    if (requiredMissing || submitting || !entry) return;
    setSubmitting(true);
    try {
      const shared = {
        food_matrix: state.foodMatrix,
        physical_form: physicalForm,
        storage_temperature_c: state.storageTemperatureC,
        packaging_type: state.packagingType,
        indicator_group: state.indicatorGroup,
        indicator_type: state.indicatorType,
        indicator_unit: state.indicatorUnit,
        indicator_threshold: state.indicatorThreshold,
        initial_indicator_value: state.initialIndicatorValue,
        pasteurization_applied: state.pasteurizationApplied ? 1 : 0,
        headspace_oxygen_pct: state.headspaceOxygenPct,
        headspace_co2_pct: state.headspaceCo2Pct,
        headspace_n2_pct: state.headspaceN2Pct,
        ...state.matrixValues,
      };
      const result = await api.predictV6({
        cheese_category: entry.cheeseCategory,
        model_task: state.modelTask,
        shared,
        candidates: [{
          name: state.treatment.ingredientName === "none" ? "Untreated" : "Treatment",
          treatment_type: state.treatment.treatmentType,
          application_method: state.treatment.applicationMethod,
          primary_ingredient_name: state.treatment.ingredientName,
          primary_concentration: state.treatment.concentration,
          primary_concentration_unit: state.treatment.concentrationUnit,
          primary_ingredient_family: state.treatment.ingredientFamily,
        }],
      });
      dispatch({ type: "setResult", result });
      toast.success("Prediction complete");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Prediction failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid gap-6 pt-8 pb-20 lg:grid-cols-[1fr_320px]">
      <div className="space-y-4">
        <button
          type="button"
          onClick={() => dispatch({ type: "goto", step: "profile" })}
          className="type-caption inline-flex items-center gap-1.5 text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" /> Edit profile
        </button>

        <Card className="surface">
          <CardHeader><SectionHeading icon={Thermometer} number={1} title="Cheese composition" description="Auto-filled from category typical values — adjust if known." /></CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {["matrix_ph", "matrix_water_activity", "matrix_moisture_pct", "matrix_fat_pct", "matrix_protein_pct", "matrix_salt_pct", "matrix_ripening_days"].map((col) => (
              <Field key={col} label={col.replace("matrix_", "").replace(/_/g, " ")}>
                <Input
                  type="number"
                  value={Number(state.matrixValues[col] ?? 0)}
                  onChange={(e) => dispatch({ type: "setCondition", patch: { matrixValues: { ...state.matrixValues, [col]: Number(e.target.value) } } })}
                />
              </Field>
            ))}
            <Field label="Pasteurization applied">
              <Select value={state.pasteurizationApplied ? "1" : "0"} onValueChange={(v) => dispatch({ type: "setCondition", patch: { pasteurizationApplied: v === "1" } })}>
                <SelectTrigger className="w-full"><PrettyValue map={{ "1": "Yes", "0": "No" }} /></SelectTrigger>
                <SelectContent><SelectItem value="1">Yes</SelectItem><SelectItem value="0">No</SelectItem></SelectContent>
              </Select>
            </Field>
          </CardContent>
        </Card>

        <Card className="surface">
          <CardHeader><SectionHeading icon={PackageOpen} number={2} title="Storage &amp; packaging" /></CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Storage temperature (°C)" required>
              <Input type="number" value={state.storageTemperatureC ?? 0} onChange={(e) => dispatch({ type: "setCondition", patch: { storageTemperatureC: Number(e.target.value) } })} />
            </Field>
            <Field label="Packaging type" required>
              <Select value={state.packagingType ?? ""} onValueChange={(v) => v && dispatch({ type: "setCondition", patch: { packagingType: v } })}>
                <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
                <SelectContent>{activeSchema.categorical_options.packaging_type.map((o) => <SelectItem key={o} value={o}>{prettify(o)}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Headspace O₂ (%)">
              <Input type="number" value={state.headspaceOxygenPct ?? 0} onChange={(e) => dispatch({ type: "setCondition", patch: { headspaceOxygenPct: Number(e.target.value) } })} />
            </Field>
            <Field label="Headspace CO₂ (%)">
              <Input type="number" value={state.headspaceCo2Pct ?? 0} onChange={(e) => dispatch({ type: "setCondition", patch: { headspaceCo2Pct: Number(e.target.value) } })} />
            </Field>
            <Field label="Headspace N₂ (%)">
              <Input type="number" value={state.headspaceN2Pct ?? 0} onChange={(e) => dispatch({ type: "setCondition", patch: { headspaceN2Pct: Number(e.target.value) } })} />
            </Field>
          </CardContent>
        </Card>

        <Card className="surface">
          <CardHeader><SectionHeading icon={Activity} number={3} title="Prediction endpoint" description="Selecting a pathogen indicator routes to our safety-focused prediction path." /></CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Indicator" required>
              <Select value={state.indicatorType ?? ""} onValueChange={(v) => v && onIndicatorTypeChange(v)}>
                <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
                <SelectContent>
                  {generalSchema.categorical_options.indicator_type.map((o) => <SelectItem key={o} value={o}>{prettify(o)}</SelectItem>)}
                  {safetySchema && safetySchema.categorical_options.indicator_type.map((o) => (
                    <SelectItem key={`safety-${o}`} value={o}>{prettify(o)} (safety)</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Indicator group" required>
              <Select value={state.indicatorGroup ?? ""} onValueChange={(v) => v && dispatch({ type: "setCondition", patch: { indicatorGroup: v } })}>
                <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
                <SelectContent>{activeSchema.categorical_options.indicator_group.map((o) => <SelectItem key={o} value={o}>{prettify(o)}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Indicator unit" required>
              <Select value={state.indicatorUnit ?? ""} onValueChange={(v) => v && dispatch({ type: "setCondition", patch: { indicatorUnit: v } })}>
                <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
                <SelectContent>{activeSchema.categorical_options.indicator_unit.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label={`Threshold (${state.indicatorUnit ?? ""})`} required>
              <Input type="number" value={state.indicatorThreshold ?? 0} onChange={(e) => dispatch({ type: "setCondition", patch: { indicatorThreshold: Number(e.target.value) } })} />
            </Field>
            <Field label={`Initial value (${state.indicatorUnit ?? ""})`} required>
              <Input type="number" value={state.initialIndicatorValue ?? 0} onChange={(e) => dispatch({ type: "setCondition", patch: { initialIndicatorValue: Number(e.target.value) } })} />
            </Field>
          </CardContent>
          <AnimatePresence>
            {isSafety && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.25, ease: EASE }}
                className="overflow-hidden px-(--card-spacing)"
              >
                <div className="mb-1 flex items-start gap-2.5 rounded-lg border border-warning/25 bg-warning/8 px-3.5 py-3">
                  <ShieldAlert className="mt-0.5 size-3.5 shrink-0 text-warning" />
                  <div>
                    <p className="type-caption font-semibold text-foreground">Safety-focused prediction, not a challenge-growth model</p>
                    <p className="type-caption mt-0.5 text-muted-foreground">
                      This endpoint predicts shelf life to a safety-related indicator threshold. It is not a dedicated microbial challenge-growth model: the training data has no challenge-study context (inoculum level, challenge design), so the model cannot simulate pathogen growth curves. Treat this as a safety-focused shelf-life estimate only.
                    </p>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </Card>

        <Card className="surface">
          <CardHeader><SectionHeading icon={TestTube2} number={4} title="Preservation treatment" description="Optional — leave as “None” to predict the untreated baseline only." /></CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Ingredient">
              <Select value={state.treatment.ingredientName} onValueChange={(v) => v && onIngredientChange(v)}>
                <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">None</SelectItem>
                  {activeSchema.categorical_options.primary_ingredient_name.filter((o) => o !== "none").map((o) => <SelectItem key={o} value={o}>{prettify(o)}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <AnimatePresence>
              {state.treatment.ingredientName !== "none" && (
                <>
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
                    <Field label="Application method" required>
                      <Select value={state.treatment.applicationMethod} onValueChange={(v) => v && dispatch({ type: "setTreatment", patch: { applicationMethod: v } })}>
                        <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
                        <SelectContent>{activeSchema.categorical_options.application_method.filter((o) => o !== "none").map((o) => <SelectItem key={o} value={o}>{prettify(o)}</SelectItem>)}</SelectContent>
                      </Select>
                    </Field>
                  </motion.div>
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
                    <Field label="Concentration" required>
                      <div className="flex gap-2">
                        <Input type="number" value={state.treatment.concentration} onChange={(e) => dispatch({ type: "setTreatment", patch: { concentration: Number(e.target.value) } })} />
                        <Input className="w-24" value={state.treatment.concentrationUnit} onChange={(e) => dispatch({ type: "setTreatment", patch: { concentrationUnit: e.target.value } })} placeholder="ppm" />
                      </div>
                    </Field>
                  </motion.div>
                </>
              )}
            </AnimatePresence>
          </CardContent>
        </Card>
      </div>

      <div className="lg:sticky lg:top-[88px] lg:self-start">
        <div className="relative">
          <div
            aria-hidden
            className="pointer-events-none absolute -inset-4 -z-10 rounded-[1.75rem] bg-[radial-gradient(closest-side,color-mix(in_srgb,var(--primary)_18%,transparent),transparent)] opacity-80 blur-2xl"
          />
          <Card className="surface">
            <CardHeader>
              <CardTitle className="text-sm">Prediction context</CardTitle>
              <CardDescription>Kept in view while you fill in conditions.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              <SummaryRow label={titleCase(baseCheeseName)} value={`${entry.cheeseCategory.replace("_", "-")} · ${prettify(physicalForm)}`} />
              <SummaryRow label="Storage" value={`${state.storageTemperatureC ?? "—"} °C`} />
              <SummaryRow label="Packaging" value={prettify(state.packagingType)} />
              <SummaryRow label="Endpoint" value={prettify(state.indicatorType)} />
              {isSafety && <Badge variant="warning" size="sm">Safety-focused</Badge>}
              <SummaryRow
                label="Treatment"
                value={state.treatment.ingredientName === "none" ? "None (baseline)" : `${prettify(state.treatment.ingredientName)} · ${state.treatment.concentration}${state.treatment.concentrationUnit}`}
              />
              <Button
                size="lg"
                className="mt-2 w-full shadow-[0_8px_28px_-8px_color-mix(in_srgb,var(--primary)_65%,transparent)]"
                disabled={requiredMissing || submitting}
                onClick={handleSubmit}
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" />}
                {submitting ? "Predicting…" : "Generate prediction"}
              </Button>
              {requiredMissing && <p className="text-[11px] text-destructive">Fill in every required (*) field to enable prediction.</p>}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-border/60 pb-2 last:border-0">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="text-right font-medium leading-snug text-foreground">{value}</span>
    </div>
  );
}
