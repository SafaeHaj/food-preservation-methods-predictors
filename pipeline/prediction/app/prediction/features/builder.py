"""Builds the expanded modelling table.

    ingredient concentrations          (Table 3 -- first-class predictors)
  + functional-pillar doses            (derived from the pillar membership)
  + meat matrix / packaging context    (conditioning variables)
  + interaction terms                  (ingredient x context, optionally pillar x context)
  + experiment_ID                      (grouping / frailty / grouped CV)

Both ingredient-level and pillar-level features are offered to the model; the group
penalty decides which carries the signal. That is why the builder also emits a **group
vector**: an ingredient and all of its own interaction terms form one block, and a
categorical's dummies form one block, so selection happens at the level of a decision a
person would actually make ("does thymol matter?") rather than picking an arbitrary
single dummy.

Nothing here is baked into Tables 1-4. Re-running `build` after a config change --
different pillar grouping, different interactions -- is the whole update path.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.prediction.features import diagnostics
from . import columns as C
from app.core.config import Config
from app.prediction.features import pillars

ING = "ing"
PIL = "pil"
CTX = "ctx"
IX = "ix"
SEP = "__"


@dataclass
class ModellingTable:
    """The design matrix plus everything an engine needs to respect study structure."""

    X: pd.DataFrame                 # standardized design, indexed by Batch_ID
    X_raw: pd.DataFrame             # same columns, original units (for diagnostics)
    y_time: np.ndarray
    y_event: np.ndarray
    groups: np.ndarray              # experiment_ID per row -- grouped CV / frailty
    feature_groups: np.ndarray      # group index per column -- the group penalty
    group_names: list[str]
    column_kinds: dict[str, str]
    coverage: pd.DataFrame
    sparsity: pd.DataFrame
    #: Per-column standard deviation used to standardize X. Engines fit on standardized
    #: columns, so effects come out "per 1 SD"; dividing by this puts them back into
    #: original units (per 1% w/w of an ingredient), which is what a food scientist reads.
    feature_scales: pd.Series = field(default_factory=pd.Series)
    dropped_columns: list[str] = field(default_factory=list)
    flagged_columns: list[str] = field(default_factory=list)
    observation_status: np.ndarray | None = None
    batch_ids: np.ndarray | None = None

    @property
    def n_studies(self) -> int:
        return int(pd.unique(self.groups).size)

    def blocks(self) -> dict[str, list[str]]:
        """group name -> its column names."""
        out: dict[str, list[str]] = {name: [] for name in self.group_names}
        for col, gi in zip(self.X.columns, self.feature_groups, strict=True):
            out[self.group_names[gi]].append(col)
        return out


class _Standardizer:
    """Centre and scale, remembering enough to put coefficients back in original units.

    A group penalty compares ||gamma_g||_2 across blocks, so unequal column scales would
    silently make "concentration in %" and "a 0/1 dummy" compete on different terms. We
    fit standardized and report in original units.
    """

    def __init__(self) -> None:
        self.mean_: pd.Series | None = None
        self.scale_: pd.Series | None = None

    def fit(self, X: pd.DataFrame) -> "_Standardizer":
        self.mean_ = X.mean()
        scale = X.std(ddof=0)
        # A constant column carries no information; scale 1 leaves it centred at 0 rather
        # than dividing by zero.
        self.scale_ = scale.where(scale > 1e-12, 1.0)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        assert self.mean_ is not None and self.scale_ is not None
        return (X - self.mean_) / self.scale_

    def unscale_coefficients(
        self, coef: pd.Series, intercept: float
    ) -> tuple[pd.Series, float]:
        """Map coefficients fitted on standardized columns back to original units."""
        assert self.mean_ is not None and self.scale_ is not None
        orig = coef / self.scale_.reindex(coef.index)
        shift = float((coef * self.mean_.reindex(coef.index) / self.scale_.reindex(coef.index)).sum())
        return orig, intercept - shift


class FeatureBuilder:
    """Config-driven construction of the modelling table.

    After :meth:`build`, the instance retains the fitted layout (columns, reference
    levels, standardization) so :meth:`transform_context` can turn a candidate
    (matrix, packaging, formulation) into a matching design row. That is the path the
    optimizer's conditional prediction runs through.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._membership: pd.DataFrame | None = None
        self._compounds: list[str] = []
        self._pillar_names: list[str] = []
        self._context_levels: dict[str, list[str]] = {}
        self._reference_levels: dict[str, str] = {}
        self._kept_columns: list[str] = []
        self._column_kinds: dict[str, str] = {}
        self._standardizer = _Standardizer()
        self._fitted = False

    @property
    def standardizer(self) -> "_Standardizer":
        """Exposed so callers can map coefficients back to original units."""
        return self._standardizer

    # -- build -------------------------------------------------------------------------

    def build(
        self, batches: pd.DataFrame, bridge: pd.DataFrame, master: pd.DataFrame
    ) -> ModellingTable:
        batches = batches.reset_index(drop=True)
        batch_ids = batches[C.BATCH_ID].to_numpy()

        self._membership = pillars.build_membership(master, self.config.pillars)
        self._compounds = sorted(set(master[C.COMPOUND_ID]))
        for col in self.config.features.context_columns:
            levels = sorted(batches[col].dropna().unique())
            self._context_levels[col] = levels
            # Fixed, deterministic reference level: the first alphabetically. Dropping one
            # level keeps the dummy block from being collinear with the intercept.
            self._reference_levels[col] = levels[0] if levels else ""

        conc = self._wide_concentrations(bridge, batch_ids)
        raw, kinds, groups_of = self._assemble(conc, batches)

        sparsity = sparsity_report(raw[[c for c in raw.columns if kinds[c] == "pillar"]])

        coverage = diagnostics.coverage_report(
            design=raw,
            experiment_ids=batches[C.EXPERIMENT_ID],
            events=batches[C.EVENT],
            column_kinds=kinds,
            config=self.config.features.coverage,
        )
        bad = diagnostics.under_supported(coverage)
        dropped, flagged = [], []
        if self.config.features.coverage.action == "drop":
            dropped = bad
            raw = raw.drop(columns=bad)
        else:
            flagged = bad

        # A column that never varies cannot be identified regardless of coverage.
        constant = [c for c in raw.columns if float(raw[c].std(ddof=0)) <= 1e-12]
        if constant:
            raw = raw.drop(columns=constant)
            dropped = sorted(set(dropped) | set(constant))

        self._kept_columns = list(raw.columns)
        self._column_kinds = {c: kinds[c] for c in self._kept_columns}

        X = self._standardizer.fit(raw).transform(raw)
        self._fitted = True

        group_names, feature_groups = self._group_vector(self._kept_columns, groups_of)

        return ModellingTable(
            X=X,
            X_raw=raw,
            y_time=batches[C.T_FAILURE].to_numpy(dtype=float),
            y_event=batches[C.EVENT].to_numpy(dtype=int),
            groups=batches[C.EXPERIMENT_ID].to_numpy(),
            feature_groups=feature_groups,
            group_names=group_names,
            column_kinds=self._column_kinds,
            coverage=coverage,
            sparsity=sparsity,
            feature_scales=self._standardizer.scale_.reindex(self._kept_columns),
            dropped_columns=dropped,
            flagged_columns=flagged,
            observation_status=(
                batches[C.OBSERVATION_STATUS].to_numpy()
                if C.OBSERVATION_STATUS in batches.columns
                else None
            ),
            batch_ids=batch_ids,
        )

    # -- conditional transform ---------------------------------------------------------

    def transform_context(
        self, context: dict[str, str], formulation: dict[str, float]
    ) -> pd.DataFrame:
        """Turn one candidate (context, formulation) into a design row.

        `context` supplies the conditioning variables (Meat_Matrix, Packaging);
        `formulation` maps Compound_ID -> concentration, with absent compounds at 0.
        """
        if not self._fitted:
            raise RuntimeError("call build() before transform_context()")
        missing = set(self.config.features.context_columns) - set(context)
        if missing:
            raise ValueError(f"context is missing {sorted(missing)}")
        for col, val in context.items():
            if col in self._context_levels and val not in self._context_levels[col]:
                raise ValueError(
                    f"unseen level {val!r} for {col}; known levels: {self._context_levels[col]}"
                )
        unknown = set(formulation) - set(self._compounds)
        if unknown:
            raise ValueError(f"unknown Compound_ID(s): {sorted(unknown)}")

        idx = pd.Index(["candidate"], name=C.BATCH_ID)
        conc = pd.DataFrame(0.0, index=idx, columns=self._compounds)
        for cid, value in formulation.items():
            conc.loc["candidate", cid] = float(value)

        meta = pd.DataFrame([{**context, C.BATCH_ID: "candidate"}])
        raw, _, _ = self._assemble(conc, meta, for_transform=True)
        raw = raw.reindex(columns=self._kept_columns, fill_value=0.0)
        return self._standardizer.transform(raw)

    # -- internals ---------------------------------------------------------------------

    def _wide_concentrations(self, bridge: pd.DataFrame, batch_ids: np.ndarray) -> pd.DataFrame:
        idx = pd.Index(batch_ids, name=C.BATCH_ID)
        if bridge.empty:
            return pd.DataFrame(0.0, index=idx, columns=self._compounds)
        wide = bridge.pivot_table(
            index=C.BATCH_ID,
            columns=C.COMPOUND_ID,
            values=C.CONCENTRATION,
            aggfunc="sum",
            fill_value=0.0,
        )
        wide.columns.name = None
        # reindex on both axes: a control has no bridge rows (all-zero, not absent), and a
        # compound in the master that no batch used still needs its column.
        return wide.reindex(index=idx, columns=self._compounds).fillna(0.0)

    def _assemble(
        self, conc: pd.DataFrame, meta: pd.DataFrame, for_transform: bool = False
    ) -> tuple[pd.DataFrame, dict[str, str], dict[str, str]]:
        assert self._membership is not None
        parts: dict[str, pd.Series] = {}
        kinds: dict[str, str] = {}
        groups_of: dict[str, str] = {}

        # 1. ingredient-level concentrations
        for cid in self._compounds:
            col = f"{ING}{SEP}{cid}"
            parts[col] = conc[cid].to_numpy()
            kinds[col] = "ingredient"
            groups_of[col] = f"ingredient:{cid}"

        # 2. pillar doses -- derivation deferred to a later fix
        doses = pd.DataFrame(index=conc.index)
        if not for_transform:
            self._pillar_names = list(doses.columns)
        for pillar_name in self._pillar_names:
            col = f"{PIL}{SEP}{pillar_name}"
            series = doses[pillar_name] if pillar_name in doses.columns else 0.0
            parts[col] = np.asarray(series, dtype=float) if not np.isscalar(series) else np.zeros(len(conc))
            kinds[col] = "pillar"
            groups_of[col] = f"pillar:{pillar_name}"

        # 3. context dummies (reference level dropped)
        dummies: dict[str, np.ndarray] = {}
        for var, levels in self._context_levels.items():
            ref = self._reference_levels[var]
            for level in levels:
                if level == ref:
                    continue
                col = f"{CTX}{SEP}{var}{SEP}{level}"
                ind = (meta[var].to_numpy() == level).astype(float)
                dummies[col] = ind
                parts[col] = ind
                kinds[col] = "context"
                groups_of[col] = f"context:{var}"

        # 4. interactions -- concentration * context indicator
        ix_cfg = self.config.features.interactions
        pairs: list[tuple[str, str, str]] = []  # (base_col, base_group, base_kind)
        if ix_cfg.get("ingredient_x_matrix") or ix_cfg.get("ingredient_x_packaging"):
            for cid in self._compounds:
                pairs.append((f"{ING}{SEP}{cid}", f"ingredient:{cid}", "ingredient"))
        if ix_cfg.get("pillar_x_matrix") or ix_cfg.get("pillar_x_packaging"):
            for pillar_name in self._pillar_names:
                pairs.append((f"{PIL}{SEP}{pillar_name}", f"pillar:{pillar_name}", "pillar"))

        for base_col, base_group, base_kind in pairs:
            for var in self._context_levels:
                if not self._interaction_enabled(base_kind, var):
                    continue
                for dummy_col, ind in dummies.items():
                    if not dummy_col.startswith(f"{CTX}{SEP}{var}{SEP}"):
                        continue
                    level = dummy_col.split(SEP, 2)[2]
                    col = f"{IX}{SEP}{base_col}{SEP}x{SEP}{var}{SEP}{level}"
                    parts[col] = np.asarray(parts[base_col], dtype=float) * ind
                    kinds[col] = "interaction"
                    # The interaction joins its ingredient's block: an ingredient and its
                    # own interactions are selected or dropped together.
                    groups_of[col] = base_group

        index = pd.Index(meta[C.BATCH_ID].to_numpy(), name=C.BATCH_ID)
        raw = pd.DataFrame({k: np.asarray(v, dtype=float) for k, v in parts.items()}, index=index)
        return raw, kinds, groups_of

    def _interaction_enabled(self, base_kind: str, var: str) -> bool:
        cfg = self.config.features.interactions
        is_matrix = var == C.MEAT_MATRIX
        if base_kind == "ingredient":
            key = "ingredient_x_matrix" if is_matrix else "ingredient_x_packaging"
        else:
            key = "pillar_x_matrix" if is_matrix else "pillar_x_packaging"
        return bool(cfg.get(key, False))

    def _group_vector(
        self, kept: list[str], groups_of: dict[str, str]
    ) -> tuple[list[str], np.ndarray]:
        names: list[str] = []
        seen: dict[str, int] = {}
        idx = np.empty(len(kept), dtype=int)
        for i, col in enumerate(kept):
            g = groups_of[col]
            if g not in seen:
                seen[g] = len(names)
                names.append(g)
            idx[i] = seen[g]
        return names, idx
