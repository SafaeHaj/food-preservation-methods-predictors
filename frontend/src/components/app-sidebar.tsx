"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BookOpen,
  Database,
  FlaskConical,
  GitCompare,
  Home,
  Leaf,
  Library,
  Lightbulb,
  ListTree,
  Sparkles,
  Tags,
} from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { UserMenu } from "@/components/user-menu";

const NAV_GROUPS = [
  {
    label: "Overview",
    items: [{ href: "/app", label: "Home", icon: Home }],
  },
  {
    label: "Data",
    items: [
      { href: "/app/synthetic", label: "Synthetic", icon: Database },
      { href: "/app/real", label: "Real", icon: Library },
    ],
  },
  {
    label: "Models",
    items: [
      { href: "/app/modeling", label: "Modeling", icon: ListTree },
      { href: "/app/explainability", label: "Explainability", icon: Lightbulb },
    ],
  },
  {
    label: "Analysis",
    items: [
      { href: "/app/prediction", label: "Prediction", icon: FlaskConical },
      { href: "/app/results", label: "Results", icon: GitCompare },
      { href: "/app/classification", label: "Classification", icon: Tags },
      { href: "/app/ingredients", label: "Ingredients", icon: Leaf },
    ],
  },
  {
    label: "Reference",
    items: [
      { href: "/app/how-it-works", label: "How it works", icon: Sparkles },
      { href: "/app/references", label: "References", icon: BookOpen },
    ],
  },
] as const;

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <Sidebar
      collapsible="icon"
      className="border-r border-sidebar-border [&>[data-slot=sidebar-inner]]:bg-sidebar/70 [&>[data-slot=sidebar-inner]]:backdrop-blur-xl"
    >
      <SidebarHeader className="h-14 justify-center px-3">
        <Link
          href="/app"
          className="flex items-center gap-2 rounded-md outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary">
            <FlaskConical className="size-3.5 text-primary-foreground" />
          </span>
          <span className="type-title truncate text-foreground group-data-[collapsible=icon]:hidden">
            Shelf-Life Studio
          </span>
        </Link>
      </SidebarHeader>

      <SidebarContent className="gap-0 px-2">
        {NAV_GROUPS.map((group) => (
          <SidebarGroup key={group.label} className="py-1.5">
            <SidebarGroupLabel className="h-6 px-2 text-[0.6875rem] font-medium tracking-[0.04em] text-subtle-foreground uppercase">
              {group.label}
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => {
                  // Exact match for /app so it isn't marked active on every child route.
                  const active =
                    item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);
                  return (
                    <SidebarMenuItem key={item.href}>
                      <SidebarMenuButton
                        isActive={active}
                        tooltip={item.label}
                        className="h-7 gap-2 rounded-md px-2 text-[0.8125rem] font-medium text-sidebar-foreground data-[active=true]:bg-sidebar-accent data-[active=true]:font-medium data-[active=true]:text-sidebar-accent-foreground"
                        render={<Link href={item.href} />}
                      >
                        <item.icon
                          className={active ? "size-4 text-primary" : "size-4 text-subtle-foreground"}
                          strokeWidth={1.75}
                        />
                        <span>{item.label}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border p-2">
        <UserMenu />
      </SidebarFooter>
    </Sidebar>
  );
}
