import * as React from "react"

import { cn } from "@/lib/utils"

/**
 * A panel: hairline border, 8px radius, no shadow and no hover lift. Depth in
 * this system comes from the 1px rule, not from floating — reserve shadows for
 * things that genuinely overlay the page (popover, dialog, toast).
 *
 * `size="sm"` tightens padding for panels used inside dense grids.
 */
function Card({
  className,
  size = "default",
  ...props
}: React.ComponentProps<"div"> & { size?: "default" | "sm" }) {
  return (
    <div
      data-slot="card"
      data-size={size}
      className={cn(
        "group/card relative flex flex-col gap-(--card-spacing) overflow-hidden rounded-lg",
        // Matches `.surface`: slightly translucent over a blur so the ambient
        // background tints panels as the page scrolls.
        "border border-border bg-card/92 backdrop-blur-xl backdrop-saturate-[1.2]",
        "py-(--card-spacing) text-card-foreground",
        // Top-edge highlight — reads as a lit physical surface.
        "after:pointer-events-none after:absolute after:inset-x-0 after:top-0 after:h-px",
        "after:bg-gradient-to-r after:from-transparent after:via-white/60 after:to-transparent",
        "dark:after:via-white/[0.14]",
        "[--card-spacing:--spacing(4)] data-[size=sm]:[--card-spacing:--spacing(3)]",
        "has-data-[slot=card-footer]:pb-0 has-[>img:first-child]:pt-0",
        "*:[img:first-child]:rounded-t-lg *:[img:last-child]:rounded-b-lg",
        className
      )}
      {...props}
    />
  )
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn(
        "group/card-header @container/card-header grid auto-rows-min items-start gap-1 px-(--card-spacing)",
        "has-data-[slot=card-action]:grid-cols-[1fr_auto]",
        "has-data-[slot=card-description]:grid-rows-[auto_auto]",
        "[.border-b]:pb-(--card-spacing)",
        className
      )}
      {...props}
    />
  )
}

function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-title"
      className={cn("type-title text-foreground", className)}
      {...props}
    />
  )
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("type-ui text-muted-foreground", className)}
      {...props}
    />
  )
}

function CardAction({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-action"
      className={cn(
        "col-start-2 row-span-2 row-start-1 self-start justify-self-end",
        className
      )}
      {...props}
    />
  )
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-content"
      className={cn("px-(--card-spacing)", className)}
      {...props}
    />
  )
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn(
        "mt-auto flex items-center rounded-b-lg border-t border-border bg-muted/40 p-(--card-spacing)",
        className
      )}
      {...props}
    />
  )
}

export {
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardAction,
  CardDescription,
  CardContent,
}
