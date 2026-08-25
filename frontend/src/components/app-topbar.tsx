"use client";

import { usePathname, useRouter } from "next/navigation";
import {
  BookOpen,
  ChevronRight,
  Database,
  FlaskConical,
  GitCompare,
  HelpCircle,
  Home,
  Leaf,
  Lightbulb,
  ListTree,
  Search,
  Sparkles,
  Tags,
} from "lucide-react";

import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useCommandPalette, useCommandPaletteTrigger } from "@/components/command-palette";
import { TopbarUserMenu } from "@/components/topbar-user-menu";

const ROUTES: Record<string, { label: string; icon: typeof Home }> = {
  "/app": { label: "Home", icon: Home },
  "/app/synthetic": { label: "Synthetic dataset", icon: Database },
  "/app/real": { label: "Real dataset", icon: Database },
  "/app/modeling": { label: "Modeling", icon: ListTree },
  "/app/prediction": { label: "Prediction", icon: FlaskConical },
  "/app/results": { label: "Results", icon: GitCompare },
  "/app/classification": { label: "Classification", icon: Tags },
  "/app/ingredients": { label: "Ingredient Efficacy", icon: Leaf },
  "/app/explainability": { label: "Explainability", icon: Lightbulb },
  "/app/how-it-works": { label: "How it works", icon: Sparkles },
  "/app/references": { label: "References", icon: BookOpen },
  "/app/account": { label: "Account", icon: Home },
};

export function AppTopbar() {
  const pathname = usePathname();
  const router = useRouter();
  const route = ROUTES[pathname];
  const { setOpen } = useCommandPalette();
  const kbd = useCommandPaletteTrigger();

  return (
    <header className="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-3 border-b border-border bg-canvas/65 px-4 backdrop-blur-xl backdrop-saturate-150 sm:px-5">
      <SidebarTrigger className="-ml-1.5 size-8 text-muted-foreground" />
      <Separator orientation="vertical" className="h-5" />

      <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2">
        <span className="type-ui hidden shrink-0 text-subtle-foreground sm:inline">Workspace</span>
        {pathname !== "/app" && route && (
          <>
            <ChevronRight className="hidden size-3 shrink-0 text-subtle-foreground sm:block" aria-hidden />
            <route.icon className="size-4 shrink-0 text-primary" strokeWidth={1.75} />
            <span className="type-title truncate text-foreground">{route.label}</span>
          </>
        )}
        {pathname === "/app" && (
          <div className="flex items-center gap-2">
            <Home className="size-4 shrink-0 text-primary" strokeWidth={1.75} />
            <span className="type-title truncate text-foreground">Home</span>
          </div>
        )}
      </nav>

      <div className="ml-auto flex items-center gap-1.5 sm:gap-2.5">
        <button
          onClick={() => setOpen(true)}
          className="hidden h-8 items-center gap-2 rounded-md border border-border bg-background/60 px-2.5 text-[0.75rem] text-subtle-foreground transition-colors hover:border-border-strong hover:bg-background hover:text-muted-foreground sm:flex sm:w-52"
        >
          <Search className="size-3.5" />
          <span className="flex-1 text-left">Search…</span>
          <kbd className="rounded-[3px] border border-border bg-muted px-1 py-px font-mono text-[0.625rem] text-subtle-foreground">
            {kbd}
          </kbd>
        </button>
        <Button variant="ghost" size="icon" className="sm:hidden" onClick={() => setOpen(true)} aria-label="Search">
          <Search className="size-4" />
        </Button>

        <Tooltip>
          <TooltipTrigger
            render={
              <Button variant="ghost" size="icon" onClick={() => router.push("/app/how-it-works")} aria-label="Help">
                <HelpCircle className="size-4" />
              </Button>
            }
          />
          <TooltipContent>Help &amp; documentation</TooltipContent>
        </Tooltip>

        <Separator orientation="vertical" className="h-5" />

        <TopbarUserMenu />
      </div>
    </header>
  );
}
