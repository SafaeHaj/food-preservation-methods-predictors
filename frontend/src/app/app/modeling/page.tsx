import { Trophy, BookOpen, ClipboardCheck, FlaskConical } from "lucide-react";
import { api } from "@/lib/api";
import { PageBody, PageHeader, Stagger, Reveal, SectionLabel } from "@/components/page-shell";
import { KpiCard } from "@/components/kpi-card";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { ModelCompareChart } from "@/components/charts/model-compare-chart";
import { ModelExplorer } from "@/components/model-explorer";

export default async function ModelingPage() {
  const { models, manifest } = await api.models();

  return (
    <PageBody>
      <PageHeader
        title="Modeling"
        description={`Training and validation results for ${models.length} independently-trained model${models.length === 1 ? "" : "s"}, read from saved artifacts. Retraining is CLI-only.`}
      />

      <Stagger className="mb-6 grid-cols-2 md:grid-cols-4">
        <KpiCard label="Best model" value={models.find((m) => m.is_best)?.label} icon={<Trophy className="h-4 w-4" />} tone="success" sub="Lowest validation RMSE" />
        <KpiCard label="Train rows" numericValue={manifest.n_train} icon={<BookOpen className="h-4 w-4" />} animateIn sub="70% of contexts" />
        <KpiCard label="Validation rows" numericValue={manifest.n_validation} icon={<ClipboardCheck className="h-4 w-4" />} animateIn sub="15% of contexts" />
        <KpiCard label="Test rows" numericValue={manifest.n_test} icon={<FlaskConical className="h-4 w-4" />} animateIn sub="15% of contexts, held out" />
      </Stagger>

      <SectionLabel>Leaderboard</SectionLabel>
      <Card className="surface mb-8">
        <CardHeader>
          <CardTitle className="text-sm">Model comparison</CardTitle>
          <CardDescription>Ranked by validation RMSE (lower is better).</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Model</TableHead>
                <TableHead className="text-right">Val R²</TableHead>
                <TableHead className="text-right">Test R²</TableHead>
                <TableHead className="text-right">Val RMSE</TableHead>
                <TableHead className="text-right">Test RMSE</TableHead>
                <TableHead className="text-right">Val MAE</TableHead>
                <TableHead className="text-right">Test MAE</TableHead>
                <TableHead className="text-right">Train time</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {models.map((m) => (
                <TableRow key={m.id} className={m.is_best ? "bg-accent/60" : "row-interactive"}>
                  <TableCell className={m.is_best ? "font-semibold text-primary" : "font-medium"}>
                    <div className="flex items-center gap-1.5">
                      {m.is_best && <Trophy className="h-3.5 w-3.5 text-warning" />}
                      {m.label}
                      {m.is_best && <Badge className="ml-1 h-5 px-1.5 text-[10px]">best</Badge>}
                    </div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{m.validation_r2.toFixed(3)}</TableCell>
                  <TableCell className="text-right tabular-nums">{m.test_r2.toFixed(3)}</TableCell>
                  <TableCell className="text-right tabular-nums">{m.validation_rmse.toFixed(2)}</TableCell>
                  <TableCell className="text-right tabular-nums">{m.test_rmse.toFixed(2)}</TableCell>
                  <TableCell className="text-right tabular-nums">{m.validation_mae.toFixed(2)}</TableCell>
                  <TableCell className="text-right tabular-nums">{m.test_mae.toFixed(2)}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">{m.training_duration_sec.toFixed(1)}s</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Reveal>
        <Card className="surface mb-8">
          <CardHeader>
            <CardTitle className="text-sm">Validation vs. test RMSE by model</CardTitle>
            <CardDescription>Lower is better. A small val↔test gap indicates the model generalizes.</CardDescription>
          </CardHeader>
          <CardContent><ModelCompareChart models={models} /></CardContent>
        </Card>
      </Reveal>

      <Reveal delay={0.04}>
        <SectionLabel>Per-model diagnostics</SectionLabel>
        <ModelExplorer models={models} />
      </Reveal>

      <Reveal delay={0.04}>
        <SectionLabel>Provenance</SectionLabel>
        <Card className="surface mt-2">
          <CardHeader>
            <CardTitle className="text-sm">Training run details</CardTitle>
            <CardDescription>Retraining happens only via <code className="font-mono">python train_models.py</code>, never from this dashboard.</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
              <Row label="Random seed" value={String(manifest.random_seed)} />
              <Row label="Dataset" value={manifest.dataset_path} />
              <Row label="Total rows (real / synthetic)" value={`${manifest.n_total.toLocaleString()} (${manifest.n_real_paper_derived} / ${manifest.n_synthetic.toLocaleString()})`} />
              <Row label="Train / val / test rows" value={`${manifest.n_train.toLocaleString()} / ${manifest.n_validation.toLocaleString()} / ${manifest.n_test.toLocaleString()}`} />
              <Row label="Total training duration" value={`${manifest.total_training_duration_sec.toFixed(1)} s`} />
              <Row label="Trained at (UTC)" value={manifest.created_at_utc.split(".")[0]} />
            </dl>
          </CardContent>
        </Card>
      </Reveal>
    </PageBody>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b py-1.5 last:border-0 sm:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-mono text-xs text-foreground">{value}</dd>
    </div>
  );
}
