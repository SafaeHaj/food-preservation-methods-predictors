"""Bridge to R's frailtypack for the Weibull shared-frailty refit.

Deliberately thin: write a CSV, make **one** Rscript call, read CSVs back. The fold loop
lives inside the R script, so k-fold CV costs one subprocess rather than k.

On resolving Rscript
--------------------
`Rscript` is not assumed to be on PATH, because on the machine this was built for it is
not, and `R_HOME` is unset. Resolution order: explicit config -> `R_HOME` -> the Windows
registry key R's own installer writes (`HKLM\\SOFTWARE\\R-core\\R`) -> PATH.

On the library path
-------------------
R's system library under `Program Files` is not writable without elevation, so packages
live in a per-user library. `R_LIBS_USER` is passed into the subprocess explicitly rather
than hoped for.

There is no silent fallback. If R or frailtypack is missing, this raises with the exact
commands needed -- the stage-2 frailty fit was chosen deliberately, and quietly returning
a frailty-free model that *looks* like it worked would be the worst outcome available.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from app.core.config import RConfig

R_SCRIPT = Path(__file__).resolve().parents[2] / "r" / "frailty_fit.R"

_INSTALL_HINT = """\
frailtypack is required for the Weibull shared-frailty stage-2 fit.

  1. Install R (if absent):
       winget install --id RProject.R --exact
  2. Create a personal library and install frailtypack into it -- the library under
     "Program Files" is not writable without elevation, and a bare install.packages()
     under Rscript will try to prompt for one and fail non-interactively:
       $lib = "$env:LOCALAPPDATA\\R\\win-library\\4.6"
       New-Item -ItemType Directory -Force -Path $lib
       & "C:\\Program Files\\R\\R-4.6.1\\bin\\x64\\Rscript.exe" -e \\
         "install.packages('frailtypack', lib='<lib>', repos='https://cloud.r-project.org')"

