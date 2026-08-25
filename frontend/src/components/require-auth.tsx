"use client";

import * as React from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

import { useSession } from "@/components/session-store";

/**
 * Client-side session gate for the app shell. Middleware handles the common
 * case at the edge; this catches a cookie the server no longer accepts, where
 * the request would otherwise render a shell whose every data call 401s.
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  React.useEffect(() => {
    if (!loading && !user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [loading, user, router, pathname]);

  if (loading || !user) {
    return (
      <div
        className="flex min-h-svh w-full items-center justify-center bg-canvas"
        role="status"
        aria-live="polite"
      >
        <Loader2 className="size-4 animate-spin text-subtle-foreground" />
        <span className="sr-only">Loading your workspace…</span>
      </div>
    );
  }

  return <>{children}</>;
}
