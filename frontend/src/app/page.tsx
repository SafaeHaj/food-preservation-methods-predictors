import Link from "next/link";
import {
  ArrowRight,
  Boxes,
  GitBranch,
  LineChart,
  Lock,
  ScrollText,
  SlidersHorizontal,
} from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { SiteHeader } from "@/components/marketing/site-header";
import { SiteFooter } from "@/components/marketing/site-footer";
import { Reveal, RevealLines } from "@/components/marketing/reveal";
import { ProductFrame } from "@/components/marketing/product-frame";
import { EditorialImage } from "@/components/marketing/editorial-image";
import {
  CategoryErrorPreview,
  ComparisonPreview,
  ExplainPreview,
  LeaderboardPreview,
} from "@/components/marketing/previews";
import { PipelineScroller } from "@/components/marketing/pipeline-scroller";

const CAPABILITIES = [
  {
    icon: SlidersHorizontal,
    title: "Predict from formulation",
    body: "Matrix chemistry, storage, packaging and the spoilage indicator you track. Every prediction carries a 90% conformal interval calibrated on held-out data.",
  },
  {
    icon: GitBranch,
    title: "Compare against a control",
    body: "Score candidate treatments beside an untreated control built from the training split's own control rows — ranked by predicted shelf life and relative gain.",
  },
  {
    icon: LineChart,
    title: "Four models, one leaderboard",
    body: "Random Forest, LightGBM, XGBoost and an Explainable Boosting Machine, trained independently and ranked by validation RMSE.",
  },
  {
    icon: ScrollText,
    title: "Explain any prediction",
    body: "See which features pushed a prediction up or down. The EBM contributes native additive decompositions; tree models use reference-value perturbation.",
  },
  {
    icon: Boxes,
    title: "Inspect the dataset",
    body: "Distributions across cheese products, ingredient families, packaging formats and indicators — plus the provenance rule behind every generated row.",
  },
  {
    icon: Lock,
    title: "Leakage-safe by construction",
    body: "Rows group by context_id so a formulation and its control never split across train, validation and test. Identifier columns are excluded from features.",
  },
];