Or set model.weibull_aft.use_r_frailty: false to fall back to the stage-1 unpenalized
refit (documented, no frailty term).\
"""


class RNotAvailableError(RuntimeError):
    """R, Rscript, or frailtypack could not be found."""


@dataclass
class FrailtyFit:
    """What frailtypack returned, plus the AFT view of it."""

    terms: list[str]
    beta_ph: np.ndarray          # proportional-hazards coefficients
    vcov_ph: np.ndarray          # covariance of beta_ph (frailtypack's varH)
    shape: float                 # Weibull shape a   (from shape.weib[1])
    scale: float                 # Weibull scale b   (from scale.weib[1])
    theta: float                 # gamma frailty variance
    var_theta: float
    converged: bool
    loglik: float
    n: int
    n_events: int
    n_groups: int
    cv_pred: pd.DataFrame | None = None

    @property
    def sigma(self) -> float:
        """AFT scale. Weibull shape a = 1/sigma."""
        return 1.0 / self.shape

    def aft_coef(self) -> np.ndarray:
        """PH -> AFT.

        For a Weibull PH model S(t|x) = exp(-(t/b)^a * e^{x'beta}), so
        log t_med = log b + (1/a)(log log 2 - x'beta): the AFT coefficient is -beta/a.
        Weibull is the only distribution that is simultaneously PH and AFT, which is what
        makes this exact rather than an approximation.
        """
        return -self.beta_ph / self.shape

    def time_ratios(self) -> np.ndarray:
        return np.exp(self.aft_coef())

    def aft_intercept(self) -> float:
        return float(np.log(self.scale))


def resolve_rscript(config: RConfig | None = None) -> str:
    """Locate Rscript. Raises :class:`RNotAvailableError` with actionable text."""
    if config is not None and config.rscript_path:
        p = Path(config.rscript_path)
        if not p.exists():
            raise RNotAvailableError(f"configured r.rscript_path does not exist: {p}")
        return str(p)

    r_home = os.environ.get("R_HOME")
    if r_home:
        for rel in ("bin/x64/Rscript.exe", "bin/Rscript.exe", "bin/Rscript"):
            cand = Path(r_home) / rel
            if cand.exists():
                return str(cand)

    if platform.system() == "Windows":
        found = _rscript_from_registry()
        if found:
            return found

    on_path = shutil.which("Rscript")
    if on_path:
        return on_path

    raise RNotAvailableError(
        "Rscript not found (checked config, R_HOME, Windows registry, PATH).\n\n" + _INSTALL_HINT
    )


def _rscript_from_registry() -> str | None:
    """Read R's install path from the registry key its own installer writes."""
    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows
        return None
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key in (r"SOFTWARE\R-core\R", r"SOFTWARE\WOW6432Node\R-core\R"):
            try:
                with winreg.OpenKey(root, key) as k:
                    install_path, _ = winreg.QueryValueEx(k, "InstallPath")
            except OSError:
                continue
            for rel in ("bin/x64/Rscript.exe", "bin/Rscript.exe"):
                cand = Path(install_path) / rel
                if cand.exists():
                    return str(cand)
    return None


def resolve_lib_path(config: RConfig | None = None) -> str | None:
    """The per-user R library, since the system one is not writable."""
    if config is not None and config.lib_path:
        return config.lib_path
    if platform.system() != "Windows":
        return None
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    base = Path(local) / "R" / "win-library"
    if not base.exists():
        return None
    versions = sorted((d for d in base.iterdir() if d.is_dir()), reverse=True)
    return str(versions[0]) if versions else None


def check_frailtypack(config: RConfig | None = None) -> bool:
    """True when Rscript exists and can load frailtypack."""
    try:
        rscript = resolve_rscript(config)
    except RNotAvailableError:
        return False
    try:
        res = subprocess.run(
            [rscript, "-e", "cat(requireNamespace('frailtypack', quietly=TRUE))"],
            capture_output=True,
            text=True,
            timeout=120,
            env=_subprocess_env(config),
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return "TRUE" in res.stdout


def _subprocess_env(config: RConfig | None) -> dict[str, str]:
    env = dict(os.environ)
    lib = resolve_lib_path(config)
    if lib:
        env["R_LIBS_USER"] = lib
    return env


def run_frailty_fit(
    X: pd.DataFrame,
    y_time: np.ndarray,
    y_event: np.ndarray,
    groups: np.ndarray,
    folds: np.ndarray | None = None,
    config: RConfig | None = None,
) -> FrailtyFit:
    """Fit a Weibull shared gamma-frailty model in R. One subprocess, folds looped in R."""
    rscript = resolve_rscript(config)
    if not check_frailtypack(config):
        raise RNotAvailableError(_INSTALL_HINT)

    # Feature names go over as V1..Vp: real ones contain characters R rejects as symbols
    # (e.g. "ctx__Packaging__active-antimicrobial").
    safe = {f"V{i + 1}": col for i, col in enumerate(X.columns)}
    payload = pd.DataFrame({v: X[col].to_numpy(dtype=float) for v, col in safe.items()})
    payload.insert(0, "row_id", np.arange(len(X)))
    payload["t_failure"] = np.asarray(y_time, dtype=float)
    payload["event"] = np.asarray(y_event, dtype=int)
    payload["experiment_id"] = np.asarray(groups).astype(str)
    if folds is not None:
        payload["fold"] = np.asarray(folds, dtype=int)

    timeout = config.timeout_seconds if config else 600
    with tempfile.TemporaryDirectory(prefix="shelflife_r_") as tmp:
        tmpdir = Path(tmp)
        data_csv = tmpdir / "data.csv"
        out_dir = tmpdir / "out"
        # utf-8 without a BOM: R's parser rejects a BOM outright.
        payload.to_csv(data_csv, index=False, encoding="utf-8")

        proc = subprocess.run(
            [rscript, str(R_SCRIPT), str(data_csv), str(out_dir)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_subprocess_env(config),
        )
        if proc.returncode != 0 or not (out_dir / "meta.csv").exists():
            raise RuntimeError(
                "frailty_fit.R failed\n"
                f"--- exit {proc.returncode} ---\n"
                f"--- stdout ---\n{proc.stdout}\n"
                f"--- stderr ---\n{proc.stderr}"
            )
        return _read_outputs(out_dir, safe)


def _read_outputs(out_dir: Path, safe: dict[str, str]) -> FrailtyFit:
    meta = pd.read_csv(out_dir / "meta.csv").set_index("key")["value"]
    coef = pd.read_csv(out_dir / "coef.csv")
    vcov = pd.read_csv(out_dir / "vcov.csv")

    terms = [safe[v] for v in coef["term"]]
    vc = vcov.drop(columns=["term"]).to_numpy(dtype=float)

    cv_pred = None
    cv_path = out_dir / "cv_pred.csv"
    if cv_path.exists():
        cv_pred = pd.read_csv(cv_path)

    return FrailtyFit(
        terms=terms,
        beta_ph=coef["beta_ph"].to_numpy(dtype=float),
        vcov_ph=vc,
        shape=float(meta["shape_weib"]),
        scale=float(meta["scale_weib"]),
        theta=float(meta["theta"]),
        var_theta=float(meta["var_theta"]),
        converged=int(meta["istop"]) == 1,
        loglik=float(meta["loglik"]),
        n=int(meta["n"]),
        n_events=int(meta["n_events"]),
        n_groups=int(meta["n_groups"]),
        cv_pred=cv_pred,
    )
