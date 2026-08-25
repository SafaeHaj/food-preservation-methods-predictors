import { BookOpen, FlaskConical, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import { PageBody, PageHeader, Stagger, Reveal, SectionLabel } from "@/components/page-shell";
import { KpiCard } from "@/components/kpi-card";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { BarHChart } from "@/components/charts/bar-h-chart";

export default async function RealPage() {
  const data = await api.datasetReal();
  const ruleData = Object.entries(data.generation_rules).sort((a, b) => b[1] - a[1]).map(([label, value]) => ({ label: label.replace(/^RULE_/, "").replace(/_/g, " ").toLowerCase(), value }));

  return (
    <PageBody>
      <PageHeader
        title="Real Dataset Workspace"
        description="This dataset version is entirely synthetic — there is no real, paper-derived subset to report here. Shown honestly rather than fabricated."
        actions={<Badge variant="outline" className="border-primary/30 text-primary">no real subset in this version</Badge>}
      />

      <Stagger className="mb-6 grid-cols-2 md:grid-cols-3">
        <KpiCard label="Real rows" numericValue={data.total_rows} icon={<BookOpen className="h-4 w-4" />} tone="warning" animateIn sub="0 in this dataset version" />
        <KpiCard label="Generation rules" numericValue={Object.keys(data.generation_rules).length} icon={<FlaskConical className="h-4 w-4" />} animateIn sub="Synthetic-row provenance categories" />
        <KpiCard label="Quality flag" value={Object.keys(data.quality_flags)[0]?.replace(/_/g, " ") ?? "n/a"} icon={<ShieldCheck className="h-4 w-4" />} sub={`${Object.values(data.quality_flags)[0]?.toLocaleString() ?? 0} rows`} />
      </Stagger>

      <Reveal>
        <SectionLabel>Integrity</SectionLabel>
        <Card className="surface mb-8">
          <CardHeader>
            <CardTitle className="text-sm">Data integrity</CardTitle>
            <CardDescription className="leading-relaxed">{data.provenance_note}</CardDescription>
          </CardHeader>
        </Card>
      </Reveal>

      <Reveal delay={0.04}>
        <SectionLabel>Provenance</SectionLabel>
        <Card className="surface">
          <CardHeader>
            <CardTitle className="text-sm">Generation-rule breakdown</CardTitle>
            <CardDescription>Every row is tagged with the synthetic-generation rule that produced it (source_rule_id) — real provenance metadata, not a literature citation.</CardDescription>
          </CardHeader>
          <CardContent><BarHChart data={ruleData} height={300} color="var(--chart-4)" /></CardContent>
        </Card>
      </Reveal>
    </PageBody>
  );
}
