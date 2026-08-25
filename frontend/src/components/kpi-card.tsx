"use client";

import * as React from "react";
import { animate, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

function useCountUp(target: number, enabled: boolean, decimals = 0) {
  const [value, setValue] = React.useState(enabled ? 0 : target);
  const reduceMotion = useReducedMotion();

  React.useEffect(() => {
    if (!enabled || reduceMotion) {
      setValue(target);
      return;
    }
    const controls = animate(0, target, {
      duration: 0.6,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setValue(v),
    });
    return () => controls.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, enabled]);

  return decimals > 0 ? value.toFixed(decimals) : Math.round(value).toLocaleString();
}

export function KpiCard({
  label,
  value,
  numericValue,
  decimals = 0,
  suffix = "",
  icon,
  sub,
  tone = "default",
  animateIn = false,
}: {
  label: string;
  value?: string;
  numericValue?: number;
  decimals?: number;
  suffix?: string;
  /** Pass an already-rendered icon element, e.g. `<Database className="h-4 w-4" />`
   * -- NOT the bare component reference. A bare function/component reference
   * can't cross the Server -> Client boundary (this card animates, so it must
   * be a Client Component), but a resolved element can. */
  icon: React.ReactNode;
  sub?: string;
  tone?: "default" | "primary" | "success" | "warning";
  animateIn?: boolean;
}) {
  const counted = useCountUp(numericValue ?? 0, numericValue !== undefined && animateIn, decimals);
  const display = value ?? (numericValue !== undefined ? `${counted}${suffix}` : "—");

  // Tone tints the icon chip. The panel itself stays neutral so a row of
  // metrics reads as one set rather than as competing coloured blocks.
  const chipTone: Record<string, string> = {
    default: "bg-muted text-subtle-foreground",
    primary: "bg-primary/15 text-primary",
    success: "bg-success/15 text-success",
    warning: "bg-warning/15 text-warning",
  };

  return (
    <div className="surface-interactive group flex h-full flex-col p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="type-eyebrow text-subtle-foreground">{label}</span>
        <span
          className={cn(
            "flex size-7 shrink-0 items-center justify-center rounded-md transition-transform duration-300 group-hover:scale-110 [&_svg]:size-3.5",
            chipTone[tone],
          )}
          aria-hidden="true"
        >
          {icon}
        </span>
      </div>
      <div className="numeral mt-2.5 text-[1.625rem] leading-none font-semibold text-foreground">
        {display}
      </div>
      {sub && <div className="type-caption mt-1.5 text-muted-foreground">{sub}</div>}
    </div>
  );
}
