"""Common helpers for the Multi-SWE-Bench Java Kozuchi analysis."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from pathlib import Path
from typing import Any


EXPERIMENT_DIR = Path(__file__).resolve().parents[1]
VERIFIED_DIR = EXPERIMENT_DIR.parent
MULTI_SWE_REPO_ROOT = Path(__file__).resolve().parents[5]

INDEX_JSON = VERIFIED_DIR / "index.json"
LOGS_DIR = EXPERIMENT_DIR / "logs"
TRAJS_DIR = EXPERIMENT_DIR / "trajs"
RESULTS_JSON = EXPERIMENT_DIR / "results" / "results.json"
ALL_PREDS_JSONL = EXPERIMENT_DIR / "all_preds.jsonl"
CSV_DIR = EXPERIMENT_DIR / "src" / "csv"
FIG_DIR = EXPERIMENT_DIR / "src" / "figures"

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


def ensure_out_dirs() -> None:
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def load_java_index() -> dict[str, list[str]]:
    return load_json(INDEX_JSON)


def load_all_ids() -> list[str]:
    return list(load_java_index()["all_ids"])


def load_difficulty_map() -> dict[str, str]:
    data = load_java_index()
    out: dict[str, str] = {}
    for difficulty in ("easy", "medium", "hard"):
        for iid in data.get(f"{difficulty}_ids", []):
            out[iid] = difficulty
    return out


def load_results() -> dict[str, Any]:
    return load_json(RESULTS_JSON)


def to_leaderboard_id(raw_id: str) -> str:
    """Normalize common Multi-SWE raw ids to leaderboard ids.

    The experiments repo uses ``owner__repo-123``.  Some Multi-SWE tooling
    emits ``owner/repo:pr-123``; this helper accepts both.
    """

    iid = str(raw_id).strip()
    if "__" in iid:
        return iid
    if ":pr-" in iid and "/" in iid:
        repo_part, number = iid.split(":pr-", 1)
        owner, repo = repo_part.split("/", 1)
        return f"{owner}__{repo}-{number}"
    if ":" in iid and "/" in iid:
        repo_part, number = iid.rsplit(":", 1)
        owner, repo = repo_part.split("/", 1)
        number = number.removeprefix("pr-")
        return f"{owner}__{repo}-{number}"
    return iid


def normalize_id_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [to_leaderboard_id(v) for v in values]


def load_resolved_set(results: dict[str, Any] | None = None) -> set[str]:
    if results is None:
        results = load_results()
    ids = results.get("resolved") or results.get("resolved_ids") or []
    return set(normalize_id_list(ids))


def repo_of(instance_id: str) -> str:
    owner, _, rest = instance_id.partition("__")
    if not rest:
        return instance_id
    repo, _, _ = rest.rpartition("-")
    return f"{owner}/{repo}"


def split_instance_id(instance_id: str) -> tuple[str, str, str]:
    owner, _, rest = instance_id.partition("__")
    if not rest:
        raise ValueError(f"not a leaderboard instance id: {instance_id}")
    repo, _, number = rest.rpartition("-")
    if not repo or not number:
        raise ValueError(f"cannot split instance id: {instance_id}")
    return owner, repo, number


def log_dir_for_instance(instance_id: str) -> Path:
    owner, repo, number = split_instance_id(instance_id)
    return LOGS_DIR / owner / repo / "evals" / f"pr-{number}"


def load_all_preds() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ALL_PREDS_JSONL.exists():
        return out
    with ALL_PREDS_JSONL.open() as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            iid = to_leaderboard_id(row.get("instance_id", ""))
            out[iid] = row.get("model_patch") or ""
    return out


@dataclass(frozen=True)
class WilsonCI:
    lo: float
    hi: float
    p: float
    n: int


def wilson_ci(k: int, n: int, z: float = 1.959964) -> WilsonCI:
    if n == 0:
        return WilsonCI(0.0, 0.0, 0.0, 0)
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return WilsonCI(max(0.0, centre - half), min(1.0, centre + half), p, n)


def mcnemar_exact_p(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = 0.0
    for i in range(0, k + 1):
        p += math.comb(n, i) * (0.5**n)
    return min(1.0, 2.0 * p)


_DIFF_FILE_RE = re.compile(r"^diff --git a/(?P<a>.+) b/(?P<b>.+)$")
_HUNK_RE = re.compile(r"^@@ ")


@dataclass
class PatchStats:
    files: tuple[str, ...] = ()
    hunks: int = 0
    added: int = 0
    removed: int = 0
    is_empty: bool = True

    @property
    def churn(self) -> int:
        return self.added + self.removed

    @property
    def net(self) -> int:
        return self.added - self.removed


def parse_patch(diff_text: str) -> PatchStats:
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


_PHASE_TOKEN_RE = re.compile(r"^WORKFLOW:\s*(\S+)")


def parse_workflow_token(content: str) -> str | None:
    if not content:
        return None
    line = content.lstrip().split("\n", 1)[0].strip()
    m = _PHASE_TOKEN_RE.match(line)
    return m.group(1) if m else None


def bool_series(series: Any) -> Any:
    return series.astype(str).str.lower().isin(("true", "1", "yes"))
