"""The 3-tier / 7-leaf functional pillar structure.

Leaves are kept separate from tiers so no information is lost; `pillars.output_level`
decides what the feature builder emits. Switching 7-leaf -> 3-tier is a config change and
nothing more -- no table migration, because Tables 1-4 never store a pillar.

The 7-leaf vocabulary is NOT assumed exhaustive. Upstream currently emits functional
classes outside it (`peptide`, `lipid`, `chelating agent`, ...), and `fiber` never occurs
in real data at all. Unknown classes therefore route to an explicit unmapped bucket by
default; `unmapped_policy: error` makes them a hard failure instead. What must never
happen is a compound quietly vanishing from the pillar features because nobody mapped its
class.
"""

from __future__ import annotations

import pandas as pd

from . import columns as C
from app.core.config import PillarConfig

LEAF_PREFIX = "leaf"
TIER_PREFIX = "tier"
PILLAR = "Pillar"


class UnmappedFunctionalClassError(ValueError):
    """Raised under ``unmapped_policy: error`` when a class is outside the vocabulary."""


def build_membership(master: pd.DataFrame, config: PillarConfig) -> pd.DataFrame:
    """Map the ingredient master onto pillars.

    Returns a long frame with ``Compound_ID``, ``Pillar``, ``pillar_kind``
    (``leaf``/``tier``), the originating ``Functional_Class``, and the Table 4 metadata
    columns the feature builder reads.

    Under ``output_level: both`` a compound contributes to its leaf *and* its tier, so it
    appears in two rows -- deliberately, since that is the point of keeping leaves.
    """
    if master.empty:
        return pd.DataFrame(
            columns=[C.COMPOUND_ID, C.FUNCTIONAL_CLASS, PILLAR, "pillar_kind"]
        )

    unknown = sorted(set(master[C.FUNCTIONAL_CLASS]) - set(config.leaf_to_tier))
    if unknown and config.unmapped_policy == "error":
        raise UnmappedFunctionalClassError(
            f"functional class(es) {unknown} are outside the configured vocabulary "
            f"{sorted(config.leaf_to_tier)}; add them to pillars.leaf_to_tier or set "
            f"pillars.unmapped_policy: bucket"
        )

    rows: list[dict] = []
    for record in master.to_dict("records"):
        klass = record[C.FUNCTIONAL_CLASS]
        mapped = klass in config.leaf_to_tier
        leaf_name = klass if mapped else config.unmapped_bucket
        tier_name = config.leaf_to_tier.get(klass, config.unmapped_bucket)

        if config.output_level in ("leaf", "both"):
            rows.append(_row(record, f"{LEAF_PREFIX}__{leaf_name}", LEAF_PREFIX))
        if config.output_level in ("tier", "both"):
            rows.append(_row(record, f"{TIER_PREFIX}__{tier_name}", TIER_PREFIX))

    out = pd.DataFrame(rows)
    # `both` can produce duplicate (compound, pillar) rows when two leaves share a tier;
    # summing the same concentration twice into one tier would double count it.
    return out.drop_duplicates(subset=[C.COMPOUND_ID, PILLAR]).reset_index(drop=True)


def _row(record: dict, pillar: str, kind: str) -> dict:
    return {
        C.COMPOUND_ID: record[C.COMPOUND_ID],
        C.FUNCTIONAL_CLASS: record[C.FUNCTIONAL_CLASS],
        PILLAR: pillar,
        "pillar_kind": kind,
        C.POTENCY: record.get(C.POTENCY),
        C.MIC: record.get(C.MIC),
        C.ANTIOXIDANT_CAPACITY: record.get(C.ANTIOXIDANT_CAPACITY),
    }


def unmapped_classes(master: pd.DataFrame, config: PillarConfig) -> list[str]:
    """Functional classes present in the master but absent from the configured vocabulary."""
    if master.empty:
        return []
    return sorted(set(master[C.FUNCTIONAL_CLASS]) - set(config.leaf_to_tier))
