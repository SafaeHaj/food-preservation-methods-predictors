"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus, X, Loader2, Milk, Thermometer, PackageOpen, Activity, TestTube2,
  SlidersHorizontal, ClipboardList, Sparkles, TrendingUp, TrendingDown, Minus,
} from "lucide-react";
import { toast } from "sonner";

import { api, type SchemaData, type ClassDefinitions, type ClassificationResult } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type Lookup = Record<string, Record<string, unknown>>;

const NONE_INGREDIENT_DESCRIPTORS = { primary_ingredient_family: "none" };

const CLASS_BADGE_VARIANT: Record<string, "destructive" | "warning" | "success"> = {
  Low: "destructive",
  Medium: "warning",
  High: "success",
};
const CLASS_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  Low: TrendingDown,
  Medium: Minus,
  High: TrendingUp,
};

interface CandidateState {
  key: string;
  name: string;
  treatment_type: string;
  application_method: string;
  primary_ingredient_name: string;
  primary_concentration: number;
  primary_concentration_unit: string;
  primary_ingredient_family: string;
}

function mode(schema: SchemaData, col: string, fallback = "") {
  return schema.categorical_modes[col] ?? schema.categorical_options[col]?.[0] ?? fallback;
}
function median(schema: SchemaData, col: string) {
  return schema.numeric_ranges[col]?.median ?? 0;
}
function prettify(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  return String(v).replace(/_/g, " ");
}
function PrettyValue({ map }: { map?: Record<string, string> }) {
  return <SelectValue>{(v: unknown) => (map && typeof v === "string" && map[v]) || prettify(v)}</SelectValue>;
}

