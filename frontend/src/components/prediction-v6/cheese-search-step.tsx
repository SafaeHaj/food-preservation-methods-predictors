"use client";

import * as React from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Search, ArrowRight } from "lucide-react";

import type { CheeseCatalog, CheeseCatalogEntry } from "@/lib/api";
import { usePredictionV6 } from "@/components/prediction-v6-store";
import cheeseImages from "@/data/cheese-images.json";
import { cn } from "@/lib/utils";

const EASE = [0.16, 1, 0.3, 1] as const;

type CheeseImageEntry = { imageUrl: string; thumbUrl: string; title: string; pageUrl: string; license: string };
const IMAGES = cheeseImages as unknown as Record<string, CheeseImageEntry | null>;

function titleCase(name: string): string {
  return name
    .split(" ")
    .map((w) => (w.length <= 3 && w === w.toLowerCase() && !["and", "the"].includes(w) ? w : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ")
    .replace(/\bAyib\b/, "Ayib");
}

const CATEGORY_LABEL: Record<string, string> = { soft: "Soft", semi_hard: "Semi-hard", hard: "Hard" };

export function CheeseSearchStep({ catalog }: { catalog: CheeseCatalog }) {
  const { dispatch } = usePredictionV6();
  const [query, setQuery] = React.useState("");
  const [focused, setFocused] = React.useState(false);
  const [activeIndex, setActiveIndex] = React.useState(0);
  const [disambiguating, setDisambiguating] = React.useState<{ name: string; entries: CheeseCatalogEntry[] } | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const reduce = useReducedMotion();

  const names = React.useMemo(() => Object.keys(catalog).sort(), [catalog]);

  const results = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return names.slice(0, 8);
    const starts = names.filter((n) => n.toLowerCase().startsWith(q));
    const contains = names.filter((n) => !n.toLowerCase().startsWith(q) && n.toLowerCase().includes(q));
    return [...starts, ...contains].slice(0, 8);
  }, [query, names]);

  React.useEffect(() => setActiveIndex(0), [query]);

  function selectCheese(name: string) {
    const entries = catalog[name];
    if (!entries || entries.length === 0) return;
    if (entries.length === 1) {
      dispatch({ type: "selectCheese", baseCheeseName: name, entry: entries[0] });
    } else {
      setDisambiguating({ name, entries });
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && results[activeIndex]) {
      e.preventDefault();
      selectCheese(results[activeIndex]);
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center pt-10 pb-20 text-center sm:pt-16">
      <motion.h1
        initial={reduce ? false : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EASE }}
        className="type-display text-foreground"
      >
        What cheese would you like to evaluate?
      </motion.h1>
      <motion.p
        initial={reduce ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: EASE, delay: 0.08 }}
        className="type-body mt-3 max-w-md text-muted-foreground"
      >
        Search our catalog of cheeses. We&rsquo;ll route your prediction to the right specialist model automatically.
      </motion.p>

      <motion.div
        initial={reduce ? false : { opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: EASE, delay: 0.16 }}
        className="relative mt-9 w-full"
      >
        <div
          className={cn(
            "relative flex items-center gap-3 rounded-2xl border bg-card/92 px-5 py-4 backdrop-blur-xl transition-all duration-300",
            focused ? "border-primary/50 shadow-[0_12px_40px_-12px_color-mix(in_srgb,var(--primary)_35%,transparent)]" : "border-border shadow-sm",
          )}
        >
          <Search className={cn("size-5 shrink-0 transition-colors", focused ? "text-primary" : "text-muted-foreground")} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setTimeout(() => setFocused(false), 150)}
            onKeyDown={handleKeyDown}
            placeholder="Search cheese…"
            className="type-h3 w-full bg-transparent text-foreground placeholder:text-muted-foreground/60 focus:outline-none"
            autoFocus
          />
        </div>

        <AnimatePresence>
          {focused && results.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.18, ease: EASE }}
              className="absolute top-[calc(100%+10px)] left-0 z-20 grid w-full grid-cols-2 gap-2 rounded-2xl border border-border bg-card/97 p-2.5 shadow-[0_20px_60px_-16px_rgb(0_0_0_/_0.25)] backdrop-blur-xl sm:grid-cols-3"
            >
              {results.map((name, i) => {
                const entries = catalog[name];
                const image = IMAGES[name];
                const categories = [...new Set(entries.map((e) => e.cheeseCategory))];
                return (
                  <button
                    key={name}
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => selectCheese(name)}
                    onMouseEnter={() => setActiveIndex(i)}
                    className={cn(
                      "group flex flex-col items-center gap-2 rounded-xl border border-transparent p-2.5 text-center transition-all duration-150",
                      i === activeIndex ? "border-border bg-secondary/60" : "hover:bg-secondary/40",
                    )}
                  >
                    <div className="flex size-16 items-center justify-center overflow-hidden rounded-lg bg-muted">
                      {image ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={image.thumbUrl} alt="" className="size-full object-cover transition-transform duration-300 group-hover:scale-105" loading="lazy" />
                      ) : (
                        <span className="type-h3 text-subtle-foreground/50">{name.charAt(0).toUpperCase()}</span>
                      )}
                    </div>
                    <div className="min-w-0">
                      <div className="type-caption truncate font-medium text-foreground">{titleCase(name)}</div>
                      <div className="type-caption mt-0.5 text-[10px] text-muted-foreground">
                        {categories.map((c) => CATEGORY_LABEL[c]).join(" / ")}
                      </div>
                    </div>
                  </button>
                );
              })}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      <AnimatePresence>
        {disambiguating && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            transition={{ duration: 0.25, ease: EASE }}
            className="mt-6 w-full rounded-2xl border border-border bg-card/92 p-5 text-left backdrop-blur-xl"
          >
            <p className="type-ui text-foreground">
              <span className="font-semibold">{titleCase(disambiguating.name)}</span> appears in more than one category in our data. Which did you mean?
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {disambiguating.entries.map((entry) => (
                <button
                  key={entry.cheeseCategory}
                  type="button"
                  onClick={() => dispatch({ type: "selectCheese", baseCheeseName: disambiguating.name, entry })}
                  className="flex items-center gap-2 rounded-lg border border-border bg-secondary/40 px-3.5 py-2 text-sm font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-secondary/70"
                >
                  {CATEGORY_LABEL[entry.cheeseCategory]}
                  <ArrowRight className="size-3.5 text-muted-foreground" />
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export { titleCase, IMAGES };
