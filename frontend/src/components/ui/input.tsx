import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"

import { cn } from "@/lib/utils"

/**
 * 32px field, hairline border, accent border + soft ring on focus. Font size
 * is 16px on small screens (prevents iOS zoom-on-focus) and drops to the 13px
 * UI size from `sm` up.
 */
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        "h-8 w-full min-w-0 rounded-md border border-input bg-background px-2.5 py-1",
        "text-base sm:text-[0.8125rem]",
        "transition-[border-color,box-shadow] duration-140 outline-none",
        "placeholder:text-subtle-foreground",
        "file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-[0.8125rem] file:font-medium file:text-foreground",
        "hover:border-border-strong",
        "focus-visible:border-ring focus-visible:shadow-[var(--shadow-focus)] focus-visible:outline-none",
        "disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-55",
        "aria-invalid:border-destructive aria-invalid:focus-visible:shadow-[0_0_0_3px_color-mix(in_srgb,var(--destructive)_18%,transparent)]",
        className
      )}
      {...props}
    />
  )
}

export { Input }
