import { AlertCircle } from "lucide-react";

/**
 * Inline form-level error. Announced politely so screen-reader users hear it
 * without it interrupting whatever they're currently reading.
 */
export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      aria-live="polite"
      className="flex items-start gap-2 rounded-md border border-destructive/25 bg-destructive/[0.06] px-3 py-2"
    >
      <AlertCircle className="mt-px size-3.5 shrink-0 text-destructive" />
      <p className="type-ui text-destructive">{message}</p>
    </div>
  );
}
