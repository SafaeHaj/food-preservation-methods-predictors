"use client";

import Link from "next/link";
import { FlaskConical } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";

const EASE = [0.16, 1, 0.3, 1] as const;

/**
 * Shared frame for /login and /signup. The shared `<Ambience/>` (mounted once
 * in the root layout) supplies the aurora/grid/grain behind this screen — the
 * same living background the landing page uses — so arriving here after the
 * marketing site never feels like hitting a different, unfinished product.
 */
export function AuthShell({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  const reduce = useReducedMotion();
  return (
    // overflow-x-clip: the halo glow behind the card intentionally overhangs
    // it by design (see below) and can exceed a narrow viewport by a few
    // pixels; clip here so it never creates a page-level horizontal scrollbar.
    <main className="relative flex min-h-svh flex-col items-center justify-center overflow-x-clip px-5 py-12">
      <motion.div
        initial={reduce ? false : { opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EASE }}
        className="relative w-full max-w-[400px]"
      >
        <Link
          href="/"
          className="mb-9 flex items-center justify-center gap-2.5 rounded-sm outline-none focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring"
        >
          <span className="flex size-7 items-center justify-center rounded-lg bg-primary shadow-[0_0_24px_-4px_color-mix(in_srgb,var(--primary)_70%,transparent)]">
            <FlaskConical className="size-4 text-primary-foreground" />
          </span>
          <span className="type-title text-[0.9375rem] text-foreground">Shelf-Life Studio</span>
        </Link>

        {/* Soft halo behind the card — the detail that keeps a dark card from
            reading as a flat rectangle dropped onto the aurora. */}
        <div
          aria-hidden
          className="pointer-events-none absolute -inset-6 -z-10 rounded-[2rem] bg-[radial-gradient(closest-side,color-mix(in_srgb,var(--primary)_16%,transparent),transparent)] opacity-70 blur-2xl"
        />

        <div className="surface p-7 shadow-lg">
          <div className="mb-6">
            <h1 className="type-h3 text-foreground">{title}</h1>
            <p className="type-ui mt-1.5 text-muted-foreground">{description}</p>
          </div>
          {children}
        </div>

        <p className="type-ui mt-6 text-center text-muted-foreground">{footer}</p>
      </motion.div>
    </main>
  );
}
