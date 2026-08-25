import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

/**
 * Small, squared-off metadata chips — not pills. Semantic variants use a
 * tinted wash plus same-hue text rather than a solid fill, so a row of badges
 * reads as annotation rather than as a row of buttons.
 */
const badgeVariants = cva(
  [
    "group/badge inline-flex h-5 w-fit shrink-0 items-center justify-center gap-1",
    "overflow-hidden rounded-sm border border-transparent px-1.5",
    "text-[0.6875rem] font-medium leading-none whitespace-nowrap",
    "transition-colors duration-140",
    "[&>svg]:pointer-events-none [&>svg]:size-3!",
  ].join(" "),
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground",
        secondary: "bg-secondary text-secondary-foreground",
        outline: "border-border text-muted-foreground",
        accent:
          "bg-[color-mix(in_srgb,var(--primary)_10%,transparent)] text-primary",
        success:
          "bg-[color-mix(in_srgb,var(--success)_12%,transparent)] text-success",
        warning:
          "bg-[color-mix(in_srgb,var(--warning)_14%,transparent)] text-warning",
        destructive:
          "bg-[color-mix(in_srgb,var(--destructive)_12%,transparent)] text-destructive",
        info: "bg-[color-mix(in_srgb,var(--info)_12%,transparent)] text-info",
        ghost: "text-subtle-foreground hover:bg-muted hover:text-foreground",
      },
      size: {
        default: "h-5 px-1.5",
        sm: "h-4 px-1 text-[0.625rem]",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "default",
    },
  }
)

function Badge({
  className,
  variant,
  size,
  render,
  ...props
}: useRender.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return useRender({
    defaultTagName: "span",
    props: mergeProps<"span">(
      {
        className: cn(badgeVariants({ variant, size }), className),
      },
      props
    ),
    render,
    state: {
      slot: "badge",
      variant,
    },
  })
}

export { Badge, badgeVariants }
