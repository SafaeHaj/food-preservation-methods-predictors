import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";

import { AuthShell } from "@/components/auth-shell";
import { LoginForm } from "@/components/login-form";

export const metadata: Metadata = { title: "Log in" };

export default function LoginPage() {
  return (
    <AuthShell
      title="Log in"
      description="Continue to your workspace."
      footer={
        <>
          Don&apos;t have an account?{" "}
          <Link
            href="/signup"
            className="font-medium text-foreground underline decoration-border underline-offset-[3px] transition-colors hover:decoration-foreground"
          >
            Sign up
          </Link>
        </>
      }
    >
      {/* useSearchParams (for ?next=) requires a Suspense boundary. */}
      <Suspense fallback={<div className="h-[196px]" />}>
        <LoginForm />
      </Suspense>
    </AuthShell>
  );
}
