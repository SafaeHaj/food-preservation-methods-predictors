"use client";

import * as React from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowLeft, Layers, ShieldCheck } from "lucide-react";

import { usePredictionV6 } from "@/components/prediction-v6-store";
import { titleCase, IMAGES } from "@/components/prediction-v6/cheese-search-step";
import { Badge } from "@/components/ui/badge";
import type { PhysicalFormOption } from "@/lib/api";
import { cn } from "@/lib/utils";

const EASE = [0.16, 1, 0.3, 1] as const;

const CATEGORY_LABEL: Record<string, string> = { soft: "Soft", semi_hard: "Semi-hard", hard: "Hard" };
const CATEGORY_BLURB: Record<string, string> = {
  soft: "Soft cheeses generally have higher moisture and shorter shelf lives, more sensitive to storage temperature and packaging.",
  semi_hard: "Semi-hard cheeses sit between soft and hard in moisture and typical shelf life, with behavior shaped strongly by ripening and packaging.",
  hard: "Hard cheeses are typically lower-moisture and longer-lived, with physical presentation and ripening playing an outsized role.",
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

const FORM_DESCRIPTIONS: Record<string, string> = {
  block: "Whole piece, uncut",
  shredded: "High exposed surface area",
  sliced: "Portioned presentation",
  grated: "Finely divided",
  spread: "Soft, spreadable consistency",
  crumbled: "Broken into small pieces",
  cubed: "Cut into cubes",
  wheel: "Traditional whole wheel",
  whole_wheel: "Whole, unopened wheel",
  wheel_or_block: "Whole or block form",
  wheel_or_wedge: "Whole wheel or cut wedge",
  brined_block: "Stored and sold in brine",
  fresh_ball: "Fresh, ball-shaped portion",
  fresh_mass: "Unshaped fresh curd mass",
  fresh_whole: "Whole fresh piece",
  curd: "Fresh curd form",
  log: "Log-shaped format",
  whole_log_or_wheel: "Whole log or wheel format",
  whole_soft: "Whole soft-ripened piece",
  whole_unspecified_shape: "Whole piece, shape unspecified",
  processed_block_or_slice: "Processed block or pre-sliced",
  ripened_whole: "Whole, fully ripened piece",
};

export function PhysicalFormStep() {
  const { state, dispatch } = usePredictionV6();
  const reduce = useReducedMotion();
  const { baseCheeseName, entry } = state;

  if (!baseCheeseName || !entry) return null;

  const image = IMAGES[baseCheeseName];
  const displayName = titleCase(baseCheeseName);

  return (
    <div className="mx-auto max-w-3xl pt-8 pb-20">
      <button
        type="button"
        onClick={() => dispatch({ type: "changeCheese" })}
        className="type-caption mb-6 inline-flex items-center gap-1.5 text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="size-3.5" /> Change cheese
      </button>

      <motion.div
        initial={reduce ? false : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: EASE }}
        className="flex items-center gap-4"
      >
        <div className="flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-muted">
          {image ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={image.thumbUrl} alt="" className="size-full object-cover" />
          ) : (
            <span className="type-h3 text-subtle-foreground/50">{displayName.charAt(0)}</span>
          )}
        </div>
        <div>
          <h1 className="type-h2 text-foreground">{displayName}</h1>
          <p className="type-body mt-1 text-muted-foreground">
            We classify {displayName} as a <span className="font-medium text-foreground">{CATEGORY_LABEL[entry.cheeseCategory].toLowerCase()}</span> cheese.
          </p>
        </div>
      </motion.div>

      <motion.p
        initial={reduce ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: EASE, delay: 0.08 }}
        className="type-ui mt-4 max-w-xl text-muted-foreground"
      >
        {CATEGORY_BLURB[entry.cheeseCategory]} Its composition, storage behavior and physical presentation will determine which prediction path is used.
      </motion.p>

      <motion.div
        initial={reduce ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: EASE, delay: 0.14 }}
        className="mt-5 flex flex-wrap gap-2"
      >
        <ProfileChip label="Cheese" value={displayName} />
        <ProfileChip label="Category" value={CATEGORY_LABEL[entry.cheeseCategory]} />
        <ProfileChip label="Specialist model" value={`${CATEGORY_LABEL[entry.cheeseCategory]} cheese model`} icon={<ShieldCheck className="size-3 text-primary" />} />
      </motion.div>

      <motion.div
        initial={reduce ? false : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: EASE, delay: 0.2 }}
        className="mt-10"
      >
        <div className="mb-4 flex items-center gap-2.5">
          <span className="flex size-7 items-center justify-center rounded-md bg-primary/12 text-primary">
            <Layers className="size-3.5" />
          </span>
          <h2 className="type-title text-foreground">How is your {displayName.toLowerCase()} presented?</h2>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {entry.physicalForms.map((option, i) => (
            <FormCard key={option.physicalForm} option={option} index={i} onSelect={() => dispatch({ type: "selectPhysicalForm", option })} />
          ))}
        </div>
      </motion.div>
    </div>
  );
}

function ProfileChip({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border bg-secondary/40 px-3 py-1.5">
      {icon}
      <span className="type-caption text-muted-foreground">{label}</span>
      <span className="type-caption font-medium text-foreground">{value}</span>
    </div>
  );
}

function FormCard({ option, index, onSelect }: { option: PhysicalFormOption; index: number; onSelect: () => void }) {
  const reduce = useReducedMotion();
  return (
    <motion.button
      type="button"
      initial={reduce ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: EASE, delay: 0.05 * index }}
      whileHover={reduce ? undefined : { y: -2 }}
      onClick={onSelect}
      className={cn(
        "group flex flex-col items-start gap-2 rounded-xl border border-border bg-card/80 p-4 text-left transition-all duration-200",
        "hover:border-primary/40 hover:bg-card hover:shadow-[0_8px_24px_-10px_color-mix(in_srgb,var(--primary)_25%,transparent)]",
      )}
    >
      <div className="flex w-full items-start justify-between gap-2">
        <span className="type-ui font-semibold text-foreground">{formLabel(option.physicalForm)}</span>
        <Badge variant={SUPPORT_BADGE_VARIANT[option.support.level] ?? "outline"} size="sm">
          {option.support.label}
        </Badge>
      </div>
      <span className="type-caption text-muted-foreground">
        {FORM_DESCRIPTIONS[option.physicalForm] ?? "Physical presentation"}
      </span>
    </motion.button>
  );
}
