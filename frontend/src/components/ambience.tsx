"use client";

import * as React from "react";
import { motion, useMotionValue, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";

/**
 * The single ambient background for the entire product — landing, auth, and
 * the app workspace all mount this once (from the root layout) so the
 * "living" quality is consistent everywhere instead of the marketing page
 * feeling designed and everything past login feeling abandoned.
 *
 * Built from five layers, back to front:
 *   1. Aurora — five huge, heavily-blurred, organically-morphing colour
 *      fields laid over plain white at low opacity, so they read as soft
 *      colour washes rather than a flat gradient. Three are present from the
 *      top of the page; two more fade in only once you scroll past the
 *      platform and research sections, so the composition visibly gains new
 *      colour as you go rather than just re-arranging the same three blobs.
 *      Every field also parallaxes against scroll at its own rate (through a
 *      spring, so it trails rather than tracking 1:1) and slowly morphs its
 *      own silhouette (`border-radius` keyframes, not just a scaling circle)
 *      — the combination is what reads as depth and motion rather than
 *      wallpaper, and is what visibly shifts as the page is scrolled.
 *   2. Conic sheen — a very faint, slowly-rotating conic gradient behind the
 *      aurora. Barely perceptible on a still frame; over tens of seconds it
 *      reads as a subtle rotation of light across the whole page.
 *   3. Cursor spotlight — a small warm glow that follows the pointer with a
 *      lag spring. Kept very faint; it should register as "the page notices
 *      you" on a still frame, not as a visible following blob.
 *   4. Dot grid — faint, masked to fade at the edges so it reads as texture
 *      in the gaps between panels, never as a pattern behind content.
 *   5. Grain — a tiled SVG turbulence texture at very low opacity. The detail
 *      that keeps a flat white ground from looking like a mockup.
 *
 * Everything here is transform/opacity, fixed, -z-10 and pointer-events:none,
 * so it never affects layout, hit-testing, or scroll performance.
 */
export function Ambience() {
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll();
  const progress = useSpring(scrollYProgress, { stiffness: 55, damping: 22, mass: 0.6 });

  // Position — each field parallaxes at its own rate/direction. Ranges are
  // large enough that the shift reads unmistakably as the page is scrolled,
  // not just at a glance.
  const yA = useTransform(progress, [0, 1], ["0%", "-58%"]);
  const xA = useTransform(progress, [0, 1], ["0%", "10%"]);
  const yB = useTransform(progress, [0, 1], ["0%", "46%"]);
  const xB = useTransform(progress, [0, 1], ["0%", "-22%"]);
  const yC = useTransform(progress, [0, 1], ["0%", "-30%"]);
  const xC = useTransform(progress, [0, 1], ["0%", "16%"]);
  const yD = useTransform(progress, [0, 1], ["-10%", "38%"]);
  const yE = useTransform(progress, [0, 1], ["12%", "-40%"]);

  // Arrival — D and E start invisible and fade in as you scroll into the
  // platform and research sections respectively, so the palette genuinely
  // gains new colour further down the page instead of only re-arranging.
  const opacityD = useTransform(progress, [0.16, 0.34], [0, 1]);
  const opacityE = useTransform(progress, [0.48, 0.68], [0, 1]);

  // Conic sheen rotates continuously with scroll — slow enough to be nearly
  // subliminal, fast enough that the light visibly turns over a full page.
  const sheenRotate = useTransform(progress, [0, 1], ["0deg", "140deg"]);

  const mx = useMotionValue(0.5);
  const my = useMotionValue(0.35);
  const springX = useSpring(mx, { stiffness: 40, damping: 18, mass: 0.9 });
  const springY = useSpring(my, { stiffness: 40, damping: 18, mass: 0.9 });
  const spotlightX = useTransform(springX, (v) => `${v * 100}%`);
  const spotlightY = useTransform(springY, (v) => `${v * 100}%`);

  React.useEffect(() => {
    if (reduce) return;
    let raf = 0;
    const onMove = (e: PointerEvent) => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        mx.set(e.clientX / window.innerWidth);
        my.set(e.clientY / window.innerHeight);
      });
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(raf);
    };
  }, [reduce, mx, my]);

  if (reduce) {
    return (
      <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 bg-canvas">
        <div className="absolute inset-0 opacity-[0.95]" style={{ backgroundImage: AURORA_STATIC }} />
        <div className="absolute inset-0 opacity-[0.035] mix-blend-multiply" style={{ backgroundImage: GRAIN }} />
      </div>
    );
  }

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-canvas">
      {/* Conic sheen — a slow-rotating wash of light beneath the aurora. */}
      <motion.div
        style={{ rotate: sheenRotate }}
        className="absolute top-1/2 left-1/2 size-[140vmax] -translate-x-1/2 -translate-y-1/2 opacity-[0.09] will-change-transform"
      >
        <div
          className="size-full"
          style={{
            background:
              "conic-gradient(from 0deg, color-mix(in srgb, var(--primary) 70%, transparent), transparent 18%, color-mix(in srgb, #6E5BFF 65%, transparent) 40%, transparent 55%, color-mix(in srgb, #1FD8B0 65%, transparent) 72%, transparent 90%, color-mix(in srgb, var(--primary) 70%, transparent) 100%)",
          }}
        />
      </motion.div>

      {/* Aurora — plain alpha blending over white. Vivid enough to read
          unmistakably as colour, not just a hint of tint. Three fields
          anchor the hero; two more arrive further down the page. */}
      <div className="absolute inset-0">
        {/* Position (x/y) comes from scroll-linked motion values via `style`;
            the gentle breathing scale comes from Framer's own `animate` loop
            on the same element. Framer composes both into one `transform`,
            so — unlike a CSS keyframe animation on the same property — they
            never fight each other. Only `border-radius` is CSS-animated. */}
        <motion.div
          style={{ y: yA, x: xA }}
          animate={{ scale: [1, 1.14, 0.96, 1.05, 1] }}
          transition={{ duration: 26, repeat: Infinity, ease: "easeInOut" }}
          className="absolute -top-[26%] -left-[12%] size-[68rem] opacity-[0.4] blur-[100px] will-change-transform
                     bg-[radial-gradient(circle,color-mix(in_srgb,var(--primary)_92%,transparent),transparent_70%)]
                     motion-safe:animate-[blob-morph-a_22s_ease-in-out_infinite]"
        />
        <motion.div
          style={{ y: yB, x: xB }}
          animate={{ scale: [1.08, 0.92, 1.1, 0.98, 1.08] }}
          transition={{ duration: 32, repeat: Infinity, ease: "easeInOut" }}
          className="absolute top-[0%] -right-[14%] size-[60rem] opacity-[0.32] blur-[105px] will-change-transform
                     bg-[radial-gradient(circle,color-mix(in_srgb,#6E5BFF_90%,transparent),transparent_70%)]
                     motion-safe:animate-[blob-morph-b_27s_ease-in-out_infinite]"
        />
        <motion.div
          style={{ y: yC, x: xC }}
          animate={{ scale: [0.94, 1.12, 0.98, 1.06, 0.94] }}
          transition={{ duration: 38, repeat: Infinity, ease: "easeInOut" }}
          className="absolute -bottom-[22%] left-[14%] size-[56rem] opacity-[0.3] blur-[110px] will-change-transform
                     bg-[radial-gradient(circle,color-mix(in_srgb,#1FD8B0_85%,transparent),transparent_70%)]
                     motion-safe:animate-[blob-morph-c_31s_ease-in-out_infinite]"
        />
        {/* Arrives around the platform section — warm gold accent. */}
        <motion.div
          style={{ y: yD, opacity: opacityD }}
          animate={{ scale: [1, 1.1, 0.95, 1] }}
          transition={{ duration: 28, repeat: Infinity, ease: "easeInOut" }}
          className="absolute top-[62%] -right-[8%] size-[48rem] blur-[95px] will-change-transform
                     bg-[radial-gradient(circle,color-mix(in_srgb,#D9A441_88%,transparent),transparent_70%)]
                     motion-safe:animate-[blob-morph-b_24s_ease-in-out_infinite]"
        />
        {/* Arrives around the research section — deep institutional blue. */}
        <motion.div
          style={{ y: yE, opacity: opacityE }}
          animate={{ scale: [1.05, 0.92, 1.08, 1.05] }}
          transition={{ duration: 34, repeat: Infinity, ease: "easeInOut" }}
          className="absolute top-[120%] -left-[10%] size-[52rem] blur-[100px] will-change-transform
                     bg-[radial-gradient(circle,color-mix(in_srgb,#3E6FA8_88%,transparent),transparent_70%)]
                     motion-safe:animate-[blob-morph-c_29s_ease-in-out_infinite]"
        />
      </div>

      {/* Cursor spotlight — follows the pointer with a lag spring. Present
          enough that moving your mouse visibly reads as "the page is alive". */}
      <div className="absolute -inset-[10%] opacity-[0.2]">
        <SpotlightPaint x={spotlightX} y={spotlightY} />
      </div>

      {/* Dot grid, faded at the edges */}
      <div
        className="absolute inset-0 opacity-[0.14] [mask-image:radial-gradient(ellipse_75%_60%_at_50%_20%,black,transparent)]"
        style={{ backgroundImage: DOT_GRID, backgroundSize: "28px 28px" }}
      />

      {/* Grain — multiply reads as fine paper texture on a light ground. */}
      <div className="absolute inset-0 opacity-[0.035] mix-blend-multiply" style={{ backgroundImage: GRAIN }} />

      {/* Edge vignette so aurora never touches the viewport border hard */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,transparent_58%,var(--canvas)_100%)] opacity-70" />
    </div>
  );
}

/** Repaints the spotlight's radial-gradient position every frame from the
 *  spring values — kept as its own tiny component so only this node re-renders. */
function SpotlightPaint({
  x,
  y,
}: {
  x: ReturnType<typeof useTransform<number, string>>;
  y: ReturnType<typeof useTransform<number, string>>;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    const update = () => {
      if (ref.current) {
        ref.current.style.background = `radial-gradient(620px circle at ${x.get()} ${y.get()}, color-mix(in srgb, var(--primary) 85%, transparent), transparent 62%)`;
      }
    };
    update();
    const unsubX = x.on("change", update);
    const unsubY = y.on("change", update);
    return () => {
      unsubX();
      unsubY();
    };
  }, [x, y]);
  return <div ref={ref} className="absolute inset-0" />;
}

const DOT_GRID =
  "radial-gradient(circle, color-mix(in srgb, var(--foreground) 40%, transparent) 1px, transparent 1px)";

const GRAIN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")";

const AURORA_STATIC =
  "radial-gradient(circle at 15% 15%, color-mix(in srgb, var(--primary) 48%, transparent), transparent 58%), radial-gradient(circle at 85% 25%, color-mix(in srgb, #6E5BFF 40%, transparent), transparent 58%), radial-gradient(circle at 35% 85%, color-mix(in srgb, #1FD8B0 34%, transparent), transparent 58%), radial-gradient(circle at 90% 75%, color-mix(in srgb, #D9A441 30%, transparent), transparent 58%)";
