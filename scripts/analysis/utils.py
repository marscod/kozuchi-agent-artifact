"""Common utilities for the Kozuchi analysis pipeline.

This module contains:
  * Path constants tied to the experiment layout (see README.md).
  * Statistical helpers (Wilson score interval, McNemar exact test).
  * Light-weight helpers for repository / year extraction and patch
    structure parsing.

The whole analysis pipeline assumes the canonical SWE-bench Verified
benchmark of N = 500 instances, regardless of how many trajectories
or per-instance logs are present on disk.  Missing artifacts are
treated as a hard failure (counted as unresolved with a "missing"
artifact tag) so that aggregate metrics are not biased upwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
import re

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[5]
"""Path to the repository root (`/home/.../swe-sota-agent`)."""

EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
"""Path to the Kozuchi experiment directory."""

EVAL_DIR = EXPERIMENT_DIR.parent
"""Path to `experiments/evaluation/verified/`."""

LOGS_DIR = EXPERIMENT_DIR / "logs"
TRAJS_DIR = EXPERIMENT_DIR / "trajs"
RESULTS_JSON = EXPERIMENT_DIR / "results" / "results.json"

# Path to the unzipped 8-leg TTS trajectory bundle that ships with
# the submission.  This is the artifact that exposes the 8 raw
# Best-of-8 candidate trajectories *before* the cross-check selector
# collapses them down to a single submission patch.  Used by
# ``analyze_tts.py`` to recover per-leg report.json (harness eval of
# every individual leg) and the xcheck instance_test_tables
# (per-instance per-suite test outcomes used by the selector).
TRAJ_BUNDLE_DIR = (
    REPO_ROOT
    / "trajectories"
    / "q35_verified500_tts8_75p2_submission_bundle_20260326-055715_merged500"
)

CSV_DIR = EXPERIMENT_DIR / "src" / "csv"
"""All generated CSV tables are written here.  Tracked in git so a
reader of ``analysis.md`` (e.g. on GitHub) can browse the tables
without re-running ``build.sh``."""

FIG_DIR = EXPERIMENT_DIR / "src" / "figures"
"""All generated PNG figures are written here.  Tracked in git so
the image references in ``analysis.md`` resolve when the document
is viewed via the GitHub web UI or any other Markdown renderer."""

# SWE-bench Verified is fixed at N = 500 instances.  We use this as
# the canonical denominator for every aggregate metric -- if a
# trajectory or log is missing, the underlying instance is still
# counted as a *failure* of the agent, never silently dropped.
N_VERIFIED = 500

# Canonical schedule of phases used by Kozuchi mini-swe-agent.
PHASES_ORDERED: list[str] = [
    "ISSUE_REPRODUCT",
    "TEST_SYNTHSIZE",
    "CODE_LOCALIZE",
    "TEST_LOCALIZE",
    "CODE_FIX",
    "VERIFY_PATCH",
    "ISSUE_CLOSE",
    "FINAL_REPORT",
]


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def ensure_out_dirs() -> None:
    """Create the CSV / figure output directories if they do not exist."""

    CSV_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)


def repo_of(instance_id: str) -> str:
    """Return the canonical "<owner>/<repo>" string for an instance.

    SWE-bench instance ids are of the form
    ``<owner>__<name>-<issue_number>`` where ``<name>`` may itself
    contain ``-`` characters (e.g. ``sphinx-doc``,
    ``scikit-learn``).  We therefore split on ``__`` first and then
    strip the trailing ``-<issue_number>`` from the right.
    """

    owner, _, rest = instance_id.partition("__")
    if not rest:
        return instance_id
    name, _, _ = rest.rpartition("-")
    return f"{owner}/{name}"


def load_verified_instance_set(canonical_path: Path | None = None) -> set[str]:
    """Return the canonical 500-instance SWE-bench Verified instance set.

    To stay self-contained, we reconstruct the set by unioning all
    instance ids referenced by *any* legacy submission's
    ``results/results.json``.  We default to
    ``20231010_rag_claude2`` because it explicitly enumerates every
    instance in its bucketed lists (no_generation/generated/etc.) and
    is therefore guaranteed to cover N = 500.
    """

    if canonical_path is None:
        canonical_path = EVAL_DIR / "20231010_rag_claude2" / "results" / "results.json"
    data = json.loads(canonical_path.read_text())
    out: set[str] = set()
    for v in data.values():
        if isinstance(v, list):
            out.update(v)
    if len(out) != N_VERIFIED:
        raise RuntimeError(
            f"Expected {N_VERIFIED} instances; reconstructed {len(out)} from {canonical_path}"
        )
    return out


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WilsonCI:
    """A Wilson score 95% confidence interval for a binomial proportion."""

    lo: float
    hi: float
    p: float
    n: int


def wilson_ci(k: int, n: int, z: float = 1.959964) -> WilsonCI:
    """Compute a Wilson score 95% CI for ``k`` successes out of ``n``.

    Using the Wilson interval is the standard reporting practice on
    SWE-bench because it remains well-defined for ``k = 0`` or
    ``k = n`` and corrects the asymmetry of the normal-approximation
    interval at the extremes -- both of which appear in our per-repo
    breakdown (e.g. flask 1/1, pylint 3/10).
    """

    if n == 0:
        return WilsonCI(0.0, 0.0, 0.0, 0)
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return WilsonCI(max(0.0, centre - half), min(1.0, centre + half), p, n)


def mcnemar_exact_p(b: int, c: int) -> float:
    """Two-sided exact-binomial McNemar p-value for paired binary outcomes.

    ``b`` and ``c`` are the off-diagonal counts of a paired 2x2
    contingency table: ``b`` instances where method A succeeds and B
    fails, and ``c`` instances where the reverse holds.  This routine
    computes the exact two-sided p-value under the null
    ``Pr(success_A) = Pr(success_B)`` without relying on SciPy so we
    can run on a minimal interpreter.
    """

    n = b + c
    if n == 0:
        return 1.0
    # Two-sided exact binomial test on min(b, c) ~ Binomial(n, 0.5).
    k = min(b, c)
    p = 0.0
    for i in range(0, k + 1):
        p += math.comb(n, i) * (0.5 ** n)
    p_two = min(1.0, 2.0 * p)
    return p_two


# ---------------------------------------------------------------------------
# Patch structure parsing
# ---------------------------------------------------------------------------


_DIFF_FILE_RE = re.compile(r"^diff --git a/(?P<a>.+) b/(?P<b>.+)$")
_HUNK_RE = re.compile(r"^@@ ")


@dataclass
class PatchStats:
    """Lightweight representation of a unified diff."""

    files: tuple[str, ...] = ()
    hunks: int = 0
    added: int = 0
    removed: int = 0
    is_empty: bool = True

    @property
    def churn(self) -> int:
        """Total LOC churn (added + removed)."""
        return self.added + self.removed

    @property
    def net(self) -> int:
        """Net change in LOC (added - removed); negative means deletion-heavy."""
        return self.added - self.removed


def parse_patch(diff_text: str) -> PatchStats:
    """Parse a unified diff produced by ``git diff``.

    We only inspect the structural skeleton -- the file headers,
    hunk markers, and ``+``/``-`` lines -- which is enough to power
    every patch-level metric in the analysis.
    """

    files: list[str] = []
    hunks = 0
    added = 0
    removed = 0
    in_body = False
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            m = _DIFF_FILE_RE.match(line)
            if m:
                files.append(m.group("b"))
            in_body = False
            continue
        if _HUNK_RE.match(line):
            hunks += 1
            in_body = True
            continue
        if not in_body:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return PatchStats(
        files=tuple(files),
        hunks=hunks,
        added=added,
        removed=removed,
        is_empty=(added == 0 and removed == 0),
    )


# ---------------------------------------------------------------------------
# Streaming-ish trajectory parsing
# ---------------------------------------------------------------------------


_PHASE_TOKEN_RE = re.compile(r"^WORKFLOW:\s*(\S+)")


def parse_workflow_token(content: str) -> str | None:
    """Return the WORKFLOW token at the head of an assistant message.

    Each assistant turn under the Kozuchi prompt starts with a
    ``WORKFLOW: Wn`` self-check, or one of the special exit tokens
    ``COMPLETE`` / ``GIVEUP``.  We use this token to drive every
    phase-level metric.
    """

    if not content:
        return None
    line = content.lstrip().split("\n", 1)[0].strip()
    m = _PHASE_TOKEN_RE.match(line)
    return m.group(1) if m else None


def percentile(xs: list[float] | np.ndarray, q: float) -> float:
    """Vectorised numpy percentile that returns 0 for empty inputs."""

    arr = np.asarray(xs, dtype=float)
    return float(np.percentile(arr, q)) if arr.size else 0.0
