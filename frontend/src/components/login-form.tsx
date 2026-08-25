"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FormError } from "@/components/form-error";
import { useSession } from "@/components/session-store";
import { ApiError } from "@/lib/api";

export function LoginForm() {
  const { signIn } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  // Only accept internal paths — an absolute URL here would be an open redirect.
  const rawNext = params.get("next");
  const next = rawNext && rawNext.startsWith("/") && !rawNext.startsWith("//") ? rawNext : "/app";

  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await signIn(email, password);
      router.push(next);
      router.refresh();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.detail
          : "Couldn't reach the server. Check that the API is running.",
      );
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      <FormError message={error} />

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@mcgill.ca"
          aria-invalid={error ? true : undefined}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          aria-invalid={error ? true : undefined}
        />
      </div>

      <Button type="submit" size="lg" disabled={pending} className="mt-1 w-full">
        {pending && <Loader2 className="size-3.5 animate-spin" />}
        {pending ? "Signing in…" : "Log in"}
      </Button>
    </form>
  );
}
