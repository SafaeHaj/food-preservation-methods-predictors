"use client";

import * as React from "react";
import Image from "next/image";

import { cn } from "@/lib/utils";

/**
 * Photograph slot for the research-context sections.
 *
 * Photographs are decorative here — the surrounding copy carries the meaning —
 * so `alt` is intentionally empty and the caption is exposed to assistive tech
 * via a visually-hidden figcaption instead. Credits live in
 * /public/marketing/CREDITS.md.
 *
 * `overlay` darkens the image and adds a bottom gradient so white type can sit
 * on top at accessible contrast regardless of what the photo happens to show
 * — and regardless of the site's own light/dark theme, since the gradient is
 * a fixed black scrim rather than the theme's `--canvas` token. This section
 * is an editorial "dark photo, white type" moment by design, independent of
 * whether the rest of the page is light or dark.
 */
export function EditorialImage({
  src,
  caption,
  className,
  imageClassName,
  priority,
  overlay = false,
}: {
  src: string;
  caption: string;
  className?: string;
  imageClassName?: string;
  priority?: boolean;
  overlay?: boolean;
}) {
  const [failed, setFailed] = React.useState(false);

  return (
    <figure className={cn("relative overflow-hidden bg-muted", className)}>
      {failed ? (
        <div className="absolute inset-0 flex items-center justify-center bg-grid">
          <span className="type-caption text-subtle-foreground">Image unavailable</span>
        </div>
      ) : (
        <>
          <Image
            src={src}
            alt=""
            fill
            priority={priority}
            sizes="(max-width: 768px) 100vw, (max-width: 1180px) 50vw, 1180px"
            onError={() => setFailed(true)}
            className={cn(
              "object-cover",
              // Photographs are lively; the page is not. Desaturating slightly
              // and dimming keeps them from overpowering the restrained UI.
              overlay ? "brightness-[0.42] saturate-[0.85]" : "brightness-[0.82] saturate-[0.9]",
              imageClassName,
            )}
          />
          {overlay && (
            <div
              aria-hidden
              className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/40 to-black/10"
            />
          )}
        </>
      )}
      <figcaption className="sr-only">{caption}</figcaption>
    </figure>
  );
}
