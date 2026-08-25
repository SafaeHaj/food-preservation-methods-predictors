"use client";

import * as React from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

import { usePredictionV6, type FlowStep } from "@/components/prediction-v6-store";
import { CheeseSearchStep } from "@/components/prediction-v6/cheese-search-step";
import { PhysicalFormStep } from "@/components/prediction-v6/physical-form-step";
import { ProfileConfirmationStep } from "@/components/prediction-v6/profile-confirmation-step";
import { PredictionConditionsStep } from "@/components/prediction-v6/prediction-conditions-step";
import { PredictionV6Result } from "@/components/prediction-v6/prediction-v6-result";
import type { CheeseCatalog } from "@/lib/api";
import { cn } from "@/lib/utils";

const EASE = [0.16, 1, 0.3, 1] as const;

const STEPS: { key: FlowStep; label: string }[] = [
  { key: "cheese", label: "Cheese" },
  { key: "form", label: "Presentation" },
  { key: "profile", label: "Profile" },
  { key: "conditions", label: "Conditions" },
  { key: "results", label: "Results" },
];

function ProgressIndicator({ current }: { current: FlowStep }) {
  const currentIndex = STEPS.findIndex((s) => s.key === current);
  return (
    <div className="mx-auto mb-2 flex w-full max-w-md items-center justify-center gap-1.5">
      {STEPS.map((step, i) => (
        <React.Fragment key={step.key}>
          <div className="flex flex-col items-center gap-1.5">
            <motion.span
              animate={{
                scale: i === currentIndex ? 1.15 : 1,
                backgroundColor: i <= currentIndex ? "var(--primary)" : "var(--border)",
              }}
              transition={{ duration: 0.3, ease: EASE }}
              className="block size-1.5 rounded-full"
            />
          </div>
          {i < STEPS.length - 1 && (
            <div className="h-px w-6 sm:w-10">
              <motion.div
                className="h-full bg-primary"
                initial={false}
                animate={{ scaleX: i < currentIndex ? 1 : 0 }}
                style={{ transformOrigin: "left" }}
                transition={{ duration: 0.35, ease: EASE }}
              />
              <div className="-mt-px h-full bg-border" style={{ opacity: i < currentIndex ? 0 : 1 }} />
            </div>
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

const stepVariants = {
  initial: { opacity: 0, x: 16 },
  animate: { opacity: 1, x: 0 },
  exit: { opacity: 0, x: -16 },
};

export function PredictionV6Flow({ catalog }: { catalog: CheeseCatalog }) {
  const { state } = usePredictionV6();
  const reduce = useReducedMotion();

  return (
    <div>
      {state.step !== "cheese" && <ProgressIndicator current={state.step} />}
      <AnimatePresence mode="wait">
        <motion.div
          key={state.step}
          initial={reduce ? false : stepVariants.initial}
          animate={stepVariants.animate}
          exit={reduce ? undefined : stepVariants.exit}
          transition={{ duration: 0.28, ease: EASE }}
          className={cn(state.step === "cheese" && "min-h-[60vh]")}
        >
          {state.step === "cheese" && <CheeseSearchStep catalog={catalog} />}
          {state.step === "form" && <PhysicalFormStep />}
          {state.step === "profile" && <ProfileConfirmationStep />}
          {state.step === "conditions" && <PredictionConditionsStep />}
          {state.step === "results" && <PredictionV6Result />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
