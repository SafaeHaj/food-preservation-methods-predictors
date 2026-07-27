"""Identifiability / coverage diagnostics.

With ingredient-level features plus ingredient x matrix and ingredient x packaging
interactions, the design matrix is large relative to the number of *independent studies*,
and many interaction cells have little or no support. A model can happily fit an
interaction resting on two batches from one study and report a confident time ratio for
it; that number is noise wearing a coefficient's clothes.

So for every interaction column we count what actually backs it -- independent studies and
non-censored events, not rows -- and let a threshold drop or flag it. Synthetic
augmentation upstream widens support, but this diagnostic still governs what is
trustworthy.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.config import CoverageConfig

COVERAGE_COLUMNS = [
    "column",
    "kind",
    "n_batches",
    "n_studies",
    "n_events",
    "supported",
    "reason",
]


def coverage_report(
    design: pd.DataFrame,
    experiment_ids: pd.Series,
    events: pd.Series,
    column_kinds: dict[str, str],
    config: CoverageConfig,
) -> pd.DataFrame:
    """Support for every design column; the threshold is applied to interactions only.

    A column "supports" a row when it is non-zero there -- that is, when the row actually
    exercises the term. Main effects are reported for context but never dropped: dropping
    an ingredient's main effect for thin support would silently change the model's
    meaning, and the group penalty is the right tool for that decision.
    """
    exp = np.asarray(experiment_ids)
    ev = np.asarray(events).astype(int)

    rows: list[dict] = []
    for col in design.columns:
        nz = np.asarray(design[col] != 0)
        n_batches = int(nz.sum())
        n_studies = int(pd.unique(exp[nz]).size) if n_batches else 0
        n_events = int(ev[nz].sum()) if n_batches else 0
        kind = column_kinds.get(col, "unknown")

        if kind != "interaction":
            supported, reason = True, "not an interaction; threshold not applied"
        elif n_studies < config.min_support_studies:
            supported = False
            reason = f"only {n_studies} study(ies) < min_support_studies={config.min_support_studies}"
        elif n_events < config.min_support_events:
            supported = False
            reason = f"only {n_events} event(s) < min_support_events={config.min_support_events}"
        else:
            supported, reason = True, "ok"

        rows.append(
            {
                "column": col,
                "kind": kind,
                "n_batches": n_batches,
                "n_studies": n_studies,
                "n_events": n_events,
                "supported": supported,
                "reason": reason,
            }
        )

    out = pd.DataFrame(rows, columns=COVERAGE_COLUMNS)
    return out.sort_values(
        ["supported", "n_studies", "column"], ascending=[True, True, True], ignore_index=True
    )


def under_supported(coverage: pd.DataFrame) -> list[str]:
    return coverage.loc[~coverage["supported"], "column"].tolist()


def summarize(coverage: pd.DataFrame) -> str:
    """One-line ASCII summary (Windows consoles are cp1252; keep output ASCII)."""
    ix = coverage[coverage["kind"] == "interaction"]
    bad = int((~ix["supported"]).sum())
    return (
        f"{len(ix)} interaction column(s); {bad} under-supported "
        f"({len(ix) - bad} usable)"
    )