export default function LandingPage() {
  return (
    // The shared <Ambience/> (mounted once in the root layout) supplies the
    // aurora and grid behind this page; `dark` is global now, so this div is
    // just the min-height wrapper.
    <div className="min-h-svh">
      <SiteHeader />

      {/* overflow-x-clip: masks bleed past their sections by design; clip
          here so none of it can create a page-level horizontal scrollbar. */}
      <main className="flex flex-col overflow-x-clip">
        {/* ── Hero ─────────────────────────────────────────────────────── */}
        <section className="relative px-5 pt-36 pb-24 sm:px-7 sm:pt-44 sm:pb-32">
          <div className="relative mx-auto w-full max-w-[1180px]">
            <div className="mx-auto max-w-[820px] text-center">
              <Reveal immediate>
                <Link
                  href="#validation"
                  className="group inline-flex items-center gap-2 rounded-full border border-border bg-white/[0.03] py-1 pr-2.5 pl-1 backdrop-blur-sm transition-colors hover:border-border-strong"
                >
                  <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[0.6875rem] font-medium text-primary">
                    New
                  </span>
                  <span className="type-caption text-muted-foreground">
                    External literature validation
                  </span>
                  <ArrowRight className="size-3 text-subtle-foreground transition-transform group-hover:translate-x-0.5" />
                </Link>
              </Reveal>

              <h1 className="type-hero text-gradient-fade mt-7">
                <RevealLines
                  immediate
                  lines={["Shelf-life modelling,", "with the evidence attached."]}
                />
              </h1>

              <Reveal immediate delay={0.18}>
                <p className="type-lede mx-auto mt-6 max-w-[600px] text-muted-foreground">
                  Model how formulation, packaging and storage change cheese shelf
                  life — and see exactly where the model holds up and where it
                  doesn&apos;t.
                </p>
              </Reveal>

              <Reveal immediate delay={0.26}>
                <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
                  <Link href="/signup" className={buttonVariants({ size: "xl", variant: "contrast" })}>
                    Get started
                    <ArrowRight className="size-4" />
                  </Link>
                  <a
                    href="#platform"
                    className={buttonVariants({ size: "xl", variant: "outline" })}
                  >
                    See the platform
                  </a>
                </div>
              </Reveal>
            </div>

            <Reveal immediate delay={0.34} y={30}>
              <div className="relative mx-auto mt-20 max-w-[1000px]">
                <ProductFrame
                  label="Shelf-Life Studio — Results"
                  className="edge-highlight relative shadow-[0_40px_120px_-20px_rgba(0,0,0,0.7)]"
                  contentClassName="grid gap-px bg-border sm:grid-cols-2"
                >
                  <div className="bg-card">
                    <ComparisonPreview />
                  </div>
                  <div className="bg-card">
                    <LeaderboardPreview />
                  </div>
                </ProductFrame>
                {/* Fade the frame into the page rather than ending on a hard edge. */}
                <div
                  aria-hidden
                  className="pointer-events-none absolute inset-x-0 -bottom-px h-32 bg-gradient-to-t from-canvas to-transparent"
                />
              </div>
            </Reveal>
          </div>
        </section>

        {/* ── Stats ────────────────────────────────────────────────────── */}
        <section className="border-y border-border px-5 py-12 sm:px-7">
          <div className="mx-auto grid w-full max-w-[1180px] grid-cols-2 gap-y-10 sm:grid-cols-4">
            {[
              { value: "30,500", label: "Training rows" },
              { value: "6,100", label: "Formulation contexts" },
              { value: "4", label: "Trained models" },
              { value: "70/15/15", label: "Grouped split" },
            ].map((stat, i) => (
              <Reveal key={stat.label} delay={i * 0.06} className="text-center">
                <p className="numeral text-[1.75rem] leading-none font-medium tracking-[-0.03em] text-foreground">
                  {stat.value}
                </p>
                <p className="type-caption mt-2 text-subtle-foreground">{stat.label}</p>
              </Reveal>
            ))}
          </div>
        </section>

        {/* ── Capabilities ─────────────────────────────────────────────── */}
        <section id="platform" className="scroll-mt-20 px-5 py-28 sm:px-7 sm:py-36">
          <div className="mx-auto w-full max-w-[1180px]">
            <div className="max-w-[640px]">
              <Reveal>
                <p className="type-eyebrow text-primary">Platform</p>
              </Reveal>
              <h2 className="type-section mt-4 text-foreground">
                <RevealLines lines={["Everything the workflow", "actually needs."]} />
              </h2>
              <Reveal delay={0.12}>
                <p className="type-lede mt-5 text-muted-foreground">
                  Built around how shelf-life studies are really run: a formulation, a
                  control, a spoilage indicator, and a question about whether a treatment
                  meaningfully extends the result.
                </p>
              </Reveal>
            </div>

            <div className="mt-16 grid gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
              {CAPABILITIES.map((item, i) => (
                <Reveal key={item.title} delay={(i % 3) * 0.07} className="bg-card">
                  <div className="group flex h-full flex-col gap-3.5 p-7 transition-colors hover:bg-elevated">
                    <item.icon className="size-4 text-primary" strokeWidth={1.75} />
                    <h3 className="type-title text-foreground">{item.title}</h3>
                    <p className="type-ui leading-relaxed text-muted-foreground">{item.body}</p>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        {/* ── Pipeline ─────────────────────────────────────────────────── */}
        <section
          id="pipeline"
          className="relative scroll-mt-20 border-y border-border px-5 py-28 sm:px-7 sm:py-36"
        >
          <div className="mx-auto w-full max-w-[1180px]">
            <div className="max-w-[640px]">
              <Reveal>
                <p className="type-eyebrow text-primary">Pipeline</p>
              </Reveal>
              <h2 className="type-section mt-4 text-foreground">
                <RevealLines lines={["From workbook", "to served prediction."]} />
              </h2>
              <Reveal delay={0.12}>
                <p className="type-lede mt-5 text-muted-foreground">
                  Training is a deliberate, inspectable sequence. Nothing is retrained at
                  request time — the API loads saved artifacts once and serves from them.
                </p>
              </Reveal>
            </div>

            <PipelineScroller />
          </div>
        </section>

        {/* ── Explainability ───────────────────────────────────────────── */}
        <section className="px-5 py-28 sm:px-7 sm:py-36">
          <div className="mx-auto grid w-full max-w-[1180px] items-center gap-14 lg:grid-cols-2 lg:gap-24">
            <div>
              <Reveal>
                <p className="type-eyebrow text-primary">Explainability</p>
              </Reveal>
              <h2 className="type-section mt-4 text-foreground">
                <RevealLines lines={["A number is not", "an answer."]} />
              </h2>
              <Reveal delay={0.12}>
                <p className="type-lede mt-5 text-muted-foreground">
                  Every prediction decomposes into the features that drove it. The
                  Explainable Boosting Machine exposes its additive shape functions
                  directly; tree models substitute each feature with its training reference
                  value and measure the shift.
                </p>
              </Reveal>
              <Reveal delay={0.18}>
                <ul className="mt-7 flex flex-col gap-3">
                  {[
                    "Global importance, native and permutation-based",
                    "Local attribution for any single prediction",
                    "EBM shape functions for the top terms",
                  ].map((line) => (
                    <li key={line} className="flex items-start gap-3">
                      <span className="mt-[7px] size-1 shrink-0 rounded-full bg-primary" />
                      <span className="type-body text-muted-foreground">{line}</span>
                    </li>
                  ))}
                </ul>
              </Reveal>
            </div>

            <Reveal delay={0.1} y={24}>
              <ProductFrame
                label="Explainability — local attribution"
                className="edge-highlight shadow-[0_30px_80px_-24px_rgba(0,0,0,0.6)]"
                contentClassName="bg-card"
              >
                <ExplainPreview />
              </ProductFrame>
            </Reveal>
          </div>
        </section>

        {/* ── Research context ────────────────────────────────────────── */}
        <section id="research" className="scroll-mt-20 px-5 py-28 sm:px-7 sm:py-36">
          <div className="mx-auto w-full max-w-[1180px]">
            <div className="max-w-[640px]">
              <Reveal>
                <p className="type-eyebrow text-primary">Research context</p>
              </Reveal>
              <h2 className="type-section mt-4 text-foreground">
                <RevealLines lines={["Built inside a", "food-science programme."]} />
              </h2>
              <Reveal delay={0.12}>
                <p className="type-lede mt-5 text-muted-foreground">
                  The platform supports preservation research — comparing antimicrobial and
                  antioxidant interventions across cheese matrices under controlled storage,
                  with provenance tracked for every row that informs a model.
                </p>
              </Reveal>
            </div>

            <Reveal delay={0.14} y={22}>
              <figure className="mt-14">
                <EditorialImage
                  src="/marketing/research-banner.png"
                  caption="Macdonald Campus — research life"
                  className="aspect-[1900/351] w-full rounded-xl border border-border"
                  priority
                />
              </figure>
            </Reveal>

            <Reveal delay={0.2} y={22}>
              <div className="edge-highlight surface mt-8 grid overflow-hidden sm:grid-cols-[300px_1fr]">
                <EditorialImage
                  src="/marketing/karboune.jpg"
                  caption="Dr. Salwa Karboune"
                  className="aspect-[4/3] sm:aspect-auto"
                />
                <div className="flex flex-col justify-center p-7 sm:p-9">
                  <p className="type-eyebrow text-primary">Faculty lead</p>
                  <h3 className="type-h3 mt-3 text-foreground">Dr. Salwa Karboune</h3>
                  <p className="type-ui mt-1 text-muted-foreground">
                    Department of Food Science and Agricultural Chemistry, McGill University
                  </p>
                  <p className="type-body mt-4 max-w-[46ch] leading-relaxed text-muted-foreground">
                    Developed within her research group at Macdonald Campus, supporting ongoing
                    work in food preservation and shelf-life science.
                  </p>
                </div>
              </div>
            </Reveal>
          </div>
        </section>

        <section className="border-y border-border px-5 py-28 sm:px-7 sm:py-36">
          <div className="mx-auto grid w-full max-w-[1180px] gap-6 sm:grid-cols-2">
            <Reveal y={22}>
              <figure>
                <EditorialImage
                  src="/marketing/cheese-aging.jpg"
                  caption="Cheese ripening cellar"
                  className="aspect-[4/3] rounded-xl border border-border"
                />
                <figcaption className="type-caption mt-3 text-subtle-foreground">
                  Ripening conditions drive the matrix descriptors the models read.
                </figcaption>
              </figure>
            </Reveal>
            <Reveal delay={0.08} y={22}>
              <figure>
                <EditorialImage
                  src="/marketing/lab.jpg"
                  caption="Microbiology laboratory"
                  className="aspect-[4/3] rounded-xl border border-border"
                />
                <figcaption className="type-caption mt-3 text-subtle-foreground">
                  Spoilage indicators define when shelf life ends.
                </figcaption>
              </figure>
            </Reveal>
          </div>
        </section>

        {/* ── Validation ───────────────────────────────────────────────── */}
        <section id="validation" className="scroll-mt-20 px-5 py-28 sm:px-7 sm:py-36">
          <div className="mx-auto grid w-full max-w-[1180px] items-center gap-14 lg:grid-cols-2 lg:gap-24">
            <Reveal y={24} className="order-2 lg:order-1">
              <ProductFrame
                label="Modeling — error breakdown"
                className="edge-highlight shadow-[0_30px_80px_-24px_rgba(0,0,0,0.6)]"
                contentClassName="bg-card"
              >
                <CategoryErrorPreview />
              </ProductFrame>
            </Reveal>

            <div className="order-1 lg:order-2">
              <Reveal>
                <p className="type-eyebrow text-primary">Validation</p>
              </Reveal>
              <h2 className="type-section mt-4 text-foreground">
                <RevealLines lines={["Designed to show", "where it fails."]} />
              </h2>
              <Reveal delay={0.12}>
                <p className="type-lede mt-5 text-muted-foreground">
                  A single headline accuracy number hides more than it reveals. Error is
                  reported by cheese category, food matrix, spoilage indicator and
                  control-versus-treatment, so a model that performs well overall but
                  poorly on one category cannot pass unnoticed.
                </p>
              </Reveal>
              <Reveal delay={0.18}>
                <div className="mt-7 rounded-xl border border-border bg-card p-5">
                  <p className="type-ui leading-relaxed text-muted-foreground">
                    <span className="font-medium text-foreground">Current status.</span>{" "}
                    Models train on a synthetic, literature-constrained corpus. External
                    validation against published studies shows strong agreement for soft
                    cheeses and substantial over-prediction for hard and semi-hard cheeses.
                    Those results are reported in the workspace rather than smoothed over.
                  </p>
                </div>
              </Reveal>
            </div>
          </div>
        </section>

        {/* ── Closing ──────────────────────────────────────────────────── */}
        <section className="relative border-t border-border px-5 py-28 sm:px-7 sm:py-36">
          <div
            aria-hidden
            className="hero-glow pointer-events-none absolute inset-x-0 -bottom-32 h-[380px] opacity-45"
          />
          <div className="relative mx-auto w-full max-w-[1180px] text-center">
            <Reveal>
              <h2 className="type-section mx-auto max-w-[18ch] text-foreground">
                Start modelling in your own workspace.
              </h2>
            </Reveal>
            <Reveal delay={0.1}>
              <p className="type-lede mx-auto mt-5 max-w-[46ch] text-muted-foreground">
                Create an account to run predictions, compare treatments and inspect the
                trained models.
              </p>
            </Reveal>
            <Reveal delay={0.16}>
              <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
                <Link href="/signup" className={buttonVariants({ size: "xl", variant: "contrast" })}>
                  Create an account
                  <ArrowRight className="size-4" />
                </Link>
                <Link
                  href="/login"
                  className={buttonVariants({ size: "xl", variant: "outline" })}
                >
                  Log in
                </Link>
              </div>
            </Reveal>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
