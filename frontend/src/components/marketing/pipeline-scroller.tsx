"use client";

import * as React from "react";
import { motion, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";

import { cn } from "@/lib/utils";

/**
 * The real training sequence from train_models.py, revealed as the section
 * scrolls. Numbering is used here because the pipeline genuinely is ordered —
 * step 2 cannot precede step 1 — not as decoration.
 */
const STEPS = [
  {
    title: "Load the workbook",
    body: "A single Excel source of 30,500 rows describing cheese formulations, storage conditions, treatments and the spoilage indicator tracked for each.",
    detail: "CHEESE_SHELF_LIFE_REVISED_READY_TO_TRAIN.xlsx",
  },
  {
    title: "Split by context, not by row",
    body: "Rows sharing a context_id — a formulation together with its control — are kept in the same split. Splitting them would leak the answer across the boundary.",
    detail: "70 / 15 / 15 · grouped · seed 42",
  },
  {
    title: "Select honest features",
    body: "Matrix chemistry, storage, packaging, treatment and indicator. Identifier and provenance columns are excluded, and an assertion fails the run if one leaks in.",
    detail: "28 features · 3 excluded identifier groups",
  },
  {
    title: "Train four models independently",
    body: "Random Forest, LightGBM, XGBoost and an Explainable Boosting Machine, each with its own preprocessing pipeline, early stopping where supported.",
    detail: "Ranked by validation RMSE",
  },
  {
    title: "Calibrate uncertainty",
    body: "A split-conformal residual quantile is computed on the validation set alone, giving every served prediction a 90% interval rather than a bare point estimate.",
    detail: "Split-conformal · 90% coverage",
  },
  {
    title: "Serve from saved artifacts",
    body: "The API loads the trained models, schema, metrics and lookups once at startup. Prediction requests never trigger training.",
    detail: "FastAPI · model_service.ModelService",
  },
];

export function PipelineScroller() {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();

  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start 0.75", "end 0.6"],
  });
  // Spring the rail so it trails the scroll slightly instead of tracking it
  // 1:1, which reads as mechanical.
  const railScale = useSpring(scrollYProgress, { stiffness: 120, damping: 26, mass: 0.4 });
  const railHeight = useTransform(railScale, (v) => `${Math.max(0, Math.min(1, v)) * 100}%`);

  return (
    <div ref={containerRef} className="relative mt-14 pl-8 sm:pl-12">
      {/* Track + progress rail */}
      <div aria-hidden className="absolute top-1 bottom-1 left-[3px] w-px bg-border sm:left-[7px]" />
      {!reduce && (
        <motion.div
          aria-hidden
          style={{ height: railHeight }}
          className="absolute top-1 left-[3px] w-px origin-top bg-primary sm:left-[7px]"
        />
      )}

      <ol className="flex flex-col gap-10 sm:gap-12">
        {STEPS.map((step, i) => (
          <PipelineStep key={step.title} index={i} {...step} />
        ))}
      </ol>
    </div>
  );
}

function PipelineStep({
  index,
  title,
  body,
  detail,
}: {
  index: number;
  title: string;
  body: string;
  detail: string;
}) {
  const reduce = useReducedMotion();
  const ref = React.useRef<HTMLLIElement>(null);
  const [active, setActive] = React.useState(false);

  React.useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      ([entry]) => entry.isIntersecting && setActive(true),
      { rootMargin: "-25% 0px -25% 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <li ref={ref} className="relative">
      <span
        aria-hidden
        className={cn(
          "absolute top-1 -left-8 size-[7px] rounded-full border-2 transition-colors duration-500 sm:-left-12 sm:size-[15px] sm:border-[3px]",
          active ? "border-primary bg-background" : "border-border bg-background",
        )}
      />
      <motion.div
        initial={reduce ? false : { opacity: 0, y: 14 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-100px" }}
        transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
        className="max-w-[620px]"
      >
        <div className="flex items-baseline gap-3">
          <span className="type-mono text-[0.6875rem] text-subtle-foreground">
            {String(index + 1).padStart(2, "0")}
          </span>
          <h3 className="type-h3 text-foreground">{title}</h3>
        </div>
        <p className="type-body mt-2 leading-relaxed text-muted-foreground">{body}</p>
        <p className="type-mono mt-2.5 text-[0.6875rem] text-subtle-foreground">{detail}</p>
      </motion.div>
    </li>
  );
}
