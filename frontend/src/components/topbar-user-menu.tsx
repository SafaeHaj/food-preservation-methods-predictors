"use client";

import Link from "next/link";
import { LogOut, Sparkles, User as UserIcon } from "lucide-react";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { initialsOf, useSession } from "@/components/session-store";
import { resolveAvatarUrl } from "@/lib/api";

/**
 * The primary, always-visible identity control — large avatar in the topbar,
 * with a soft ring that brightens on hover so it reads as a real photo (or a
 * deliberate initials mark) rather than a default system icon.
 */
export function TopbarUserMenu() {
  const { user, signOut } = useSession();
  if (!user) return null;

  const avatar = resolveAvatarUrl(user.avatar_url);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="group relative flex shrink-0 items-center outline-none"
        aria-label="Account menu"
      >
        <span
          aria-hidden
          className="absolute -inset-1 rounded-full bg-primary/0 blur-md transition-colors duration-300 group-hover:bg-primary/25 group-aria-expanded:bg-primary/30"
        />
        <Avatar className="relative size-10 rounded-full ring-2 ring-border transition-all duration-200 group-hover:ring-primary/50 group-aria-expanded:ring-primary/60">
          {avatar && <AvatarImage src={avatar} alt="" className="object-cover" />}
          <AvatarFallback className="rounded-full bg-gradient-to-br from-primary to-[color-mix(in_srgb,var(--primary)_60%,#6E5BFF)] text-[0.8125rem] font-semibold text-primary-foreground">
            {initialsOf(user.name)}
          </AvatarFallback>
        </Avatar>
        {/* Online/active dot — a small, expected SaaS-chrome detail. */}
        <span
          aria-hidden
          className="absolute right-0 bottom-0 size-2.5 rounded-full border-2 border-canvas bg-success"
        />
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" side="bottom" sideOffset={12} className="w-64">
        {/* Plain div, not DropdownMenuLabel: this Base UI version's GroupLabel
            requires a Menu.Group ancestor, and this block is purely a visual
            identity header, not a semantic group label. */}
        <div className="flex items-center gap-3 px-1 py-1.5">
          <Avatar className="size-9 rounded-full ring-1 ring-border">
            {avatar && <AvatarImage src={avatar} alt="" className="object-cover" />}
            <AvatarFallback className="rounded-full bg-gradient-to-br from-primary to-[color-mix(in_srgb,var(--primary)_60%,#6E5BFF)] text-[0.75rem] font-semibold text-primary-foreground">
              {initialsOf(user.name)}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <p className="truncate text-[0.8125rem] font-medium text-foreground">{user.name}</p>
            <p className="truncate text-[0.6875rem] text-subtle-foreground">{user.email}</p>
          </div>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem render={<Link href="/app/account" />}>
          <UserIcon className="size-3.5" />
          Account settings
        </DropdownMenuItem>
        <DropdownMenuItem render={<Link href="/app/how-it-works" />}>
          <Sparkles className="size-3.5" />
          How it works
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => void signOut()} variant="destructive">
          <LogOut className="size-3.5" />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
