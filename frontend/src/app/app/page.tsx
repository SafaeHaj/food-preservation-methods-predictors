import Link from "next/link";
import { Database, Route as RouteIcon, ClipboardCheck, Brain, LineChart, Lightbulb, ArrowRight, Trophy, Layers } from "lucide-react";
import { api, MODEL_LABELS } from "@/lib/api";
import { PageBody, PageHeader, Stagger, Reveal, SectionLabel } from "@/components/page-shell";
import { KpiCard } from "@/components/kpi-card";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { HistogramChart } from "@/components/charts/histogram-chart";
import { BarHChart } from "@/components/charts/bar-h-chart";

const PIPELINE = [
  { icon: Database, title: "Data curation", desc: "Load training_data, drop identifiers & provenance flags." },
  { icon: ClipboardCheck, title: "Schema validation", desc: "Auto-detect numeric / categorical / binary columns." },
  { icon: RouteIcon, title: "Feature preparation", desc: "Impute, encode, scale per model family." },
  { icon: Brain, title: "Model training", desc: "Fit independent models, early-stop where supported." },
  { icon: LineChart, title: "Prediction", desc: "Compare a control formulation against candidates." },
  { icon: Lightbulb, title: "Explainability", desc: "Permutation importance, EBM shapes, local factors." },
];

export default async function HomePage() {
  const [manifest, synthetic] = await Promise.all([api.manifest(), api.datasetSynthetic()]);
  const familyData = Object.entries(synthetic.ingredient_families)
    .sort((a, b) => b[1] - a[1])
    .map(([label, value]) => ({ label: label.replace(/_/g, " "), value }));

  return (
    <PageBody>
      <PageHeader
        title="Shelf-Life Prediction Workspace"
        description="A machine-learning research platform for predicting cheese shelf life from formulation, processing, and storage attributes."
        actions={
          <Link href="/app/prediction" className={buttonVariants()}>Run a prediction<ArrowRight className="h-3.5 w-3.5" /></Link>
        }
      />

      <Stagger className="mb-8 grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
        <KpiCard label="Total rows" numericValue={manifest.n_total} icon={<Database className="h-4 w-4" />} tone="primary" animateIn sub="training_data sheet" />
        <KpiCard label="Contexts" numericValue={manifest.n_contexts_total} icon={<RouteIcon className="h-4 w-4" />} animateIn sub="Environmental / processing settings" />
        <KpiCard label="Target range" value={`${synthetic.target_min.toFixed(1)}–${synthetic.target_max.toFixed(1)} d`} icon={<LineChart className="h-4 w-4" />} sub="shelf_life_days" />
        <KpiCard label="Models trained" numericValue={manifest.models_trained.length} icon={<Layers className="h-4 w-4" />} animateIn sub={manifest.models_trained.map((m) => MODEL_LABELS[m] ?? m).join(", ")} />
        <KpiCard label="Best model" value={MODEL_LABELS[manifest.best_model_by_validation_rmse] ?? manifest.best_model_by_validation_rmse} icon={<Trophy className="h-4 w-4" />} tone="success" sub="Lowest validation RMSE" />
      </Stagger>

      <Reveal>
        <SectionLabel>Method</SectionLabel>
        <Card className="surface mb-8">
          <CardHeader>
            <CardTitle className="text-sm">Shared modeling pipeline</CardTitle>
            <CardDescription>Every page in this app reads the same trained artifacts through one backend.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="relative grid grid-cols-2 gap-x-5 gap-y-7 sm:grid-cols-3 lg:grid-cols-6">
              {/* Connecting rule behind the step icons, large screens only */}
              <div className="pointer-events-none absolute left-[8%] right-[8%] top-[18px] hidden h-px bg-gradient-to-r from-transparent via-border to-transparent lg:block" />
              {PIPELINE.map((step, i) => (
                <div key={step.title} className="group relative">
                  <div className="relative mb-3 flex h-10 w-10 items-center justify-center rounded-full border border-border bg-card text-primary shadow-xs transition-all duration-300 group-hover:border-primary/30 group-hover:shadow-sm">
                    <step.icon className="h-4 w-4" />
                  </div>
                  <div className="absolute right-0 top-0 font-mono text-[10px] tabular-nums text-muted-foreground">
                    {String(i + 1).padStart(2, "0")}
                  </div>
                  <div className="text-[13px] font-medium text-foreground">{step.title}</div>
                  <div className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{step.desc}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </Reveal>

      <Reveal delay={0.05}>
        <SectionLabel>Dataset at a glance</SectionLabel>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card className="surface">
            <CardHeader>
              <CardTitle className="text-sm">Shelf-life distribution (days)</CardTitle>
              <CardDescription>Across the full training dataset.</CardDescription>
            </CardHeader>
            <CardContent>
              <HistogramChart counts={synthetic.shelf_life_histogram} edges={synthetic.shelf_life_bin_edges} />
            </CardContent>
          </Card>
          <Card className="surface">
            <CardHeader>
              <CardTitle className="text-sm">Rows by ingredient family</CardTitle>
              <CardDescription>Non-control treatment rows only.</CardDescription>
            </CardHeader>
            <CardContent>
              <BarHChart data={familyData} height={220} />
            </CardContent>
          </Card>
        </div>
      </Reveal>
    </PageBody>
  );
}
