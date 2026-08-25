import * as React from "react"
import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

/**
 * Compact product buttons. Default height is 32px (28px at `sm`) — controls
 * stay dense enough to sit inline with text and table rows without dominating
 * them. Only `default` carries the accent; everything else is neutral, so a
 * screen never has two competing primary actions.
 *
 * `xl` exists solely for landing-page CTAs, where a larger target is
 * appropriate. Do not use it inside the app.
 */
const buttonVariants = cva(
  [
    "group/button relative inline-flex shrink-0 select-none items-center justify-center",
    "whitespace-nowrap rounded-md border border-transparent bg-clip-padding font-medium",
    "outline-none transition-[background-color,border-color,color,box-shadow,opacity] duration-140 ease-[cubic-bezier(0.4,0,0.2,1)]",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
    "disabled:pointer-events-none disabled:opacity-45",
    "aria-invalid:border-destructive",
    "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  ].join(" "),
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-xs hover:bg-primary-hover active:not-aria-[haspopup]:translate-y-px",
        outline:
          "border-border bg-background text-foreground hover:bg-muted hover:border-border-strong aria-expanded:bg-muted",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-[color-mix(in_srgb,var(--secondary),var(--foreground)_5%)] aria-expanded:bg-[color-mix(in_srgb,var(--secondary),var(--foreground)_5%)]",
        ghost:
          "text-muted-foreground hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground",
        destructive:
          "bg-destructive text-destructive-foreground shadow-xs hover:bg-[color-mix(in_srgb,var(--destructive),black_10%)] focus-visible:outline-destructive",
        "destructive-ghost":
          "text-destructive hover:bg-destructive/10 focus-visible:outline-destructive",
        // Maximum-contrast CTA: inverts against whatever ground it sits on, so
        // it reads white-on-dark for marketing and dark-on-light in the app.
        // Reserved for the single most important action on a page.
        contrast:
          "bg-foreground text-background shadow-sm hover:bg-foreground/90 active:translate-y-px",
        link: "h-auto rounded-xs p-0 text-foreground underline decoration-border underline-offset-[3px] hover:decoration-foreground",
      },
      size: {
        default: "h-8 gap-1.5 px-2.5 text-[0.8125rem]",
        xs: "h-6 gap-1 rounded-sm px-1.5 text-[0.75rem] [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1.5 rounded-md px-2 text-[0.8125rem] [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-2 px-3.5 text-[0.875rem]",
        xl: "h-11 gap-2 rounded-lg px-5 text-[0.9375rem] tracking-[-0.011em]",
        icon: "size-8",
        "icon-xs": "size-6 rounded-sm [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-7 rounded-md [&_svg:not([class*='size-'])]:size-3.5",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  render,
  nativeButton,
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  // `render` is nearly always used to swap in a Link or anchor. Base UI warns
  // (correctly) when it emits button semantics onto a non-<button>, so default
  // nativeButton to false whenever a render element is supplied. An explicit
  // prop still wins, for the rare case of rendering an actual <button>.
  const resolvedNativeButton = nativeButton ?? (render ? false : undefined)

  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      render={render}
      nativeButton={resolvedNativeButton}
      {...props}
    />
  )
}

/**
 * A navigation control that looks like a button.
 *
 * Use this instead of `<Button render={<Link/>}>` for anything that navigates:
 * routing Button's primitive through an anchor either emits button semantics
 * onto a non-button (which Base UI warns about) or overrides the anchor's
 * `link` role, breaking the "open in new tab" affordance and how screen readers
 * announce it. Styling is identical — only the semantics differ.
 */
function LinkButton({
  className,
  variant = "default",
  size = "default",
  ...props
}: React.ComponentProps<"a"> & VariantProps<typeof buttonVariants>) {
  return (
    <a
      data-slot="link-button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, LinkButton, buttonVariants }
