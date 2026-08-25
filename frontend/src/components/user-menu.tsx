"use client";

import Link from "next/link";
import { ChevronsUpDown, LogOut, User as UserIcon } from "lucide-react";

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

/** Account switcher at the foot of the sidebar. Collapses to just the avatar
 *  when the sidebar is in icon mode. */
export function UserMenu() {
  const { user, signOut } = useSession();
  if (!user) return null;

  const avatar = resolveAvatarUrl(user.avatar_url);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="flex w-full items-center gap-2 rounded-md p-1.5 text-left outline-none transition-colors hover:bg-sidebar-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring aria-expanded:bg-sidebar-accent"
        aria-label="Account menu (sidebar)"
      >
        <Avatar className="size-6 shrink-0 rounded-md">
          {avatar && <AvatarImage src={avatar} alt="" />}
          <AvatarFallback className="rounded-md bg-primary text-[0.625rem] font-medium text-primary-foreground">
            {initialsOf(user.name)}
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1 group-data-[collapsible=icon]:hidden">
          <p className="truncate text-[0.8125rem] font-medium text-foreground">{user.name}</p>
          <p className="truncate text-[0.6875rem] text-subtle-foreground">{user.email}</p>
        </div>
        <ChevronsUpDown className="size-3.5 shrink-0 text-subtle-foreground group-data-[collapsible=icon]:hidden" />
      </DropdownMenuTrigger>

      <DropdownMenuContent align="start" side="top" sideOffset={8} className="w-[--anchor-width] min-w-56">
        <div className="flex items-center gap-2 px-2 py-1.5">
          <Avatar className="size-7 rounded-md">
            {avatar && <AvatarImage src={avatar} alt="" />}
            <AvatarFallback className="rounded-md bg-primary text-[0.6875rem] font-medium text-primary-foreground">
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
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => void signOut()} variant="destructive">
          <LogOut className="size-3.5" />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
