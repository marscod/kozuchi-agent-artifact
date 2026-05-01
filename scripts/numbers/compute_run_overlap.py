"""Per-run completed/resolved-instance overlap across the eight runs.

For each pair of runs we report ``|intersection|``, ``|union|``, and the
symmetric Jaccard similarity over ``completed_ids``. We also compute
the union and intersection of ``resolved_ids``: the union is an oracle
upper bound on what a perfect TTS@8 selector could achieve.
"""

from __future__ import annotations

import json

from _paths import STATS_DIR, TRAJ_RUNS_DIR


def main() -> None:
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    run_dirs = sorted(p for p in TRAJ_RUNS_DIR.iterdir() if p.is_dir())
    completed: dict[str, set[str]] = {}
    resolved: dict[str, set[str]] = {}
    for d in run_dirs:
        report_path = d / "report.json"
        if not report_path.exists():
            continue
        rep = json.loads(report_path.read_text())
        completed[d.name] = set(rep.get("completed_ids", []))
        resolved[d.name] = set(rep.get("resolved_ids", []))

    pairs = []
    names = sorted(completed.keys())
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            inter = completed[a] & completed[b]
            union = completed[a] | completed[b]
            pairs.append(
                {
                    "a": a,
                    "b": b,
                    "intersection": len(inter),
                    "union": len(union),
                    "jaccard": round(len(inter) / len(union), 4) if union else None,
                }
            )

    union_resolved: set[str] = set()
    intersect_resolved: set[str] | None = None
    for n, s in resolved.items():
        union_resolved |= s
        intersect_resolved = s if intersect_resolved is None else (intersect_resolved & s)

    out = {
        "runs": names,
        "per_run_completed": {n: len(s) for n, s in completed.items()},
        "per_run_resolved": {n: len(s) for n, s in resolved.items()},
        "pairwise_completed_overlap": pairs,
        "n_resolved_in_any_run": len(union_resolved),
        "n_resolved_in_every_run": (
            len(intersect_resolved) if intersect_resolved is not None else None
        ),
    }
    (STATS_DIR / "run_overlap.json").write_text(json.dumps(out, indent=2))
    print(
        json.dumps(
            {
                "n_runs": len(names),
                "union_resolved": out["n_resolved_in_any_run"],
                "intersect_resolved": out["n_resolved_in_every_run"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
