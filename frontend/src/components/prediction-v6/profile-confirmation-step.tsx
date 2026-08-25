"use client";

import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, Sparkles } from "lucide-react";

import { usePredictionV6 } from "@/components/prediction-v6-store";
import { titleCase, IMAGES } from "@/components/prediction-v6/cheese-search-step";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

const EASE = [0.16, 1, 0.3, 1] as const;

const CATEGORY_LABEL: Record<string, string> = { soft: "Soft", semi_hard: "Semi-hard", hard: "Hard" };

const FORM_EFFECT_NOTES: Record<string, string> = {
  shredded: "Shredding increases exposed surface area and may influence oxygen exposure, moisture loss and microbial behavior.",
  grated: "Fine division increases exposed surface area, which can accelerate moisture loss and oxidation.",
  sliced: "Slicing increases exposed surface relative to a whole piece, moderately affecting moisture loss.",
  spread: "A spreadable format has a very different moisture and surface profile from a solid block.",
  crumbled: "Crumbling substantially increases surface area and typically shortens practical shelf life.",
  cubed: "Cubing increases exposed surface area relative to a whole block.",
};

const SUPPORT_BADGE_VARIANT: Record<string, "success" | "info" | "warning" | "destructive"> = {
  strong: "success",
  moderate: "info",
  limited: "warning",
  experimental: "destructive",
  unsupported: "destructive",
};

function formLabel(form: string): string {
  return form.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function ProfileConfirmationStep() {
  const { state, dispatch } = usePredictionV6();
  const reduce = useReducedMotion();
  const [loading, setLoading] = React.useState(false);
  const { baseCheeseName, entry, physicalForm, physicalFormOption } = state;

  if (!baseCheeseName || !entry || !physicalForm || !physicalFormOption) return null;

  const displayName = titleCase(baseCheeseName);
  const image = IMAGES[baseCheeseName];
  const effectNote = FORM_EFFECT_NOTES[physicalForm];

  async function handleContinue() {
    if (!entry) return;
    setLoading(true);
    try {
      const [general, safety] = await Promise.all([
        api.schemaV6(entry.cheeseCategory, "general_shelf_life"),
        api.schemaV6(entry.cheeseCategory, "safety_endpoint").catch(() => null),
      ]);
      dispatch({ type: "setSchemas", general, safety });
      dispatch({ type: "goto", step: "conditions" });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl pt-8 pb-20">
      <motion.div
        initial={reduce ? false : { opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: EASE }}
        className="overflow-hidden rounded-2xl border border-border bg-card/92 backdrop-blur-xl"
      >
        <div className="flex items-center gap-4 border-b border-border p-5">
          <div className="flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-muted">
            {image ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={image.thumbUrl} alt="" className="size-full object-cover" />
            ) : (
              <span className="type-h3 text-subtle-foreground/50">{displayName.charAt(0)}</span>
            )}
          </div>
          <div>
            <h1 className="type-h2 text-foreground">
              {displayName} <span className="text-muted-foreground">&mdash;</span> {formLabel(physicalForm)}
            </h1>
          </div>
        </div>

        <div className="p-5">
          <p className="type-body text-muted-foreground">
            We identify this product as a <span className="font-medium text-foreground">{CATEGORY_LABEL[entry.cheeseCategory].toLowerCase()}</span> cheese in{" "}
            <span className="font-medium text-foreground">{formLabel(physicalForm).toLowerCase()}</span> form.
            {effectNote ? ` ${effectNote}` : " Its physical presentation is one of several factors that will be considered in the prediction."}
          </p>

          <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <ProfileField label="Base cheese" value={displayName} />
            <ProfileField label="Category" value={CATEGORY_LABEL[entry.cheeseCategory]} />
            <ProfileField label="Physical form" value={formLabel(physicalForm)} />
            <ProfileField label="Prediction route" value={`${CATEGORY_LABEL[entry.cheeseCategory]} specialist`} />
            <div className="space-y-1">
              <div className="type-caption text-muted-foreground">Training support</div>
              <Badge variant={SUPPORT_BADGE_VARIANT[physicalFormOption.support.level] ?? "outline"}>{physicalFormOption.support.label}</Badge>
            </div>
          </div>

          <p className="type-caption mt-4 flex items-start gap-1.5 text-muted-foreground">
            <Sparkles className="mt-0.5 size-3 shrink-0 text-primary" />
            {physicalFormOption.support.explanation}
          </p>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-border bg-muted/30 p-5">
          <div className="flex gap-4">
            <button type="button" onClick={() => dispatch({ type: "changeCheese" })} className="type-caption text-muted-foreground transition-colors hover:text-foreground">
              Change cheese
            </button>
            <button type="button" onClick={() => dispatch({ type: "changePresentation" })} className="type-caption text-muted-foreground transition-colors hover:text-foreground">
              Change presentation
            </button>
          </div>
          <Button onClick={handleContinue} disabled={loading}>
            {loading ? "Loading…" : "Continue"} <ArrowRight className="size-3.5" />
          </Button>
        </div>
      </motion.div>
    </div>
  );
}

function ProfileField({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <div className="type-caption text-muted-foreground">{label}</div>
      <div className="type-ui font-medium text-foreground">{value}</div>
    </div>
  );
}
