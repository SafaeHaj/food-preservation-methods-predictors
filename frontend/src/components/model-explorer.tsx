"use client";

import * as React from "react";
import { api, type ModelSummary, type ModelDetails } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LineCurveChart } from "@/components/charts/line-curve-chart";
import { BarHChart } from "@/components/charts/bar-h-chart";
import { ActualVsPredictedChart } from "@/components/charts/scatter-chart";

export function ModelExplorer({ models }: { models: ModelSummary[] }) {
  const [active, setActive] = React.useState(models[0]?.id ?? "");
  const [cache, setCache] = React.useState<Record<string, ModelDetails>>({});
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!active || cache[active]) return;
    setLoading(true);
    api.modelDetails(active).then((d) => {
      setCache((prev) => ({ ...prev, [active]: d }));
      setLoading(false);
    });
  }, [active, cache]);

  const details = cache[active];

  return (
    <Card className="surface">
      <CardHeader>
        <CardTitle className="text-sm">Model diagnostics</CardTitle>
        <CardDescription>Complete metrics, training curve, and feature importance per model.</CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs value={active} onValueChange={setActive}>
          <TabsList>
            {models.map((m) => (
              <TabsTrigger key={m.id} value={m.id}>{m.label}</TabsTrigger>
            ))}
          </TabsList>
          {models.map((m) => (
            <TabsContent key={m.id} value={m.id} className="pt-4">
              {active === m.id && (loading && !details ? <DetailsSkeleton /> : details && <DetailsPanel details={details} />)}
            </TabsContent>
          ))}
        </Tabs>
      </CardContent>
    </Card>
  );
}

function DetailsSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-24 w-full" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    </div>
  );
}

function DetailsPanel({ details }: { details: ModelDetails }) {
  const m = details.metrics;
  const permImportance = details.feature_importance.permutation ?? {};
  const nativeImportance = details.feature_importance.native;
  const permData = Object.entries(permImportance).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 12).reverse().map(([label, value]) => ({ label, value: Number(value.toFixed(4)) }));
  const nativeData = nativeImportance
    ? Object.entries(nativeImportance).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 12).reverse().map(([label, value]) => ({ label, value: Number(value.toFixed(4)) }))
    : null;

  return (
    <div className="space-y-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Split</TableHead>
            <TableHead className="text-right">R²</TableHead>
            <TableHead className="text-right">RMSE</TableHead>
            <TableHead className="text-right">MAE</TableHead>
            <TableHead className="text-right">Median AE</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {(["train", "validation", "test"] as const).map((s) => (
            <TableRow key={s}>
              <TableCell className="capitalize">{s}</TableCell>
              <TableCell className="text-right tabular-nums">{(m[`${s}_r2`] as number)?.toFixed(3)}</TableCell>
              <TableCell className="text-right tabular-nums">{(m[`${s}_rmse`] as number)?.toFixed(2)}</TableCell>
              <TableCell className="text-right tabular-nums">{(m[`${s}_mae`] as number)?.toFixed(2)}</TableCell>
              <TableCell className="text-right tabular-nums">{(m[`${s}_median_ae`] as number)?.toFixed(2)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="surface">
          <CardHeader><CardTitle className="text-xs">Actual vs. predicted (test)</CardTitle></CardHeader>
          <CardContent><ActualVsPredictedChart points={details.scatter.test} /></CardContent>
        </Card>
        <Card className="surface">
          <CardHeader><CardTitle className="text-xs">Training diagnostic</CardTitle></CardHeader>
          <CardContent>
            {details.curves ? (
              details.curves.type === "loss_curve" ? (
                <LineCurveChart series={[
                  { name: "train loss", color: "var(--primary)", points: details.curves.train_loss ?? [] },
                  { name: "validation loss", color: "var(--chart-2)", points: details.curves.val_loss ?? [] },
                ]} xLabel="Boosting round / epoch" />
              ) : (
                <LineCurveChart series={[
                  { name: "train R²", color: "var(--primary)", points: details.curves.train_r2 ?? [] },
                  { name: "validation R²", color: "var(--chart-2)", points: details.curves.val_r2 ?? [] },
                ]} xLabel="Training-set size step" />
              )
            ) : (
              <div className="flex h-[240px] items-center justify-center text-xs text-muted-foreground">No curve stored for this model.</div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="surface">
          <CardHeader><CardTitle className="text-xs">Permutation importance (cross-model consistent)</CardTitle></CardHeader>
          <CardContent><BarHChart data={permData} height={280} /></CardContent>
        </Card>
        <Card className="surface">
          <CardHeader><CardTitle className="text-xs">Native importance</CardTitle></CardHeader>
          <CardContent>
            {nativeData ? <BarHChart data={nativeData} color="var(--chart-4)" height={280} /> : (
              <div className="flex h-[280px] items-center justify-center text-xs text-muted-foreground">No native importance for this model family.</div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
