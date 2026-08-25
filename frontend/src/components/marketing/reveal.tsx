"use client";

import * as React from "react";
import { motion, useInView, useReducedMotion } from "framer-motion";

import { cn } from "@/lib/utils";

const EASE = [0.16, 1, 0.3, 1] as const;

/**
 * Drives entrance animations from an explicit IntersectionObserver rather than
 * framer's `whileInView`.
 *
 * `whileInView` proved unreliable here: elements already intersecting at mount
 * never received an enter transition, so headings stayed pinned at their
 * `initial` transform and rendered invisible inside their overflow-hidden
 * masks. Reading visibility ourselves and driving `animate` means an element
 * that is already on screen animates immediately, and one below the fold
 * animates when it arrives.
 */
function useReveal(immediate: boolean) {
  const ref = React.useRef<HTMLElement | null>(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });
  return { ref, shown: immediate || inView };
}

export function Reveal({
  children,
  delay = 0,
  y = 16,
  immediate = false,
  className,
}: {
  children: React.ReactNode;
  delay?: number;
  y?: number;
  /** Skip the observer and animate on mount — for above-the-fold content. */
  immediate?: boolean;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const { ref, shown } = useReveal(immediate);

  if (reduce) return <div className={className}>{children}</div>;

  return (
    <motion.div
      ref={ref as React.Ref<HTMLDivElement>}
      initial={{ opacity: 0, y }}
      animate={shown ? { opacity: 1, y: 0 } : { opacity: 0, y }}
      transition={{ duration: 0.6, delay, ease: EASE }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/**
 * Reveals a heading one line at a time. Pass pre-split lines rather than a
 * sentence — splitting on words would let a line break mid-phrase and stagger
 * the fragments independently, which reads as a glitch.
 */
export function RevealLines({
  lines,
  className,
  lineClassName,
  delay = 0,
  immediate = false,
}: {
  lines: React.ReactNode[];
  className?: string;
  lineClassName?: string;
  delay?: number;
  immediate?: boolean;
}) {
  const reduce = useReducedMotion();
  const { ref, shown } = useReveal(immediate);

  return (
    <span ref={ref as React.Ref<HTMLSpanElement>} className={cn("block", className)}>
      {lines.map((line, i) => (
        <span key={i} className={cn("block overflow-hidden pb-[0.08em]", lineClassName)}>
          {reduce ? (
            <span className="block">{line}</span>
          ) : (
            <motion.span
              className="block"
              initial={{ y: "110%" }}
              animate={shown ? { y: "0%" } : { y: "110%" }}
              transition={{ duration: 0.8, delay: delay + i * 0.09, ease: EASE }}
            >
              {line}
            </motion.span>
          )}
        </span>
      ))}
    </span>
  );
}

export { motion as m };
