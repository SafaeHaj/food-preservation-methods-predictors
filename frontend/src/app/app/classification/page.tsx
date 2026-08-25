import Link from "next/link";
import { Database, Layers, Trophy, Target, Sparkles, FlaskConical, Scale, ListTree, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { PageBody, PageHeader, Stagger, Reveal, SectionLabel } from "@/components/page-shell";
import { KpiCard } from "@/components/kpi-card";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { BarHChart } from "@/components/charts/bar-h-chart";
import { ClassificationExplorer } from "@/components/classification-explorer";
import { ClassificationForm } from "@/components/classification-form";

const CLASS_BADGE_VARIANT: Record<string, "destructive" | "warning" | "success"> = {
  Low: "destructive",
  Medium: "warning",
  High: "success",
};

const METHOD_STEPS = [
  { icon: Database, title: "Match to control", desc: "Every treated row is paired with its untreated control -- same matrix, storage, packaging." },
  { icon: Scale, title: "Compute improvement", desc: "Relative shelf-life change vs. that matched control, as a percentage." },
  { icon: ListTree, title: "Bucket into tertiles", desc: "Improvement % is split into 3 balanced classes using train-split-only cutoffs." },
  { icon: FlaskConical, title: "Train on the combination", desc: "Matrix + storage + packaging + treatment -- never the ingredient in isolation." },
  { icon: Target, title: "Classify directly", desc: "At inference, one filled-in formulation goes in, one class comes out." },
];

export default async function ClassificationPage() {
  const health = await api.classificationHealth();

  if (!health.available) {
    return (
      <PageBody>
        <PageHeader title="Classification" description="Formulation efficacy classification is not available yet." />
        <Card className="surface">
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <p className="type-title text-foreground">Classifier artifacts not found</p>
            <p className="max-w-md text-xs text-muted-foreground">
              Run <code className="font-mono">python train_classifier.py</code> to build the classification artifacts, then reload this page.
            </p>
          </CardContent>
        </Card>
      </PageBody>
    );
  }

  const [manifest, { models, best_model, class_definitions }, distribution, schema, matrixLookup, ingredientLookup] = await Promise.all([
    api.classificationManifest(),
    api.classificationModels(),
    api.classificationDistribution(),
    api.classificationSchema(),
    api.matrixLookup(),
    api.ingredientLookup(),
  ]);

  const bestSummary = models.find((m) => m.is_best);
  const overallData = class_definitions.class_names.map((cls) => ({ label: cls, value: distribution.overall[cls] ?? 0 }));
  const totalRows = Object.values(distribution.overall).reduce((a, b) => a + b, 0);

  const familyRows = Object.entries(distribution.by_ingredient_family)
    .filter(([fam]) => fam !== "none")
    .map(([fam, counts]) => {
      const total = class_definitions.class_names.reduce((s, c) => s + (counts[c] ?? 0), 0);
      const highPct = total > 0 ? ((counts["High"] ?? 0) / total) * 100 : 0;
      return { fam, counts, total, highPct };
    })
    .sort((a, b) => b.highPct - a.highPct);

  return (
    <PageBody>
      <PageHeader
        title="Formulation Efficacy Classification"
        description="Classifies a full formulation + treatment combination -- not an ingredient in isolation -- into a Low / Medium / High shelf-life-improvement tier, trained on the same dataset as the regression models."
        actions={
          <Link href="#classify" className={buttonVariants()}>Classify a formulation<ArrowRight className="h-3.5 w-3.5" /></Link>
        }
      />

      <Stagger className="mb-8 grid-cols-2 md:grid-cols-4">
        <KpiCard label="Treated formulations" numericValue={manifest.n_total_treated_rows} icon={<Database className="h-4 w-4" />} tone="primary" animateIn sub="Matched to a control row" />
        <KpiCard label="Classes" numericValue={class_definitions.class_names.length} icon={<Layers className="h-4 w-4" />} animateIn sub={class_definitions.class_names.join(" / ")} />
        <KpiCard label="Best classifier" value={bestSummary?.label ?? best_model} icon={<Trophy className="h-4 w-4" />} tone="success" sub="Highest test macro F1" />
        <KpiCard label="Test accuracy" numericValue={(bestSummary?.test_accuracy ?? 0) * 100} decimals={1} suffix="%" icon={<Target className="h-4 w-4" />} tone="primary" animateIn sub={`vs. ${(100 / class_definitions.class_names.length).toFixed(0)}% random baseline`} />
      </Stagger>

      <Reveal>
        <SectionLabel>Method</SectionLabel>
        <Card className="surface mb-8">
          <CardHeader>
            <CardTitle className="text-sm">Why the combination, not the ingredient alone</CardTitle>
            <CardDescription>
              The same ingredient produces very different shelf-life gains depending on the cheese matrix, concentration, and application method it is paired with --
              training data shows within-ingredient standard deviations as high as 20 percentage points across contexts. A single fixed label per ingredient would
              erase that variation, so every prediction here is made on the full formulation, exactly as it will be used.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="relative grid grid-cols-2 gap-x-5 gap-y-7 sm:grid-cols-3 lg:grid-cols-5">
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
            <CardTitle className="text-sm">Shelf-life improvement over matched control</CardTitle>
            <CardDescription>{class_definitions.description}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 sm:grid-cols-3">
              <ClassRangeCard cls="Low" range={`< ${class_definitions.thresholds_pct.low_max.toFixed(1)}%`} count={distribution.overall["Low"] ?? 0} total={totalRows} />
              <ClassRangeCard cls="Medium" range={`${class_definitions.thresholds_pct.low_max.toFixed(1)}% – ${class_definitions.thresholds_pct.medium_max.toFixed(1)}%`} count={distribution.overall["Medium"] ?? 0} total={totalRows} />
              <ClassRangeCard cls="High" range={`≥ ${class_definitions.thresholds_pct.medium_max.toFixed(1)}%`} count={distribution.overall["High"] ?? 0} total={totalRows} />
            </div>
          </CardContent>
        </Card>
      </Reveal>

      <SectionLabel>Leaderboard</SectionLabel>
      <Card className="surface mb-8">
        <CardHeader>
          <CardTitle className="text-sm">Classifier comparison</CardTitle>
          <CardDescription>Ranked by test macro F1 (balanced across all 3 classes, unaffected by class size).</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Classifier</TableHead>
                <TableHead className="text-right">Val accuracy</TableHead>
                <TableHead className="text-right">Test accuracy</TableHead>
                <TableHead className="text-right">Val macro F1</TableHead>
                <TableHead className="text-right">Test macro F1</TableHead>
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
                    <div className="mt-0.5 text-[11px] font-normal text-muted-foreground">{m.blurb}</div>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{m.validation_accuracy.toFixed(3)}</TableCell>
                  <TableCell className="text-right tabular-nums">{m.test_accuracy.toFixed(3)}</TableCell>
                  <TableCell className="text-right tabular-nums">{m.validation_macro_f1.toFixed(3)}</TableCell>
                  <TableCell className="text-right tabular-nums">{m.test_macro_f1.toFixed(3)}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">{m.training_duration_sec.toFixed(1)}s</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Reveal delay={0.04}>
        <SectionLabel>Diagnostics</SectionLabel>
        <div className="mb-8">
          <ClassificationExplorer models={models} />
        </div>
      </Reveal>

      <Reveal delay={0.04}>
        <SectionLabel>Class distribution</SectionLabel>
        <div className="mb-8 grid gap-4 lg:grid-cols-2">
          <Card className="surface">
            <CardHeader>
              <CardTitle className="text-sm">Overall (train + validation + test)</CardTitle>
              <CardDescription>{totalRows.toLocaleString()} treated rows, balanced by design (tertile cutoffs).</CardDescription>
            </CardHeader>
            <CardContent><BarHChart data={overallData} height={180} /></CardContent>
          </Card>
          <Card className="surface">
            <CardHeader>
              <CardTitle className="text-sm">By cheese category</CardTitle>
              <CardDescription>Which categories skew toward higher-efficacy treatments in this dataset.</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Category</TableHead>
                    {class_definitions.class_names.map((c) => <TableHead key={c} className="text-right">{c}</TableHead>)}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {Object.entries(distribution.by_cheese_category).map(([cat, counts]) => (
                    <TableRow key={cat} className="row-interactive">
                      <TableCell className="capitalize">{cat.replace(/_/g, " ")}</TableCell>
                      {class_definitions.class_names.map((c) => (
                        <TableCell key={c} className="text-right tabular-nums">{counts[c] ?? 0}</TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
      </Reveal>

      <Reveal delay={0.04}>
        <SectionLabel>Ingredient families, ranked by share of High-tier outcomes</SectionLabel>
        <Card className="surface mb-8">
          <CardHeader>
            <CardTitle className="text-sm">Which families most often land in the High class</CardTitle>
            <CardDescription>
              Descriptive only, not a fixed label -- the same family still spans multiple classes depending on the formulation (see Method above).
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ingredient family</TableHead>
                    <TableHead className="text-right">Low</TableHead>
                    <TableHead className="text-right">Medium</TableHead>
                    <TableHead className="text-right">High</TableHead>
                    <TableHead className="text-right">% High</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {familyRows.map((r) => (
                    <TableRow key={r.fam} className="row-interactive">
                      <TableCell className="capitalize">{r.fam.replace(/_/g, " ")}</TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">{r.counts["Low"] ?? 0}</TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">{r.counts["Medium"] ?? 0}</TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">{r.counts["High"] ?? 0}</TableCell>
                      <TableCell className="text-right tabular-nums font-medium text-foreground">{r.highPct.toFixed(0)}%</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </Reveal>

      <div id="classify" className="scroll-mt-20">
        <SectionLabel>Classify a formulation</SectionLabel>
        <Card className="surface mb-4">
          <CardContent className="flex items-start gap-3 py-4">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/12 text-primary">
              <Sparkles className="size-4" />
            </span>
            <p className="text-xs leading-relaxed text-muted-foreground">
              Fill in a cheese profile and up to 4 candidate treatments below. Each is classified independently and directly --
              the control&apos;s shelf life is never requested, because the model already learned that relationship during training.
            </p>
          </CardContent>
        </Card>
        <ClassificationForm
          schema={schema}
          matrixLookup={matrixLookup}
          ingredientLookup={ingredientLookup}
          modelOptions={models.map((m) => m.id)}
          bestModel={best_model}
          classDefinitions={class_definitions}
        />
      </div>
    </PageBody>
  );
}

function ClassRangeCard({ cls, range, count, total }: { cls: string; range: string; count: number; total: number }) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className="rounded-lg border p-4">
      <div className="mb-2 flex items-center justify-between">
        <Badge variant={CLASS_BADGE_VARIANT[cls] ?? "secondary"} className="h-6 px-2 text-[11px]">{cls}</Badge>
        <span className="font-mono text-[11px] text-muted-foreground">{pct.toFixed(0)}% of rows</span>
      </div>
      <div className="numeral text-lg font-semibold text-foreground">{range}</div>
      <div className="mt-0.5 text-[11px] text-muted-foreground">{count.toLocaleString()} formulations</div>
    </div>
  );
}
