"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Check, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FormError } from "@/components/form-error";
import { useSession } from "@/components/session-store";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

const MIN_PASSWORD = 8;

export function SignupForm() {
  const { signUp } = useSession();
  const router = useRouter();

  const [name, setName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [pending, setPending] = React.useState(false);
  // Only surface the mismatch once they've actually started the second field,
  // so the error doesn't appear while they're still typing the first character.
  const [confirmTouched, setConfirmTouched] = React.useState(false);

  const longEnough = password.length >= MIN_PASSWORD;
  const matches = confirm.length > 0 && password === confirm;
  const mismatch = confirmTouched && confirm.length > 0 && !matches;

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);

    if (!longEnough) {
      setError(`Password must be at least ${MIN_PASSWORD} characters.`);
      return;
    }
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }

    setPending(true);
    try {
      await signUp(name, email, password);
      router.push("/app");
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
        <Label htmlFor="name">Full name</Label>
        <Input
          id="name"
          name="name"
          autoComplete="name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Ada Lovelace"
        />
      </div>

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
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          aria-describedby="password-hint"
        />
        <p
          id="password-hint"
          className={cn(
            "type-caption flex items-center gap-1 transition-colors",
            longEnough ? "text-success" : "text-subtle-foreground",
          )}
        >
          {longEnough && <Check className="size-3" />}
          At least {MIN_PASSWORD} characters
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="confirm">Confirm password</Label>
        <Input
          id="confirm"
          name="confirm"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          onBlur={() => setConfirmTouched(true)}
          aria-invalid={mismatch || undefined}
          aria-describedby={mismatch ? "confirm-error" : undefined}
        />
        {mismatch && (
          <p id="confirm-error" className="type-caption text-destructive">
            Passwords don&apos;t match.
          </p>
        )}
      </div>

      <Button type="submit" size="lg" disabled={pending} className="mt-1 w-full">
        {pending && <Loader2 className="size-3.5 animate-spin" />}
        {pending ? "Creating account…" : "Create account"}
      </Button>
    </form>
  );
}
