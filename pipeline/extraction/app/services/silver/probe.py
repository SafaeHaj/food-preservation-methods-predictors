"""Is this image something a chart reader should even be shown?

Chart conversion is the most expensive step per figure and the most confidently wrong: a
photograph of a meat sample comes back as a plausible table of numbers. This is a cheap,
content-free geometry test run first — a uniform background, ink in a sane range, and
axis-like rules reaching across the frame in both directions.

It says nothing about *what* the figure plots. That is the schema gate's job, on the CSV
the converter produces, and keeping the two apart is why neither needs a keyword list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from PIL import Image

from shared.config import get_extraction_settings

_settings = get_extraction_settings()

MIN_SIDE_PX = 120
MIN_AREA_PX = 40_000
ASPECT_BOUNDS = (0.2, 5.0)
MIN_BACKGROUND_FRACTION = 0.35
MAX_INK_FRACTION = 0.60
MIN_INK_FRACTION = 0.004
MIN_RULE_SPAN = 0.55
#: Everything below is measured on a downscaled copy: the verdict is about layout, and a
#: 320px probe answers it as well as a 2000px one for a fraction of the work.
PROBE_LONG_SIDE = 320
INK_THRESHOLD = 32
COLOUR_LEVELS = 8
COLOUR_STEP = 256 // COLOUR_LEVELS

EDGE_STRENGTH = 24
AXIS_ALIGNED_RATIO = 3.0
MIN_AXIS_ALIGNED_EDGES = 0.45


@dataclass
class PlotProbe:
    plot_like: bool
    reason: str
    width: int = 0
    height: int = 0
    background_fraction: float = 0.0
    ink_fraction: float = 0.0
    distinct_colours: int = 0
    h_rule: float = 0.0
    v_rule: float = 0.0
    axis_aligned_edges: float = 0.0
    #: Read from the caption *and* the prose around it — what FIGURE_CAPTION_FILTER uses.
    caption_verdict: str = "unknown"
    #: Read from the figure's own caption alone — what FIGURE_REQUIRE_PLOT_CAPTION uses.
    #: Both are recorded whichever filter is on, so a gate report answers what the other
    #: policy would have done without re-running the corpus.
    own_caption_verdict: str = "unknown"

    def summary(self) -> dict:
        return {
            "plot_like": self.plot_like,
            "reason": self.reason,
            "width": self.width,
            "height": self.height,
            "background_fraction": round(self.background_fraction, 3),
            "ink_fraction": round(self.ink_fraction, 3),
            "distinct_colours": self.distinct_colours,
            "h_rule": round(self.h_rule, 3),
            "v_rule": round(self.v_rule, 3),
            "axis_aligned_edges": round(self.axis_aligned_edges, 3),
            "caption_verdict": self.caption_verdict,
            "own_caption_verdict": self.own_caption_verdict,
        }


def _rule_span(mask, axis: int) -> float:
    """How far the strongest rule reaches, as a fraction of the frame: an unbroken run, or
    a line mostly inked along its length so a dashed spine still counts."""
    grid = mask if axis == 1 else mask.T
    span = grid.shape[1]
    if span == 0:
        return 0.0

    pad = np.zeros((grid.shape[0], 1), dtype=bool)
    padded = np.concatenate([pad, grid, pad], axis=1).astype(np.int8)
    deltas = np.diff(padded, axis=1)
    _, starts = np.where(deltas == 1)
    _, ends = np.where(deltas == -1)
    longest_run = int((ends - starts).max()) if starts.size else 0

    return max(longest_run / span, float(grid.mean(axis=1).max()))


def _axis_aligned_edge_fraction(pixels) -> float:
    """Share of the image's edges that run along one of the two axes.

    Tick marks, spines, gridlines and bar sides are all axis-aligned, so a plot is strongly
    bimodal here; a photograph's edges point everywhere.
    """
    grey = pixels.mean(axis=2)
    if min(grey.shape) < 3:
        return 0.0
    horizontal = np.abs(np.diff(grey, axis=1))[:-1, :]
    vertical = np.abs(np.diff(grey, axis=0))[:, :-1]
    strong = np.maximum(horizontal, vertical) >= EDGE_STRENGTH
    if not strong.any():
        return 0.0
    across, down = horizontal[strong], vertical[strong]
    aligned = ((across >= AXIS_ALIGNED_RATIO * down)
               | (down >= AXIS_ALIGNED_RATIO * across))
    return float(aligned.mean())


_PLOT_CAPTION_HINTS = re.compile(
    r"\bvs\.?\b|\bversus\b|\bas\s+a\s+function\s+of\b|\bover\s+(?:time|storage)\b"
    r"|\bstorage\s+(?:day|time|period)\b|\bchanges?\s+(?:in|of)\b|\bevolution\s+of\b"
    r"|\bcurve\b|\bkinetics?\b|\bgrowth\b|\bcount\b|\baxis\b"
    r"|\blog\s*(?:10)?\s*cfu\b|\bmg\s*/\s*\d*\s*(?:g|kg|ml|l)\b|\bday\s*\d+\b|\b\d+\s*°\s*c\b",
    re.IGNORECASE)
_PHOTO_CAPTION_HINTS = re.compile(
    r"\bphotograph\b|\bphotos?\b|\bappearance\b|\bvisual\s+aspect\b|\bmicrograph\b"
    r"|\bscanning\s+electron\b|\btransmission\s+electron\b|\b(?:sem|tem)\s+(?:image|micrograph)\b"
    r"|\bschematic\b|\bflow\s*[- ]?chart\b|\bdiagram\s+of\b|\bapparatus\b|\bset[- ]?up\b",
    re.IGNORECASE)


def caption_plot_verdict(*texts) -> str:
    """"plot", "photo" or "unknown" from the words around a figure.

    A caption naming both is unknown: one of the two patterns matched something incidental.
    """
    joined = " ".join(str(text or "") for text in texts)
    if not joined.strip():
        return "unknown"
    says_plot = bool(_PLOT_CAPTION_HINTS.search(joined))
    says_photo = bool(_PHOTO_CAPTION_HINTS.search(joined))
    if says_plot == says_photo:
        return "unknown"
    return "plot" if says_plot else "photo"


def plot_likeness(image_path: str, *, caption=None, nearby_text=None) -> PlotProbe:
    """Cheap, content-free test for "this image could be a data display".

    The caption- and edge-based filters are off by default and gated on settings: all of
    them reject real charts as well as photographs, and the share they would reject is
    worth reading off the gate report before any is switched on.
    """
    try:
        image = Image.open(image_path).convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        return PlotProbe(plot_like=False, reason=f"unreadable image ({exc})")

    verdict = caption_plot_verdict(caption, nearby_text)
    # The caption on its own, for the strict filter. Judged separately because
    # `nearby_text` is FIGURE_CONTEXT_CHARS of surrounding prose, and words like "growth",
    # "count" or "storage day" appear near almost every figure in a shelf-life paper --
    # read together they call nearly everything a plot, which is no filter at all.
    own_verdict = caption_plot_verdict(caption)
    verdicts = {"caption_verdict": verdict, "own_caption_verdict": own_verdict}
    width, height = image.size
    aspect = width / height if height else 0.0
    if not (ASPECT_BOUNDS[0] <= aspect <= ASPECT_BOUNDS[1]):
        return PlotProbe(False, f"aspect ratio {aspect:.2f} outside plot range", width, height,
                         **verdicts)

    if min(width, height) < MIN_SIDE_PX or width * height < MIN_AREA_PX:
        return PlotProbe(False, "too small to be a data display", width, height, **verdicts)

    scale = PROBE_LONG_SIDE / max(width, height)
    if scale < 1.0:
        image = image.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))), Image.BILINEAR
        )
    pixels = np.asarray(image, dtype=np.int16)

    quantised = (pixels // COLOUR_STEP).astype(np.uint8)
    codes = (quantised[..., 0] * COLOUR_LEVELS ** 2
             + quantised[..., 1] * COLOUR_LEVELS + quantised[..., 2])
    counts = np.bincount(codes.ravel(), minlength=COLOUR_LEVELS ** 3)
    ground_code = int(counts.argmax())
    background_fraction = float(counts.max()) / codes.size

    ground = pixels[codes == ground_code].mean(axis=0)
    ink = (np.abs(pixels - ground).max(axis=2) > INK_THRESHOLD)
    ink_fraction = float(ink.mean())

    probe = PlotProbe(
        plot_like=False,
        reason="",
        width=width,
        height=height,
        background_fraction=background_fraction,
        ink_fraction=ink_fraction,
        distinct_colours=int((counts > 0).sum()),
        **verdicts,
    )

    if background_fraction < MIN_BACKGROUND_FRACTION:
        probe.reason = "no uniform ground — photographic or dense imagery"
        return probe
    if ink_fraction > MAX_INK_FRACTION:
        probe.reason = "image is mostly ink"
        return probe
    if ink_fraction < MIN_INK_FRACTION:
        probe.reason = "image is effectively blank"
        return probe

    probe.h_rule = _rule_span(ink, axis=1)
    probe.v_rule = _rule_span(ink, axis=0)
    if probe.h_rule < MIN_RULE_SPAN or probe.v_rule < MIN_RULE_SPAN:
        probe.reason = "no axis-like rules in both directions"
        return probe

    probe.axis_aligned_edges = _axis_aligned_edge_fraction(pixels)
    if _settings.FIGURE_EDGE_FILTER and probe.axis_aligned_edges < MIN_AXIS_ALIGNED_EDGES:
        probe.reason = (f"only {probe.axis_aligned_edges:.0%} of edges run along an axis "
                        "— photographic rather than drawn")
        return probe
    if _settings.FIGURE_CAPTION_FILTER and verdict == "photo":
        probe.reason = "the caption calls it a photograph, micrograph or schematic"
        return probe
    if _settings.FIGURE_REQUIRE_PLOT_CAPTION and own_verdict != "plot":
        probe.reason = ("the caption does not name a plotted quantity "
                        f"(reads as {own_verdict})")
        return probe

    probe.plot_like = True
    probe.reason = "uniform ground with rules on both axes"
    return probe
