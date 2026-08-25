"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  Home,
  Database,
  GitBranch,
  Beaker,
  ListOrdered,
  Lightbulb,
  BookOpenText,
  Library,
  Tags,
  Leaf,
} from "lucide-react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

const PAGES = [
  { href: "/app", label: "Home", icon: Home },
  { href: "/app/synthetic", label: "Synthetic dataset workspace", icon: Database },
  { href: "/app/real", label: "Real dataset workspace", icon: Database },
  { href: "/app/modeling", label: "Modeling", icon: GitBranch },
  { href: "/app/prediction", label: "Prediction", icon: Beaker },
  { href: "/app/results", label: "Results", icon: ListOrdered },
  { href: "/app/classification", label: "Classification", icon: Tags },
  { href: "/app/ingredients", label: "Ingredient efficacy", icon: Leaf },
  { href: "/app/explainability", label: "Explainability", icon: Lightbulb },
  { href: "/app/how-it-works", label: "How it works", icon: BookOpenText },
  { href: "/app/references", label: "References", icon: Library },
];

const MODELS = ["Random Forest", "LightGBM", "XGBoost", "Explainable Boosting Machine", "LSTM"];

interface CommandPaletteContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const CommandPaletteContext = React.createContext<CommandPaletteContextValue | null>(null);

export function useCommandPalette() {
  const ctx = React.useContext(CommandPaletteContext);
  if (!ctx) throw new Error("useCommandPalette must be used within CommandPaletteProvider");
  return ctx;
}

export function CommandPaletteProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const router = useRouter();

  React.useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const go = (href: string) => {
    setOpen(false);
    router.push(href);
  };

  return (
    <CommandPaletteContext.Provider value={{ open, setOpen }}>
      {children}
      <CommandDialog open={open} onOpenChange={setOpen} title="Search" description="Jump to a page or model">
        <CommandInput placeholder="Search pages, models, features…" />
        <CommandList>
          <CommandEmpty>No results found.</CommandEmpty>
          <CommandGroup heading="Pages">
            {PAGES.map((p) => (
              <CommandItem key={p.href} value={p.label} onSelect={() => go(p.href)}>
                <p.icon />
                <span>{p.label}</span>
              </CommandItem>
            ))}
          </CommandGroup>
          <CommandGroup heading="Models">
            {MODELS.map((m) => (
              <CommandItem key={m} value={m} onSelect={() => go("/app/modeling")}>
                <GitBranch />
                <span>{m}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </CommandPaletteContext.Provider>
  );
}

export function useCommandPaletteTrigger() {
  const [label, setLabel] = React.useState("Ctrl K");
  React.useEffect(() => {
    if (/Mac/.test(navigator.platform)) setLabel("⌘K");
  }, []);
  return label;
}
