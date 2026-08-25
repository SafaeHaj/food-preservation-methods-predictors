import { Database, ClipboardCheck, Route as RouteIcon, Brain, LineChart, Lightbulb } from "lucide-react";
import { api } from "@/lib/api";
import { PageBody, PageHeader, Reveal, SectionLabel } from "@/components/page-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const STEPS = [
  { icon: Database, title: "Data curation", desc: "Load the training workbook; drop identifiers and provenance flags so they can never leak into a prediction." },
  { icon: ClipboardCheck, title: "Schema validation", desc: "Automatically classify every remaining column as numeric, binary, or categorical." },
  { icon: RouteIcon, title: "Feature preparation", desc: "Median/mode imputation, one-hot encoding for tree models, native dtypes preserved for the EBM." },
  { icon: Brain, title: "Model training", desc: "Fit each model independently on the same context-grouped train split, with early stopping where supported." },
  { icon: LineChart, title: "Prediction", desc: "Load the saved pipelines and predict a control plus up to four candidates — never retrains." },
  { icon: Lightbulb, title: "Explainability", desc: "Permutation importance for every model, native importance where available, EBM shape functions, and local factors for your last prediction." },
];


const GLOSSARY = [
  ["context_id", "One experimental context: a fixed set of environmental/processing conditions that several rows (control + treatments) share."],
  ["food_matrix", "The specific cheese product (e.g. mozzarella, burrata)."],
  ["matrix_ph", "Acidity of the product — lower values generally slow microbial growth."],
  ["matrix_water_activity", "Free water available for microbial growth; a key spoilage driver."],
  ["storage_temperature_c", "Storage/display temperature — the single strongest lever on shelf life."],
  ["packaging_type", "Barrier properties of the packaging (vacuum, MAP, active film, etc.)."],
  ["indicator_type", "The spoilage indicator organism/measure the threshold is defined against."],
  ["indicator_threshold", "The indicator level (in its own unit — log CFU/g, a relative index, or a sensory score) that defines end-of-shelf-life."],
  ["primary_ingredient_name", "The active antimicrobial/antioxidant ingredient, if any, added to the formulation."],
  ["90% prediction interval", "A split-conformal interval calibrated on the validation set's residuals — not a property of the model itself, but a wrapper around any of them."],
];

export default async function HowItWorksPage() {
  // Pull the model list from the backend rather than hardcoding it, so this
  // page can never claim a model was trained when it wasn't.
  const [manifest, { models }] = await Promise.all([api.manifest(), api.models()]);
  return (
    <PageBody>
      <PageHeader title="How Shelf-Life Studio Works" description="From raw workbook to an explainable, ranked shelf-life prediction." />

      <Card className="surface mb-6">
        <CardHeader>
          <CardTitle className="text-sm">Application purpose</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm leading-relaxed text-muted-foreground">
          <p>
            Shelf-Life Studio predicts how many days a cheese product remains within a defined spoilage-indicator
            threshold, given its formulation, processing, packaging, and storage conditions. It also compares a
            control formulation against candidate antimicrobial/antioxidant treatments, ranking them by predicted
            improvement.
          </p>
          <p>
            The dataset is{" "}
            <strong className="text-foreground">
              {manifest.n_real_paper_derived > 0 ? "predominantly synthetic" : "entirely synthetic"}
            </strong>{" "}
            ({manifest.n_synthetic.toLocaleString()} of {manifest.n_total.toLocaleString()} rows are
            scientifically-constrained synthetic points
            {manifest.n_real_paper_derived > 0
              ? `; ${manifest.n_real_paper_derived} are real, paper-derived measurements). Treat absolute predictions as a prototyping signal, not a validated laboratory result — see References for the literature behind the real subset.`
              : " — this dataset version has no real, paper-derived subset). Treat absolute predictions as a prototyping signal, not a validated laboratory result — see References for how the synthetic data was generated."}
          </p>
        </CardContent>
      </Card>

      <Reveal>
        <SectionLabel>Pipeline</SectionLabel>
        <Card className="surface mb-8">
          <CardHeader><CardTitle className="text-sm">End-to-end pipeline</CardTitle></CardHeader>
          <CardContent>
            <div className="relative grid grid-cols-2 gap-x-5 gap-y-7 sm:grid-cols-3 lg:grid-cols-6">
              <div className="pointer-events-none absolute left-[8%] right-[8%] top-[18px] hidden h-px bg-gradient-to-r from-transparent via-border to-transparent lg:block" />
              {STEPS.map((s, i) => (
                <div key={s.title} className="group relative">
                  <div className="relative mb-3 flex h-10 w-10 items-center justify-center rounded-full border border-border bg-card text-primary shadow-xs transition-all duration-300 group-hover:border-primary/30 group-hover:shadow-sm">
                    <s.icon className="h-4 w-4" />
                  </div>
                  <div className="absolute right-0 top-0 font-mono text-[10px] tabular-nums text-muted-foreground">
                    {String(i + 1).padStart(2, "0")}
                  </div>
                  <div className="text-[13px] font-medium text-foreground">{s.title}</div>
                  <div className="mt-1 text-[11px] leading-relaxed text-muted-foreground">{s.desc}</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </Reveal>

      <Reveal delay={0.04}>
        <SectionLabel>Models</SectionLabel>
        <Card className="surface mb-8">
          <CardHeader><CardTitle className="text-sm">Models used</CardTitle></CardHeader>
          <CardContent className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {models.map((m) => (
              <div key={m.id} className="border-l-2 border-border pl-3 transition-colors duration-200 hover:border-primary/40">
                <div className="mb-1 font-serif text-sm font-semibold text-foreground">{m.label}</div>
                <div className="text-[11px] leading-relaxed text-muted-foreground">{m.blurb}</div>
              </div>
            ))}
          </CardContent>
        </Card>
      </Reveal>

      <Reveal delay={0.04}>
        <SectionLabel>Glossary</SectionLabel>
        <Card className="surface mb-8">
          <CardHeader><CardTitle className="text-sm">Feature &amp; concept glossary</CardTitle></CardHeader>
          <CardContent>
            <Table>
              <TableHeader><TableRow><TableHead className="w-64">Term</TableHead><TableHead>Meaning</TableHead></TableRow></TableHeader>
              <TableBody>
                {GLOSSARY.map(([term, def]) => (
                  <TableRow key={term} className="row-interactive">
                    <TableCell className="font-mono text-xs">{term}</TableCell>
                    <TableCell className="text-sm leading-relaxed text-muted-foreground">{def}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </Reveal>

      <Reveal delay={0.04}>
        <SectionLabel>Caveats</SectionLabel>
      </Reveal>
      <Card className="surface">
        <CardHeader><CardTitle className="text-sm">Good to know</CardTitle></CardHeader>
        <CardContent>
          <ul className="list-disc space-y-2 pl-5 text-sm text-muted-foreground">
            <li>The 90% interval on every prediction comes from split-conformal calibration on the validation set, not from the model itself.</li>
            <li>This data is cross-sectional, not sequential — tree-based and additive models suit it well; sequence models have no natural advantage here.</li>
            <li>Retraining only happens via <code className="rounded bg-secondary px-1 py-0.5 font-mono text-xs">python train_models.py</code> from the command line — this application only ever reads saved artifacts.</li>
            <li>Identifier and data-provenance columns (row_id, context_id, data_origin, quality_flag, etc.) are excluded from model features to prevent leakage.</li>
          </ul>
        </CardContent>
      </Card>
    </PageBody>
  );
}
