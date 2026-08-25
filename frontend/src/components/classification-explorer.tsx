"use client";

import * as React from "react";
import { api, type ClassificationModelSummary, type ClassificationModelDetails } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { BarHChart } from "@/components/charts/bar-h-chart";

const CLASS_COLOR: Record<string, string> = {
  Low: "var(--destructive)",
  Medium: "var(--warning)",
  High: "var(--success)",
};

export function ClassificationExplorer({ models }: { models: ClassificationModelSummary[] }) {
  const [active, setActive] = React.useState(models[0]?.id ?? "");
  const [cache, setCache] = React.useState<Record<string, ClassificationModelDetails>>({});
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!active || cache[active]) return;
    setLoading(true);
    api.classificationModelDetails(active).then((d) => {
      setCache((prev) => ({ ...prev, [active]: d }));
      setLoading(false);
    });
  }, [active, cache]);

  const details = cache[active];

  return (
    <Card className="surface">
      <CardHeader>
        <CardTitle className="text-sm">Classifier diagnostics</CardTitle>
        <CardDescription>Per-split metrics, confusion matrix, and feature importance per classifier.</CardDescription>
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

function DetailsPanel({ details }: { details: ClassificationModelDetails }) {
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
            <TableHead className="text-right">Accuracy</TableHead>
            <TableHead className="text-right">Macro F1</TableHead>
            {details.confusion_matrix.labels.map((cls) => (
              <TableHead key={cls} className="text-right">{cls} F1</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {(["train", "validation", "test"] as const).map((s) => (
            <TableRow key={s}>
              <TableCell className="capitalize">{s}</TableCell>
              <TableCell className="text-right tabular-nums">{m[s].accuracy.toFixed(3)}</TableCell>
              <TableCell className="text-right tabular-nums">{m[s].macro_f1.toFixed(3)}</TableCell>
              {details.confusion_matrix.labels.map((cls) => (
                <TableCell key={cls} className="text-right tabular-nums">{m[s].per_class[cls]?.f1.toFixed(3) ?? "—"}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="surface">
          <CardHeader>
            <CardTitle className="text-xs">Confusion matrix (test split)</CardTitle>
            <CardDescription>Rows: actual class. Columns: predicted class.</CardDescription>
          </CardHeader>
          <CardContent><ConfusionMatrix confusion={details.confusion_matrix} /></CardContent>
        </Card>
        <Card className="surface">
          <CardHeader><CardTitle className="text-xs">Permutation importance (accuracy drop)</CardTitle></CardHeader>
          <CardContent><BarHChart data={permData} height={280} /></CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="surface">
          <CardHeader><CardTitle className="text-xs">Native importance</CardTitle></CardHeader>
          <CardContent>
            {nativeData ? <BarHChart data={nativeData} color="var(--chart-4)" height={240} /> : (
              <div className="flex h-[240px] items-center justify-center text-xs text-muted-foreground">No native importance for this model family.</div>
            )}
          </CardContent>
        </Card>
        <Card className="surface">
          <CardHeader><CardTitle className="text-xs">Per-class precision / recall (test)</CardTitle></CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Class</TableHead>
                  <TableHead className="text-right">Precision</TableHead>
                  <TableHead className="text-right">Recall</TableHead>
                  <TableHead className="text-right">F1</TableHead>
                  <TableHead className="text-right">Support</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {details.confusion_matrix.labels.map((cls) => {
                  const pc = m.test.per_class[cls];
                  return (
                    <TableRow key={cls}>
                      <TableCell>
                        <span className="inline-flex items-center gap-1.5">
                          <span className="size-2 rounded-full" style={{ background: CLASS_COLOR[cls] }} />
                          {cls}
                        </span>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{pc?.precision.toFixed(3) ?? "—"}</TableCell>
                      <TableCell className="text-right tabular-nums">{pc?.recall.toFixed(3) ?? "—"}</TableCell>
                      <TableCell className="text-right tabular-nums">{pc?.f1.toFixed(3) ?? "—"}</TableCell>
                      <TableCell className="text-right tabular-nums">{pc?.support ?? "—"}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function ConfusionMatrix({ confusion }: { confusion: { labels: string[]; matrix: number[][] } }) {
  const { labels, matrix } = confusion;
  const maxVal = Math.max(...matrix.flat(), 1);
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-1">
        <thead>
          <tr>
            <th className="w-24 text-left text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Actual \ Pred</th>
            {labels.map((l) => (
              <th key={l} className="pb-1 text-center text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{l}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {labels.map((rowLabel, i) => (
            <tr key={rowLabel}>
              <td className="pr-2 text-right text-[11px] font-medium text-muted-foreground">{rowLabel}</td>
              {labels.map((colLabel, j) => {
                const val = matrix[i]?.[j] ?? 0;
                const intensity = val / maxVal;
                const isDiag = i === j;
                return (
                  <td key={colLabel} className="p-0">
                    <div
                      className="flex aspect-square min-w-[3.25rem] items-center justify-center rounded-md text-xs font-semibold tabular-nums"
                      style={{
                        background: isDiag
                          ? `color-mix(in srgb, var(--success) ${10 + intensity * 55}%, transparent)`
                          : `color-mix(in srgb, var(--destructive) ${intensity * 45}%, transparent)`,
                        color: intensity > 0.5 ? "var(--foreground)" : "var(--muted-foreground)",
                      }}
                    >
                      {val}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
