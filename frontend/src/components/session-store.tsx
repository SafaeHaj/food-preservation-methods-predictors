"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { api, type AuthUser } from "@/lib/api";

interface SessionValue {
  user: AuthUser | null;
  /** True until the initial /api/auth/me call resolves. Gate protected UI on
   *  this so a signed-in user never sees a flash of the signed-out state. */
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (name: string, email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  /** Replace the cached user after a profile/avatar mutation. */
  setUser: (user: AuthUser) => void;
  refresh: () => Promise<void>;
}

const SessionContext = React.createContext<SessionValue | null>(null);

/**
 * Holds the signed-in user for the whole app. The session itself is an
 * httpOnly cookie owned by the backend — this only caches the identity the
 * server reports, so signing out server-side is always authoritative.
 */
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [user, setUserState] = React.useState<AuthUser | null>(null);
  const [loading, setLoading] = React.useState(true);
  const router = useRouter();

  const refresh = React.useCallback(async () => {
    try {
      setUserState(await api.me());
    } catch {
      setUserState(null);
    }
  }, []);

  React.useEffect(() => {
    let active = true;
    api
      .me()
      .then((u) => active && setUserState(u))
      .catch(() => active && setUserState(null))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  const signIn = React.useCallback(async (email: string, password: string) => {
    setUserState(await api.login({ email, password }));
  }, []);

  const signUp = React.useCallback(async (name: string, email: string, password: string) => {
    setUserState(await api.signup({ name, email, password }));
  }, []);

  const signOut = React.useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUserState(null);
      router.push("/");
      router.refresh();
    }
  }, [router]);

  const value = React.useMemo<SessionValue>(
    () => ({ user, loading, signIn, signUp, signOut, setUser: setUserState, refresh }),
    [user, loading, signIn, signUp, signOut, refresh],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const ctx = React.useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}

/** Initials fallback for the avatar, e.g. "Ada Lovelace" -> "AL". */
export function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