export function ClassificationForm({
  schema,
  matrixLookup,
  ingredientLookup,
  modelOptions,
  bestModel,
  classDefinitions,
}: {
  schema: SchemaData;
  matrixLookup: Lookup;
  ingredientLookup: Lookup;
  modelOptions: string[];
  bestModel: string;
  classDefinitions: ClassDefinitions;
}) {
  const [submitting, setSubmitting] = React.useState(false);
  const [results, setResults] = React.useState<ClassificationResult[] | null>(null);

  const [model, setModel] = React.useState(bestModel);

  const [foodMatrix, setFoodMatrix] = React.useState(schema.categorical_options.food_matrix[0]);
  const [matrixSource, setMatrixSource] = React.useState<Record<string, "default" | "user">>({});
  const [matrixValues, setMatrixValues] = React.useState<Record<string, unknown>>(() => matrixLookup[schema.categorical_options.food_matrix[0]] ?? {});

  const [storageTemp, setStorageTemp] = React.useState(median(schema, "storage_temperature_c"));
  const [packagingType, setPackagingType] = React.useState(mode(schema, "packaging_type"));
  const [indicatorGroup, setIndicatorGroup] = React.useState(mode(schema, "indicator_group"));
  const [indicatorType, setIndicatorType] = React.useState(mode(schema, "indicator_type"));
  const [indicatorUnit, setIndicatorUnit] = React.useState(mode(schema, "indicator_unit"));
  const [indicatorThreshold, setIndicatorThreshold] = React.useState(median(schema, "indicator_threshold"));
  const [initialIndicator, setInitialIndicator] = React.useState(median(schema, "initial_indicator_value"));

  const [pasteurizationApplied, setPasteurizationApplied] = React.useState(median(schema, "pasteurization_applied") >= 0.5);
  const [headspaceO2, setHeadspaceO2] = React.useState(median(schema, "headspace_oxygen_pct"));
  const [headspaceCO2, setHeadspaceCO2] = React.useState(median(schema, "headspace_co2_pct"));
  const [headspaceN2, setHeadspaceN2] = React.useState(median(schema, "headspace_n2_pct"));

  const makeCandidate = React.useCallback((n: number): CandidateState => ({
    key: `c${n}-${Date.now()}`,
    name: `Formulation ${n}`,
    treatment_type: schema.categorical_options.treatment_type.find((t) => t !== "none") ?? mode(schema, "treatment_type"),
    application_method: schema.categorical_options.application_method.find((t) => t !== "none") ?? mode(schema, "application_method"),
    primary_ingredient_name: schema.categorical_options.primary_ingredient_name.find((t) => t !== "none") ?? "none",
    primary_concentration: median(schema, "primary_concentration") || 1,
    primary_concentration_unit: schema.categorical_options.primary_concentration_unit.find((u) => u !== "none") ?? "none",
    primary_ingredient_family: "",
  }), [schema]);

  const [candidates, setCandidates] = React.useState<CandidateState[]>(() => {
    const first = makeCandidate(1);
    const lookup = ingredientLookup[first.primary_ingredient_name] ?? NONE_INGREDIENT_DESCRIPTORS;
    return [{ ...first, ...(lookup as object) } as CandidateState];
  });

  function updateCandidate(key: string, patch: Partial<CandidateState>) {
    setCandidates((prev) => prev.map((c) => (c.key === key ? { ...c, ...patch } : c)));
  }
  function onIngredientChange(key: string, ingredientName: string) {
    const lookup = (ingredientLookup[ingredientName] ?? NONE_INGREDIENT_DESCRIPTORS) as Partial<CandidateState>;
    updateCandidate(key, { primary_ingredient_name: ingredientName, ...lookup });
  }
  function onFoodMatrixChange(value: string) {
    setFoodMatrix(value);
    setMatrixValues(matrixLookup[value] ?? {});
    setMatrixSource({});
  }
  function resetMatrixDefaults() {
    setMatrixValues(matrixLookup[foodMatrix] ?? {});
    setMatrixSource({});
  }
  function addCandidate() {
    if (candidates.length >= 4) return;
    const n = candidates.length + 1;
    const next = makeCandidate(n);
    const lookup = ingredientLookup[next.primary_ingredient_name] ?? NONE_INGREDIENT_DESCRIPTORS;
    setCandidates((prev) => [...prev, { ...next, ...(lookup as object) } as CandidateState]);
  }
  function removeCandidate(key: string) {
    setCandidates((prev) => prev.filter((c) => c.key !== key));
  }

  const requiredMissing =
    !foodMatrix || storageTemp === null || !packagingType || !indicatorGroup || !indicatorType || !indicatorUnit ||
    indicatorThreshold === null || initialIndicator === null ||
    candidates.some((c) => !c.name.trim() || !c.treatment_type || !c.application_method || !c.primary_ingredient_name || !c.primary_ingredient_family || c.primary_concentration === null || !c.primary_concentration_unit);

  async function handleSubmit() {
    if (requiredMissing || submitting) return;
    setSubmitting(true);
    try {
      const shared = {
        food_matrix: foodMatrix,
        storage_temperature_c: storageTemp,
        packaging_type: packagingType,
        indicator_group: indicatorGroup,
        indicator_type: indicatorType,
        indicator_unit: indicatorUnit,
        indicator_threshold: indicatorThreshold,
        initial_indicator_value: initialIndicator,
        pasteurization_applied: pasteurizationApplied ? 1 : 0,
        headspace_oxygen_pct: headspaceO2,
        headspace_co2_pct: headspaceCO2,
        headspace_n2_pct: headspaceN2,
        ...matrixValues,
      };
      const result = await api.classificationPredict({
        model,
        shared,
        candidates: candidates.map((c) => ({
          name: c.name,
          treatment_type: c.treatment_type,
          application_method: c.application_method,
          primary_ingredient_name: c.primary_ingredient_name,
          primary_concentration: c.primary_concentration,
          primary_concentration_unit: c.primary_concentration_unit,
          primary_ingredient_family: c.primary_ingredient_family,
        })),
      });
      setResults(result.results);
      toast.success("Classification complete");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Classification failed");
    } finally {
      setSubmitting(false);
    }
  }

  const modelLabelOptions = modelOptions.map((m) => ({
    value: m,
    label: m === "random_forest" ? "Random Forest Classifier" : m === "xgboost" ? "XGBoost Classifier" : m,
  }));
  const modelLabelMap = Object.fromEntries(modelLabelOptions.map((o) => [o.value, o.label]));
  const YES_NO = { "1": "Yes", "0": "No" };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <div className="space-y-4">
        <Card className="surface">
          <CardHeader>
            <div className="flex items-center gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/12 text-primary">
                <ClipboardList className="size-4" />
              </span>
              <CardTitle className="text-sm">Classifier</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <Select value={model} onValueChange={(v) => v && setModel(v)}>
              <SelectTrigger className="w-full max-w-sm"><PrettyValue map={modelLabelMap} /></SelectTrigger>
              <SelectContent>
                {modelLabelOptions.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </CardContent>
        </Card>

        <Card className="surface">
          <CardHeader>
            <SectionHeading
              icon={Milk}
              number={1}
              title="Cheese profile"
              description="Food matrix selection auto-fills the descriptors below from dataset medians."
            />
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Food matrix" required>
              <Select value={foodMatrix} onValueChange={(v) => v && onFoodMatrixChange(v)}>
                <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
                <SelectContent>
                  {schema.categorical_options.food_matrix.map((o) => <SelectItem key={o} value={o}>{o.replace(/_/g, " ")}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            {["cheese_category", "matrix_ph", "matrix_water_activity", "matrix_moisture_pct", "matrix_fat_pct", "matrix_protein_pct", "matrix_salt_pct", "matrix_ripening_days"].map((col) => (
              <AutoField
                key={col}
                col={col}
                schema={schema}
                value={matrixValues[col]}
                source={matrixSource[col]}
                onChange={(v) => { setMatrixValues((prev) => ({ ...prev, [col]: v })); setMatrixSource((prev) => ({ ...prev, [col]: "user" })); }}
              />
            ))}
            <div className="col-span-full">
              <Button type="button" variant="outline" size="sm" onClick={resetMatrixDefaults}>Reset to dataset defaults</Button>
            </div>
          </CardContent>
        </Card>

        <Card className="surface">
          <CardHeader>
            <SectionHeading icon={Thermometer} number={2} title="Processing" />
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-3">
            <Field label="Pasteurization applied">
              <Select value={pasteurizationApplied ? "1" : "0"} onValueChange={(v) => setPasteurizationApplied(v === "1")}>
                <SelectTrigger className="w-full"><PrettyValue map={YES_NO} /></SelectTrigger>
                <SelectContent><SelectItem value="1">Yes</SelectItem><SelectItem value="0">No</SelectItem></SelectContent>
              </Select>
            </Field>
          </CardContent>
        </Card>

        <Card className="surface">
          <CardHeader>
            <SectionHeading icon={PackageOpen} number={3} title="Storage & packaging" />
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field label="Storage temperature (°C)" required>
              <Input type="number" value={storageTemp} onChange={(e) => setStorageTemp(Number(e.target.value))} />
            </Field>
            <Field label="Packaging type" required>
              <Select value={packagingType} onValueChange={(v) => v && setPackagingType(v)}>
                <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
                <SelectContent>
                  {schema.categorical_options.packaging_type.map((o) => <SelectItem key={o} value={o}>{o.replace(/_/g, " ")}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
          </CardContent>
        </Card>

        <Card className="surface">
          <CardHeader>
            <SectionHeading icon={Activity} number={4} title="Indicator" />
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-3">
            <Field label="Indicator group" required>
              <Select value={indicatorGroup} onValueChange={(v) => v && setIndicatorGroup(v)}>
                <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
                <SelectContent>
                  {schema.categorical_options.indicator_group.map((o) => <SelectItem key={o} value={o}>{o.replace(/_/g, " ")}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Indicator type" required>
              <Select value={indicatorType} onValueChange={(v) => v && setIndicatorType(v)}>
                <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
                <SelectContent>
                  {schema.categorical_options.indicator_type.map((o) => <SelectItem key={o} value={o}>{o.replace(/_/g, " ")}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <Field label="Indicator unit" required>
              <Select value={indicatorUnit} onValueChange={(v) => v && setIndicatorUnit(v)}>
                <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
                <SelectContent>
                  {schema.categorical_options.indicator_unit.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <Field label={`Threshold (${indicatorUnit})`} required>
              <Input type="number" value={indicatorThreshold} onChange={(e) => setIndicatorThreshold(Number(e.target.value))} />
            </Field>
            <Field label={`Initial value (${indicatorUnit})`} required>
              <Input type="number" value={initialIndicator} onChange={(e) => setInitialIndicator(Number(e.target.value))} />
            </Field>
          </CardContent>
        </Card>

        <Card className="surface">
          <CardHeader>
            <SectionHeading
              icon={TestTube2}
              number={5}
              title="Treatment formulations"
              description="Each formulation is classified independently -- add up to 4 to compare their efficacy tiers side by side."
            />
          </CardHeader>
          <CardContent className="space-y-4">
            <AnimatePresence initial={false}>
              {candidates.map((c, i) => (
                <motion.div
                  key={c.key}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.2 }}
                  className="rounded-lg border p-4"
                >
                  <div className="mb-3 flex items-center justify-between">
                    <span className="text-xs font-semibold text-muted-foreground">Formulation {i + 1}</span>
                    {i > 0 && (
                      <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => removeCandidate(c.key)}>
                        <X className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    <Field label="Name" required>
                      <Input value={c.name} onChange={(e) => updateCandidate(c.key, { name: e.target.value })} />
                    </Field>
                    <Field label="Treatment type" required>
                      <Select value={c.treatment_type} onValueChange={(v) => v && updateCandidate(c.key, { treatment_type: v })}>
                        <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
                        <SelectContent>
                          {schema.categorical_options.treatment_type.map((o) => <SelectItem key={o} value={o}>{o.replace(/_/g, " ")}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field label="Application method" required>
                      <Select value={c.application_method} onValueChange={(v) => v && updateCandidate(c.key, { application_method: v })}>
                        <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
                        <SelectContent>
                          {schema.categorical_options.application_method.map((o) => <SelectItem key={o} value={o}>{o.replace(/_/g, " ")}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field label="Ingredient" required>
                      <Select value={c.primary_ingredient_name} onValueChange={(v) => v && onIngredientChange(c.key, v)}>
                        <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
                        <SelectContent>
                          {schema.categorical_options.primary_ingredient_name.map((o) => <SelectItem key={o} value={o}>{o.replace(/_/g, " ")}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field label="Ingredient family" required>
                      <Select value={c.primary_ingredient_family} onValueChange={(v) => v && updateCandidate(c.key, { primary_ingredient_family: v })}>
                        <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
                        <SelectContent>
                          {schema.categorical_options.primary_ingredient_family.map((o) => <SelectItem key={o} value={o}>{o.replace(/_/g, " ")}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </Field>
                    <Field label="Concentration" required>
                      <div className="flex gap-2">
                        <Input type="number" value={c.primary_concentration} onChange={(e) => updateCandidate(c.key, { primary_concentration: Number(e.target.value) })} />
                        <Select value={c.primary_concentration_unit} onValueChange={(v) => v && updateCandidate(c.key, { primary_concentration_unit: v })}>
                          <SelectTrigger className="w-28"><PrettyValue /></SelectTrigger>
                          <SelectContent>
                            {schema.categorical_options.primary_concentration_unit.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </div>
                    </Field>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
            {candidates.length < 4 && (
              <Button type="button" variant="outline" size="sm" onClick={addCandidate}>
                <Plus className="h-3.5 w-3.5" /> Add formulation
              </Button>
            )}
          </CardContent>
        </Card>

        <Card className="surface">
          <CardHeader>
            <SectionHeading icon={SlidersHorizontal} number={6} title="Advanced parameters" />
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-3">
            <Field label="Headspace O₂ (%)">
              <Input type="number" value={headspaceO2} onChange={(e) => setHeadspaceO2(Number(e.target.value))} />
            </Field>
            <Field label="Headspace CO₂ (%)">
              <Input type="number" value={headspaceCO2} onChange={(e) => setHeadspaceCO2(Number(e.target.value))} />
            </Field>
            <Field label="Headspace N₂ (%)">
              <Input type="number" value={headspaceN2} onChange={(e) => setHeadspaceN2(Number(e.target.value))} />
            </Field>
          </CardContent>
        </Card>

        {results && (
          <Card className="surface">
            <CardHeader>
              <div className="flex items-center gap-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/12 text-primary">
                  <Sparkles className="size-4" />
                </span>
                <div>
                  <CardTitle className="text-sm">Classification results</CardTitle>
                  <CardDescription className="mt-0.5">
                    Low: below {classDefinitions.thresholds_pct.low_max.toFixed(1)}% improvement over a matched control · Medium: {classDefinitions.thresholds_pct.low_max.toFixed(1)}–{classDefinitions.thresholds_pct.medium_max.toFixed(1)}% · High: {classDefinitions.thresholds_pct.medium_max.toFixed(1)}%+
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {results.map((r) => {
                const Icon = CLASS_ICON[r.predicted_class] ?? Minus;
                const confidence = r.probabilities[r.predicted_class] ?? 0;
                return (
                  <div key={r.candidate_name} className="rounded-lg border p-4">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-semibold text-foreground">{r.candidate_name}</span>
                      <Badge variant={CLASS_BADGE_VARIANT[r.predicted_class] ?? "secondary"} className="h-6 gap-1 px-2 text-[11px]">
                        <Icon className="size-3" />
                        {r.predicted_class} efficacy
                      </Badge>
                    </div>
                    <div className="mb-2 text-xs text-muted-foreground">
                      {r.model_label} · {(confidence * 100).toFixed(0)}% confidence
                    </div>
                    <div className="space-y-1.5">
                      {classDefinitions.class_names.map((cls) => (
                        <div key={cls} className="flex items-center gap-2">
                          <span className="w-14 shrink-0 text-[11px] text-muted-foreground">{cls}</span>
                          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${((r.probabilities[cls] ?? 0) * 100).toFixed(1)}%`,
                                background: cls === "Low" ? "var(--destructive)" : cls === "Medium" ? "var(--warning)" : "var(--success)",
                              }}
                            />
                          </div>
                          <span className="w-9 shrink-0 text-right font-mono text-[11px] tabular-nums text-muted-foreground">
                            {((r.probabilities[cls] ?? 0) * 100).toFixed(0)}%
                          </span>
                        </div>
                      ))}
                    </div>
                    {r.warnings.length > 0 && (
                      <ul className="mt-2.5 space-y-0.5 border-t pt-2 text-[11px] text-warning">
                        {r.warnings.map((w, i) => <li key={i}>⚠ {w}</li>)}
                      </ul>
                    )}
                  </div>
                );
              })}
            </CardContent>
          </Card>
        )}
      </div>

      <div className="lg:sticky lg:top-[88px] lg:self-start">
        <div className="relative">
          <div
            aria-hidden
            className="pointer-events-none absolute -inset-4 -z-10 rounded-[1.75rem] bg-[radial-gradient(closest-side,color-mix(in_srgb,var(--primary)_18%,transparent),transparent)] opacity-80 blur-2xl"
          />
          <Card className="surface">
            <CardHeader>
              <CardTitle className="text-sm">Summary</CardTitle>
              <CardDescription>Review before classifying.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              <SummaryRow label="Food matrix" value={foodMatrix.replace(/_/g, " ")} />
              <SummaryRow label="Storage" value={`${storageTemp} °C · ${packagingType.replace(/_/g, " ")}`} />
              <SummaryRow label="Formulations" value={`${candidates.length} to classify`} />
              <AnimatePresence initial={false}>
                {candidates.map((c) => (
                  <motion.div
                    key={c.key}
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, height: 0, marginTop: 0 }}
                    transition={{ duration: 0.18 }}
                    className="rounded-md border-l-2 border-l-primary/50 bg-secondary/40 px-2.5 py-1.5"
                  >
                    <div className="font-medium text-foreground">{c.name}</div>
                    <div className="text-muted-foreground">{c.primary_ingredient_name.replace(/_/g, " ")} · {c.primary_concentration}{c.primary_concentration_unit}</div>
                  </motion.div>
                ))}
              </AnimatePresence>
              <Button
                size="lg"
                className="mt-2 w-full shadow-[0_8px_28px_-8px_color-mix(in_srgb,var(--primary)_65%,transparent)]"
                disabled={requiredMissing || submitting}
                onClick={handleSubmit}
              >
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {submitting ? "Classifying…" : "Classify"}
              </Button>
              {requiredMissing && <p className="text-[11px] text-destructive">Fill in every required (*) field to enable classification.</p>}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function SectionHeading({
  icon: Icon, number, title, description,
}: {
  icon: React.ComponentType<{ className?: string }>; number: number; title: string; description?: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="relative flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/12 text-primary">
        <Icon className="size-4" />
        <span className="absolute -right-1 -bottom-1 flex size-4 items-center justify-center rounded-full border border-border bg-card font-mono text-[0.5625rem] text-subtle-foreground">
          {number}
        </span>
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

function AutoField({ col, schema, value, source, onChange }: { col: string; schema: SchemaData; value: unknown; source?: "default" | "user"; onChange: (v: unknown) => void }) {
  const isCategorical = schema.categorical_columns.includes(col);
  const isBinary = schema.binary_columns.includes(col);
  const label = col.replace("matrix_", "").replace(/_/g, " ");

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <Label className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</Label>
        <Badge variant="outline" className="h-4 px-1.5 text-[9px]">{source === "user" ? "user value" : "dataset default"}</Badge>
      </div>
      {isCategorical ? (
        <Select value={String(value ?? "")} onValueChange={(v) => v && onChange(v)}>
          <SelectTrigger className="w-full"><PrettyValue /></SelectTrigger>
          <SelectContent>
            {schema.categorical_options[col]?.map((o) => <SelectItem key={o} value={o}>{o.replace(/_/g, " ")}</SelectItem>)}
          </SelectContent>
        </Select>
      ) : isBinary ? (
        <Select value={Number(value) >= 0.5 ? "1" : "0"} onValueChange={(v) => v && onChange(Number(v))}>
          <SelectTrigger className="w-full"><PrettyValue map={{ "1": "Yes", "0": "No" }} /></SelectTrigger>
          <SelectContent><SelectItem value="1">Yes</SelectItem><SelectItem value="0">No</SelectItem></SelectContent>
        </Select>
      ) : (
        <Input type="number" value={Number(value ?? 0)} onChange={(e) => onChange(Number(e.target.value))} />
      )}
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium text-foreground">{value}</span>
    </div>
  );
}
