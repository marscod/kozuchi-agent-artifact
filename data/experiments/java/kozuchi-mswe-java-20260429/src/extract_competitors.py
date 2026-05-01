"""Extract Java verified leaderboard competitor results into CSVs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import yaml

from utils import (
    CSV_DIR,
    EXPERIMENT_DIR,
    VERIFIED_DIR,
    load_all_ids,
    normalize_id_list,
    wilson_ci,
)


def _read_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _resolved_ids(results: dict[str, Any]) -> set[str]:
    ids = results.get("resolved") or results.get("resolved_ids") or []
    return set(normalize_id_list(ids))


def extract(output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_ids = load_all_ids()
    all_id_set = set(all_ids)

    summary_rows: list[dict[str, Any]] = []
    resolved_rows: list[dict[str, Any]] = []

    for folder in sorted(p for p in VERIFIED_DIR.iterdir() if p.is_dir()):
        results_path = folder / "results" / "results.json"
        if not results_path.exists():
            continue
        results = json.loads(results_path.read_text())
        metadata = _read_metadata(folder / "metadata.yaml")
        resolved = _resolved_ids(results)
        resolved_in_index = resolved & all_id_set
        n = len(all_ids)
        k = len(resolved_in_index)
        ci = wilson_ci(k, n)
        row = {
            "folder": folder.name,
            "name": metadata.get("name") or folder.name,
            "verified": bool(metadata.get("verified", False)),
            "oss": metadata.get("oss"),
            "site": metadata.get("site", ""),
            "is_target": folder.name == EXPERIMENT_DIR.name,
            "total_instances": int(results.get("total_instances", n) or n),
            "submitted_instances": int(
                results.get("submitted_instances", len(results.get("submitted_ids") or []))
                or 0
            ),
            "completed_instances": int(
                results.get("completed_instances", len(results.get("completed_ids") or []))
                or 0
            ),
            "resolved_instances_reported": int(
                results.get("resolved_instances", len(resolved)) or 0
            ),
            "resolved_instances": k,
            "resolved_out_of_index": len(resolved - all_id_set),
            "denominator": n,
            "rate": ci.p,
            "ci_lo": ci.lo,
            "ci_hi": ci.hi,
        }
        summary_rows.append(row)
        for instance_id in all_ids:
            resolved_rows.append(
                {
                    "folder": folder.name,
                    "name": row["name"],
                    "is_target": row["is_target"],
                    "instance_id": instance_id,
                    "resolved": instance_id in resolved_in_index,
                }
            )

    summary_path = output_dir / "competitors_summary.csv"
    resolved_path = output_dir / "competitors_resolved.csv"
    with summary_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)
    with resolved_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(resolved_rows[0].keys()))
        writer.writeheader()
        writer.writerows(resolved_rows)
    return summary_path, resolved_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=CSV_DIR)
    args = parser.parse_args()
    summary, resolved = extract(args.output_dir)
    print(f"[extract_competitors] wrote {summary} and {resolved}")


if __name__ == "__main__":
    main()
