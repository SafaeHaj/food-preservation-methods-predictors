"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { FlaskConical } from "lucide-react";
import { api, type ModelSummary, type ModelDetails } from "@/lib/api";
import { usePredictionStore } from "@/components/prediction-store";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { BarHChart } from "@/components/charts/bar-h-chart";
import { LineCurveChart } from "@/components/charts/line-curve-chart";

export function ExplainabilityView({ models }: { models: ModelSummary[] }) {
  const [active, setActive] = React.useState(models[0]?.id ?? "");
  const [cache, setCache] = React.useState<Record<string, ModelDetails>>({});
  const [ebmShapes, setEbmShapes] = React.useState<{ term: string; type: string; names: string[]; scores: number[] }[] | null>(null);

  React.useEffect(() => {
    if (!active || cache[active]) return;
    api.modelDetails(active).then((d) => setCache((prev) => ({ ...prev, [active]: d })));
  }, [active, cache]);

  React.useEffect(() => {
    if (active === "ebm" && !ebmShapes) {
      api.ebmShapes().then((r) => setEbmShapes(r.shapes));
    }
  }, [active, ebmShapes]);

  const details = cache[active];

  return (
    <div className="space-y-6">
      <Card className="surface">
        <CardHeader>
          <CardTitle className="text-sm">Global feature importance</CardTitle>
          <CardDescription>Permutation importance is the consistent cross-model method; native importance is shown where the model family supports it.</CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs value={active} onValueChange={setActive}>
            <TabsList>
              {models.map((m) => <TabsTrigger key={m.id} value={m.id}>{m.label}</TabsTrigger>)}
            </TabsList>
            {models.map((m) => (
              <TabsContent key={m.id} value={m.id} className="pt-4">
                {active === m.id && (!details ? <Skeleton className="h-72 w-full" /> : <ImportancePanel details={details} />)}
              </TabsContent>
            ))}
          </Tabs>
        </CardContent>
      </Card>

      {active === "ebm" && (
        <Card className="surface">
          <CardHeader>
            <CardTitle className="text-sm">EBM shape functions</CardTitle>
            <CardDescription>How each top term additively contributes to the prediction across its own range (e.g. pH, water activity, temperature).</CardDescription>
          </CardHeader>
          <CardContent>
            {!ebmShapes ? <Skeleton className="h-64 w-full" /> : (
              <div className="grid gap-4 lg:grid-cols-2">
                {ebmShapes.map((s) => (
                  <div key={s.term}>
                    <div className="mb-2 text-xs font-medium text-muted-foreground">{s.term.replace(/_/g, " ")}</div>
                    <LineCurveChart series={[{ name: s.term, color: "var(--warning)", points: s.scores }]} />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {details && Object.keys(details.category_errors).length > 0 && (
        <Card className="surface">
          <CardHeader>
            <CardTitle className="text-sm">Test error by category</CardTitle>
            <CardDescription>Where {models.find((m) => m.id === active)?.label} struggles most, by category.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            {Object.entries(details.category_errors).map(([col, groups]) => {
              const rows = Object.entries(groups).sort((a, b) => b[1].mae - a[1].mae).slice(0, 8);
              return (
                <div key={col}>
                  <div className="mb-2 text-xs font-medium capitalize text-muted-foreground">{col.replace(/_/g, " ")}</div>
                  <Table>
                    <TableHeader><TableRow><TableHead>Category</TableHead><TableHead className="text-right">MAE</TableHead><TableHead className="text-right">n</TableHead></TableRow></TableHeader>
                    <TableBody>
                      {rows.map(([k, v]) => (
                        <TableRow key={k}><TableCell className="text-xs">{k}</TableCell><TableCell className="text-right tabular-nums text-xs">{v.mae.toFixed(2)}</TableCell><TableCell className="text-right tabular-nums text-xs">{v.n}</TableCell></TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      <LocalExplanationCard />
    </div>
  );
}

function ImportancePanel({ details }: { details: ModelDetails }) {
  const perm = details.feature_importance.permutation ?? {};
  const native = details.feature_importance.native;
  const permData = Object.entries(perm).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 15).reverse().map(([label, value]) => ({ label, value: Number(value.toFixed(4)) }));
  const nativeData = native ? Object.entries(native).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 15).reverse().map(([label, value]) => ({ label, value: Number(value.toFixed(4)) })) : null;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div>
        <div className="mb-2 text-xs font-medium text-muted-foreground">Permutation importance</div>
        <BarHChart data={permData} height={320} />
      </div>
      <div>
        <div className="mb-2 text-xs font-medium text-muted-foreground">Native importance</div>
        {nativeData ? <BarHChart data={nativeData} color="var(--chart-4)" height={320} /> : (
          <div className="flex h-[320px] items-center justify-center text-xs text-muted-foreground">Not available for this model family.</div>
        )}
      </div>
    </div>
  );
}

function LocalExplanationCard() {
  const { lastPrediction } = usePredictionStore();
  const [factors, setFactors] = React.useState<{ feature: string; contribution: number }[] | null>(null);

  React.useEffect(() => {
    if (!lastPrediction) return;
    const top = lastPrediction.candidates[0];
    api.explainLocal({ model: top.model, row: top.row, top_k: 8 }).then((r) => setFactors(r.factors));
  }, [lastPrediction]);

  if (!lastPrediction) {
    return (
      <Card className="surface">
        <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
          <FlaskConical className="h-6 w-6 text-muted-foreground" />
          <p className="text-sm font-medium text-foreground">No prediction yet</p>
          <p className="text-xs text-muted-foreground">Run a prediction to see local factors for that specific formulation here.</p>
        </CardContent>
      </Card>
    );
  }

  const top = lastPrediction.candidates[0];

  return (
    <Card className="surface">
      <CardHeader>
        <CardTitle className="text-sm">Local explanation — {top.candidate_name}</CardTitle>
        <CardDescription>Exact contributions for EBM, permutation-based perturbation otherwise. From your most recent prediction.</CardDescription>
      </CardHeader>
      <CardContent>
        {!factors ? <Skeleton className="h-40 w-full" /> : (
          <ul className="space-y-1.5">
            {factors.map((f, i) => (
              <motion.li
                key={f.feature}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.18, delay: i * 0.04 }}
                className="flex items-center justify-between rounded-md border bg-secondary/30 px-3 py-1.5 text-xs"
              >
                <span className="text-foreground">{f.feature.replace(/_/g, " ")}</span>
                <span className={f.contribution >= 0 ? "font-mono text-success" : "font-mono text-destructive"}>
                  {f.contribution >= 0 ? "+" : ""}{f.contribution.toFixed(2)} d
                </span>
              </motion.li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
