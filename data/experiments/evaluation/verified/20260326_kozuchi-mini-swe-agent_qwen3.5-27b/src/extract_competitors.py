"""Build a flat ``competitors.csv`` listing every public submission's
``resolved`` set together with simple bookkeeping metadata.

We rely on the canonical ``results/results.json`` file that every
SWE-bench Verified submission ships with.  The schema differs
slightly from one submission to the next (some carry intermediate
buckets such as ``no_apply``/``test_errored`` while modern ones only
emit ``no_generation``/``no_logs``/``resolved``), but the ``resolved``
key is always present.

For each submission we additionally read ``metadata.yaml`` to
recover the system / model name, organisation, and the
``os_model`` / ``os_system`` flags.  Together these define the slate
of comparator buckets used in :mod:`analyze_competitors`.

Run as:

    python -m extract_competitors --output-dir src/csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import yaml

from utils import CSV_DIR, EVAL_DIR, ensure_out_dirs, load_verified_instance_set


def _load_metadata(path: Path) -> dict[str, Any]:
    """Return the parsed YAML metadata or an empty dict if missing."""

    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


# ---------------------------------------------------------------------------
# Per-submission readers
# ---------------------------------------------------------------------------


def _read_submission(path: Path) -> dict[str, Any] | None:
    """Return a flat record describing a single submission directory."""

    res_path = path / "results" / "results.json"
    meta_path = path / "metadata.yaml"
    if not res_path.exists():
        return None
    res = json.loads(res_path.read_text())
    resolved = list(res.get("resolved") or [])
    no_gen = list(res.get("no_generation") or [])
    no_logs = list(res.get("no_logs") or [])
    meta = _load_metadata(meta_path)
    info: dict[str, Any] = meta.get("info") or {}
    tags: dict[str, Any] = meta.get("tags") or {}
    return dict(
        submission_dir=path.name,
        name=info.get("name") or path.name,
        org=tags.get("org"),
        os_model=tags.get("os_model"),
        os_system=tags.get("os_system"),
        report=info.get("report"),
        n_resolved=len(resolved),
        n_no_generation=len(no_gen),
        n_no_logs=len(no_logs),
        resolved=resolved,
    )


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------


def build_competitor_table(output_dir: Path) -> tuple[Path, Path]:
    """Materialise two CSVs.

    * ``competitors_summary.csv`` -- one row per submission with the
      headline numbers (resolution rate, missing-artifact counts).
    * ``competitors_resolved.csv`` -- long-format table with one row
      per (submission, instance) pair restricted to the submission's
      *resolved* set.  This is the lightweight backbone for the
      pairwise / per-repo competitor comparisons.
    """

    ensure_out_dirs()
    verified = load_verified_instance_set()
    rows: list[dict[str, Any]] = []
    long_rows: list[dict[str, Any]] = []
    for sub_dir in sorted(EVAL_DIR.iterdir()):
        if not sub_dir.is_dir():
            continue
        rec = _read_submission(sub_dir)
        if rec is None:
            continue
        # Restrict to canonical Verified instances; some old
        # submissions accidentally include a stray id.
        rec_resolved = sorted(set(rec["resolved"]) & verified)
        rec_summary = {k: v for k, v in rec.items() if k != "resolved"}
        rec_summary["n_resolved_in_500"] = len(rec_resolved)
        rec_summary["resolution_rate"] = len(rec_resolved) / len(verified)
        rows.append(rec_summary)
        for iid in rec_resolved:
            long_rows.append(
                dict(
                    submission_dir=rec["submission_dir"],
                    instance_id=iid,
                )
            )

    summary_path = output_dir / "competitors_summary.csv"
    with summary_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    long_path = output_dir / "competitors_resolved.csv"
    with long_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["submission_dir", "instance_id"])
        w.writeheader()
        w.writerows(long_rows)
    return summary_path, long_path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, default=CSV_DIR)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    s, l = build_competitor_table(args.output_dir)
    print(f"[extract_competitors] summary={s}")
    print(f"[extract_competitors] resolved-long={l}")


if __name__ == "__main__":
    main()
