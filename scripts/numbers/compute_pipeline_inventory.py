"""Inventory of CI stages, cluster tags, and reuse-mode variables.

Reads the redacted operational-metadata CSVs under
``data/operational_metadata/`` and produces a machine-readable summary
of the multi-cluster pipeline that the manuscript discusses. The raw
``.gitlab-ci.yml`` and ``scripts/module_load.sh`` are not shipped with
the artifact (they contain internal runner tags, SLURM partitions, and
tokens); only the derived counts are released.
"""

from __future__ import annotations

import csv
import json

from _paths import (
    CI_CLUSTER_TAGS_CSV,
    CI_REUSE_VARS_CSV,
    CI_STAGES_CSV,
    CLUSTER_ENV_NAMES_CSV,
    STATS_DIR,
)


def _read_column(path, column: str) -> list[str]:
    with path.open() as f:
        return [row[column] for row in csv.DictReader(f) if row.get(column)]


def _read_stages() -> tuple[list[str], dict[str, str]]:
    stages: list[tuple[int, str, str]] = []
    with CI_STAGES_CSV.open() as f:
        for row in csv.DictReader(f):
            order = int(row["order"])
            stages.append((order, row["stage"], row.get("notes", "")))
    stages.sort(key=lambda r: r[0])
    return [s for _, s, _ in stages], {s: n for _, s, n in stages}


def main() -> None:
    STATS_DIR.mkdir(parents=True, exist_ok=True)

    stages, stage_notes = _read_stages()
    cluster_tags = sorted(set(_read_column(CI_CLUSTER_TAGS_CSV, "tag")))
    reuse_vars = sorted(set(_read_column(CI_REUSE_VARS_CSV, "variable")))
    env_names = sorted(set(_read_column(CLUSTER_ENV_NAMES_CSV, "env_name")))

    out = {
        "stages": stages,
        "n_stages": len(stages),
        "cluster_tags": cluster_tags,
        "reuse_vars": reuse_vars,
        "env_names": env_names,
    }
    (STATS_DIR / "pipeline_inventory.json").write_text(json.dumps(out, indent=2))

    tex = [
        "% Auto-generated: GitLab CI stage list (redacted from upstream .gitlab-ci.yml).",
        r"\begin{tabular}{ll}",
        r"\toprule",
        r"Stage & Notes \\",
        r"\midrule",
    ]
    for s in stages:
        escaped = s.replace("_", r"\_")
        note = stage_notes.get(s, "--") or "--"
        tex.append(f"\\code{{{escaped}}} & {note} \\\\")
    tex.append(r"\bottomrule")
    tex.append(r"\end{tabular}")
    (STATS_DIR / "pipeline_inventory.tex").write_text("\n".join(tex) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
