import { Database, FlaskConical, Beaker, ClipboardList } from "lucide-react";
import { api } from "@/lib/api";
import { PageBody, PageHeader, Stagger, Reveal, SectionLabel } from "@/components/page-shell";
import { KpiCard } from "@/components/kpi-card";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { HistogramChart } from "@/components/charts/histogram-chart";
import { BarHChart } from "@/components/charts/bar-h-chart";

export default async function SyntheticPage() {
  const data = await api.datasetSynthetic();
  const familyData = Object.entries(data.ingredient_families).sort((a, b) => b[1] - a[1]).map(([label, value]) => ({ label: label.replace(/_/g, " "), value }));

  return (
    <PageBody>
      <PageHeader
        title="Synthetic Dataset Workspace"
        description="A scientifically constrained synthetic training set generated to reflect real cheese systems. This route follows the identical modeling pipeline as the real-data workflow."
        actions={
          <div className="flex gap-2">
            <Badge variant="outline" className="border-primary/30 text-primary">scientifically constrained</Badge>
            <Badge variant="outline">training-ready</Badge>
          </div>
        }
      />

      <Stagger className="mb-6 grid-cols-2 md:grid-cols-4">
        <KpiCard label="Total rows" numericValue={data.total_rows} icon={<Database className="h-4 w-4" />} tone="primary" animateIn />
        <KpiCard label="Contexts" numericValue={data.contexts} icon={<FlaskConical className="h-4 w-4" />} animateIn sub="Environmental/processing settings" />
        <KpiCard label="Controls" numericValue={data.controls} icon={<ClipboardList className="h-4 w-4" />} animateIn />
        <KpiCard label="Treatments" numericValue={data.treatments} icon={<Beaker className="h-4 w-4" />} animateIn />
      </Stagger>

      <Reveal>
        <SectionLabel>Distributions</SectionLabel>
        <div className="mb-8 grid gap-4 lg:grid-cols-2">
          <Card className="surface">
            <CardHeader>
              <CardTitle className="text-sm">Shelf-life distribution (days)</CardTitle>
              <CardDescription>
                Target range {data.target_min.toFixed(2)}–{data.target_max.toFixed(2)} days.
              </CardDescription>
            </CardHeader>
            <CardContent><HistogramChart counts={data.shelf_life_histogram} edges={data.shelf_life_bin_edges} /></CardContent>
          </Card>
          <Card className="surface">
            <CardHeader>
              <CardTitle className="text-sm">Storage-temperature distribution</CardTitle>
              <CardDescription>The strongest single driver of shelf life.</CardDescription>
            </CardHeader>
            <CardContent><HistogramChart counts={data.storage_temperature_histogram} edges={data.storage_temperature_bin_edges} color="var(--chart-2)" /></CardContent>
          </Card>
        </div>
      </Reveal>

      <Reveal delay={0.04}>
        <SectionLabel>Formulation space</SectionLabel>
        <Card className="surface mb-8">
          <CardHeader>
            <CardTitle className="text-sm">Ingredient families</CardTitle>
            <CardDescription>Distribution across non-control treatment rows.</CardDescription>
          </CardHeader>
          <CardContent><BarHChart data={familyData} height={220} /></CardContent>
        </Card>
      </Reveal>

      <Reveal delay={0.04}>
        <SectionLabel>Schema</SectionLabel>
        <Card className="surface">
          <CardHeader>
            <CardTitle className="text-sm">Schema preview</CardTitle>
            <CardDescription>Generation method: {data.generation_method?.replace(/_/g, " ")}.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Column</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead className="text-right">Missing</TableHead>
                    <TableHead>Example</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.schema_preview.map((row) => (
                    <TableRow key={row.column} className="row-interactive">
                      <TableCell className="font-mono text-xs">{row.column}</TableCell>
                      <TableCell className="capitalize">{row.role}</TableCell>
                      <TableCell className="text-muted-foreground">{row.dtype}</TableCell>
                      <TableCell className="text-right tabular-nums">{row.missing_pct.toFixed(1)}%</TableCell>
                      <TableCell className="text-muted-foreground">{String(row.example)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </Reveal>
    </PageBody>
  );
}
