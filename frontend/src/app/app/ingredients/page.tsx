import { Database, Layers, Target, Sparkles, FlaskConical, GitCompareArrows, Gauge } from "lucide-react";
import { api } from "@/lib/api";
import { PageBody, PageHeader, Stagger, Reveal, SectionLabel } from "@/components/page-shell";
import { KpiCard } from "@/components/kpi-card";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { BarHChart } from "@/components/charts/bar-h-chart";
import { IngredientTable } from "@/components/ingredient-table";

const METHOD_STEPS = [
  { icon: Database, title: "Match to control", desc: "Every treated row is paired with its untreated control -- same matrix, storage, packaging." },
  { icon: GitCompareArrows, title: "Compute improvement", desc: "Relative shelf-life change vs. that matched control, as a percentage, for every row the ingredient appears in." },
  { icon: FlaskConical, title: "Adjust for context", desc: "A ridge regression controls for cheese category, storage temperature, concentration, pH, water activity, packaging and method -- isolating the ingredient's own contribution." },
  { icon: Gauge, title: "Check it holds up", desc: "The adjusted ranking is compared against completely held-out validation/test rows, not just the data used to build it." },
];

const CLASS_BADGE_VARIANT: Record<string, "destructive" | "warning" | "success"> = {
  Low: "destructive",
  Medium: "warning",
  High: "success",
};

export default async function IngredientsPage() {
  const health = await api.ingredientRankingHealth();

  if (!health.available) {
    return (
      <PageBody>
        <PageHeader title="Ingredients" description="Ingredient efficacy ranking is not available yet." />
        <Card className="surface">
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <p className="type-title text-foreground">Ranking artifacts not found</p>
            <p className="max-w-md text-xs text-muted-foreground">
              Run <code className="font-mono">python train_ingredient_ranking.py</code> to build the ranking, then reload this page.
            </p>
          </CardContent>
        </Card>
      </PageBody>
    );
  }

  const [manifest, { rankings, families, class_definitions }] = await Promise.all([
    api.ingredientRankingManifest(),
    api.ingredientRankings(),
  ]);

  const top10 = [...rankings].sort((a, b) => b.adjusted_effect_pct - a.adjusted_effect_pct).slice(0, 10)
    .map((r) => ({ label: r.ingredient_name, value: Number(r.adjusted_effect_pct.toFixed(1)) }));
  const bottom10 = [...rankings].sort((a, b) => a.adjusted_effect_pct - b.adjusted_effect_pct).slice(0, 10)
    .map((r) => ({ label: r.ingredient_name, value: Number(r.adjusted_effect_pct.toFixed(1)) }))
    .reverse();

  const classCounts = class_definitions.class_names.map((cls) => ({
    cls, count: rankings.filter((r) => r.efficacy_class === cls).length,
  }));

  return (
    <PageBody>
      <PageHeader
        title="Ingredient Efficacy"
        description="Ranks individual ingredients on their own, independent of any specific formulation -- a separate, complementary system to the formulation-level Classification page."
      />

      <Stagger className="mb-8 grid-cols-2 md:grid-cols-4">
        <KpiCard label="Ingredients ranked" numericValue={manifest.n_ingredients} icon={<Database className="h-4 w-4" />} tone="primary" animateIn sub="Every ingredient in the training set" />
        <KpiCard label="Classes" numericValue={class_definitions.class_names.length} icon={<Layers className="h-4 w-4" />} animateIn sub={class_definitions.class_names.join(" / ")} />
        <KpiCard label="Regression fit" numericValue={manifest.regression_in_sample_r2 * 100} decimals={1} suffix="%" icon={<Target className="h-4 w-4" />} tone="primary" sub="In-sample R², context-adjusted model" />
        <KpiCard
          label="Out-of-sample stability"
          value={manifest.rank_stability_spearman_vs_test_split !== null ? manifest.rank_stability_spearman_vs_test_split.toFixed(2) : "n/a"}
          icon={<Gauge className="h-4 w-4" />}
          tone="success"
          sub="Spearman vs. held-out test split"
        />
      </Stagger>

      <Reveal>
        <SectionLabel>Method</SectionLabel>
        <Card className="surface mb-8">
          <CardHeader>
            <CardTitle className="text-sm">Two rankings, checked against each other</CardTitle>
            <CardDescription>
              A raw average of an ingredient&apos;s outcomes can be misleading if it happened to be tested mostly in favourable
              conditions. The adjusted ranking below is a regression that controls for context; the simpler raw mean is shown
              alongside every ingredient, not hidden. The two methods agree on class {manifest.descriptive_vs_adjusted_agreement_pct.toFixed(0)}% of the time --
              disagreement is exactly where controlling for context changed the answer.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="relative grid grid-cols-2 gap-x-5 gap-y-7 sm:grid-cols-4">
              <div className="pointer-events-none absolute left-[8%] right-[8%] top-[18px] hidden h-px bg-gradient-to-r from-transparent via-border to-transparent lg:block" />
              {METHOD_STEPS.map((step, i) => (
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

      <Reveal delay={0.04}>
        <SectionLabel>Class definitions</SectionLabel>
        <Card className="surface mb-8">
          <CardHeader>
            <CardTitle className="text-sm">Adjusted effect over matched control</CardTitle>
            <CardDescription>{class_definitions.description}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 sm:grid-cols-3">
              {classCounts.map(({ cls, count }) => (
                <div key={cls} className="rounded-lg border p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <Badge variant={CLASS_BADGE_VARIANT[cls] ?? "secondary"} className="h-6 px-2 text-[11px]">{cls}</Badge>
                    <span className="font-mono text-[11px] text-muted-foreground">{((count / rankings.length) * 100).toFixed(0)}%</span>
                  </div>
                  <div className="numeral text-lg font-semibold text-foreground">{count} ingredients</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </Reveal>

      <Reveal delay={0.06}>
        <SectionLabel>Extremes</SectionLabel>
        <div className="mb-8 grid gap-4 lg:grid-cols-2">
          <Card className="surface">
            <CardHeader>
              <CardTitle className="text-sm">Highest adjusted effect</CardTitle>
              <CardDescription>Top 10 ingredients, controlling for the context they were tested in.</CardDescription>
            </CardHeader>
            <CardContent><BarHChart data={top10} height={280} color="var(--success)" /></CardContent>
          </Card>
          <Card className="surface">
            <CardHeader>
              <CardTitle className="text-sm">Lowest adjusted effect</CardTitle>
              <CardDescription>Bottom 10 -- some may reduce shelf life relative to a matched control.</CardDescription>
            </CardHeader>
            <CardContent><BarHChart data={bottom10} height={280} color="var(--destructive)" /></CardContent>
          </Card>
        </div>
      </Reveal>

      <Reveal delay={0.08}>
        <SectionLabel>Full ranking</SectionLabel>
        <Card className="surface">
          <CardHeader>
            <div className="flex items-center gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/12 text-primary">
                <Sparkles className="size-4" />
              </span>
              <div>
                <CardTitle className="text-sm">All {rankings.length} ingredients</CardTitle>
                <CardDescription className="mt-0.5">Sortable by any column; search by name or family.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <IngredientTable rankings={rankings} families={families} />
          </CardContent>
        </Card>
      </Reveal>
    </PageBody>
  );
}
