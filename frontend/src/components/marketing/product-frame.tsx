"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Chrome that makes an embedded UI fragment read as "a window of the product"
 * rather than a floating card. Contents are real components rendered with real
 * shapes of data — nothing here is a screenshot.
 */
export function ProductFrame({
  label,
  children,
  className,
  contentClassName,
}: {
  label?: string;
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border border-border bg-background shadow-lg",
        className,
      )}
    >
      <div className="flex h-9 items-center gap-2 border-b border-border bg-muted/50 px-3">
        <div className="flex gap-1.5" aria-hidden>
          <span className="size-2.5 rounded-full bg-border-strong" />
          <span className="size-2.5 rounded-full bg-border-strong" />
          <span className="size-2.5 rounded-full bg-border-strong" />
        </div>
        {label && (
          <span className="type-caption ml-1.5 truncate text-subtle-foreground">{label}</span>
        )}
      </div>
      <div className={cn("bg-background", contentClassName)}>{children}</div>
    </div>
  );
}
