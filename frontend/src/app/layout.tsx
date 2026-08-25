import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Fraunces } from "next/font/google";
import "./globals.css";

import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { SessionProvider } from "@/components/session-store";
import { Ambience } from "@/components/ambience";

/**
 * Inter, loaded as a variable font with the optical-size axis.
 *
 * `opsz` is what makes large headings feel like a display cut rather than body
 * text scaled up — tighter apertures and spacing at size. Without it, big type
 * reads soft and generic. The variable weight range also lets headings sit at
 * ~530-590 instead of jumping to 700, which is the difference between
 * "considered" and "bold".
 */
// No `weight` here on purpose: declaring an explicit weight list opts into the
// static cut, and `axes` is only valid on the variable font. Omitting weight
// keeps the full 100-900 range available, which is what lets headings sit at
// 540 rather than snapping to 500 or 600.
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  axes: ["opsz"],
  display: "swap",
});
const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
});
/**
 * Fraunces — a warm, editorial display serif with a huge optical-size range,
 * used for the largest display headings (hero, section titles). This was
 * already the brand's intended display face (paired with Inter + JetBrains
 * Mono in the original Dash dashboard's font stack) but never made it into
 * this Next.js frontend. Loaded with the full `opsz` range so headings at
 * 4rem+ get the true display cut — high-contrast strokes, tighter fit —
 * instead of a body serif scaled up.
 */
const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  axes: ["opsz", "SOFT", "WONK"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Shelf-Life Studio",
    template: "%s · Shelf-Life Studio",
  },
  description:
    "A research platform for modelling cheese shelf life from formulation, processing, packaging and storage conditions.",
};

/**
 * Root layout is deliberately thin: fonts, session, tooltips, toasts. The
 * application chrome (sidebar, topbar, assistant) lives in /app's own layout
 * so the marketing and auth routes render without it.
 *
 * Light is applied here, globally, on purpose: a clean white canvas end to
 * end — landing, auth, and the app workspace share one palette. No `dark`
 * class is added, so every token in globals.css resolves to its `:root`
 * (light) value everywhere.
 *
 * `<Ambience />` is likewise mounted exactly once, here, so every route gets
 * the same living, scroll-reactive background without each page
 * re-implementing it.
 */
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} ${jetbrainsMono.variable} ${fraunces.variable} h-full`} style={{ colorScheme: "light" }}>
      <body className="min-h-full bg-canvas font-sans text-foreground">
        <SessionProvider>
          <TooltipProvider delay={150}>
            <Ambience />
            {children}
          </TooltipProvider>
        </SessionProvider>
        <Toaster />
      </body>
    </html>
  );
}
