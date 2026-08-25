"use client";

import * as React from "react";
import { motion, useInView, useReducedMotion } from "framer-motion";

import { cn } from "@/lib/utils";

const EASE = [0.16, 1, 0.3, 1] as const;

/**
 * The page frame every app screen uses. Keeps max width, gutters and vertical
 * rhythm identical across screens so navigating between them doesn't shift the
 * content column.
 */
export function PageBody({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: EASE }}
      // overflow-x-clip: some panels (e.g. the prediction summary) place a
      // deliberately-overhanging halo glow behind themselves; clip at the
      // page level so that can never create a page-level horizontal scrollbar.
      className={cn("mx-auto w-full max-w-[1180px] overflow-x-clip px-5 pt-6 pb-20 sm:px-7", className)}
    >
      {children}
    </motion.div>
  );
}

/**
 * Compact page header — a title line with optional description and actions.
 * Deliberately short: it should orient, not occupy a third of the viewport.
 */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  const reduce = useReducedMotion();
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-3 border-b border-border pb-5">
      <div className="min-w-0">
        {/* Short accent rule that draws itself in — a quiet signal that the
            page starts here, without spending a whole band on a header. */}
        <motion.span
          aria-hidden
          initial={reduce ? false : { scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: 0.5, ease: EASE, delay: 0.05 }}
          className="mb-3 block h-[2px] w-8 origin-left rounded-full bg-primary"
        />
        <motion.h1
          initial={reduce ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: EASE }}
          className="type-h1 text-foreground"
        >
          {title}
        </motion.h1>
        {description && (
          <motion.p
            initial={reduce ? false : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: EASE, delay: 0.06 }}
            className="type-body mt-2 max-w-[68ch] text-muted-foreground"
          >
            {description}
          </motion.p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

/** A labelled band within a page. The rule sits under the label, not around
 *  the content, so sections read as one document rather than stacked cards. */
export function Section({
  title,
  description,
  actions,
  children,
  className,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("flex flex-col", className)}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2 border-b border-border pb-2">
        <div className="min-w-0">
          <h2 className="type-title text-foreground">{title}</h2>
          {description && (
            <p className="type-caption mt-0.5 text-muted-foreground">{description}</p>
          )}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

/**
 * Staggered entrance for a grid of sibling panels. Lays out as a grid by
 * default — call sites pass only the responsive column classes
 * (e.g. `sm:grid-cols-2 lg:grid-cols-4`), so the display and gap must come
 * from here or the children stack as blocks.
 */
export function Stagger({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const reduce = useReducedMotion();
  return (
    <div className={cn("grid gap-3", className)}>
      {React.Children.map(children, (child, i) => (
        <motion.div
          initial={reduce ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.24, delay: i * 0.035, ease: EASE }}
        >
          {child}
        </motion.div>
      ))}
    </div>
  );
}

/**
 * Reveals its children the first time they scroll into view, once, so long
 * analytical screens unfold instead of arriving all at once.
 *
 * Uses an explicit `useInView` observer rather than framer's `whileInView`:
 * the latter never fires an enter transition for elements already intersecting
 * at mount, which left anything above the fold stuck at its `initial` opacity.
 */
export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();
  const ref = React.useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });

  if (reduce) return <div className={className}>{children}</div>;

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 12 }}
      animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 12 }}
      transition={{ duration: 0.45, delay, ease: EASE }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/** Small uppercase eyebrow with a trailing rule, for breaking a long screen
 *  into scannable bands without adding heavy chrome. */
export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center gap-2.5">
      <span className="type-eyebrow text-subtle-foreground">{children}</span>
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}

/** Shown when a screen has nothing to display yet — always paired with the
 *  action that would populate it. */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border px-6 py-14 text-center">
      {icon && <div className="text-subtle-foreground">{icon}</div>}
      <div>
        <p className="type-title text-foreground">{title}</p>
        {description && (
          <p className="type-ui mx-auto mt-1 max-w-[46ch] text-muted-foreground">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}
