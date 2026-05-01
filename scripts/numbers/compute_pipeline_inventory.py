"""Inventory of CI stages, cluster tags, and reuse-mode variables.

Reads ``.gitlab-ci.yml`` and ``scripts/module_load.sh`` to produce a
machine-readable summary of the multi-cluster pipeline that the
manuscript discusses.
"""

from __future__ import annotations

import json
import re

from _paths import GITLAB_CI, MODULE_LOAD, STATS_DIR


def main() -> None:
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    ci_text = GITLAB_CI.read_text()

    m_stages = re.search(r"^stages:\s*\n((?:\s+-\s+\w+\s*\n)+)", ci_text, re.MULTILINE)
    stages: list[str] = []
    if m_stages:
        for ln in m_stages.group(1).splitlines():
            ms = re.match(r"\s+-\s+(\w+)", ln)
            if ms:
                stages.append(ms.group(1))

    # The CI uses block-style tag lists, e.g.
    #     tags:
    #       - kagura
    cluster_tags: list[str] = []
    seen_tags: set[str] = set()
    lines = ci_text.splitlines()
    for i, ln in enumerate(lines):
        if re.match(r"^\s+tags:\s*$", ln):
            for j in range(i + 1, min(i + 6, len(lines))):
                m = re.match(r"^\s+-\s+\[?(\w+)\]?\s*$", lines[j])
                if not m:
                    break
                t = m.group(1)
                if t not in seen_tags:
                    seen_tags.add(t)
                    cluster_tags.append(t)
        m_inline = re.match(r"^\s+tags:\s*\[\s*(\w+)\s*\]\s*$", ln)
        if m_inline and m_inline.group(1) not in seen_tags:
            seen_tags.add(m_inline.group(1))
            cluster_tags.append(m_inline.group(1))
    cluster_tags = sorted(cluster_tags)

    reuse_vars = sorted(
        set(
            re.findall(
                r"\b(PIPELINE_[A-Z0-9_]+_DIR|PHASE_SFT_ADAPTER_DIRS_FILE)\b",
                ci_text,
            )
        )
    )

    env_block = MODULE_LOAD.read_text() if MODULE_LOAD.exists() else ""
    env_names = sorted(set(re.findall(r'ENV_NAME"\s*==\s*"(\w+)"', env_block)))
    if not env_names:
        env_names = sorted(
            set(re.findall(r"\b(kagura|stratus|ashitaka|abci|azalea)\b", env_block))
        )

    out = {
        "stages": stages,
        "n_stages": len(stages),
        "cluster_tags": cluster_tags,
        "reuse_vars": reuse_vars,
        "env_names": env_names,
    }
    (STATS_DIR / "pipeline_inventory.json").write_text(json.dumps(out, indent=2))

    tex = [
        "% Auto-generated: GitLab CI stage list (.gitlab-ci.yml).",
        r"\begin{tabular}{ll}",
        r"\toprule",
        r"Stage & Notes \\",
        r"\midrule",
    ]
    notes = {
        "prepare": "Prepare venv / pin pip modules",
        "test": "Run repo-level pytest on stratus",
        "bench": "Inference seed runs (multi-cluster)",
        "synth": "Build SFT data from prior trajectories",
        "sft": "Supervised fine-tuning",
        "rl": "Reinforcement learning",
        "bench_post": "Re-bench with SFT/RL adapters",
        "tts": "Test-time selection over multiple runs",
        "report": "Aggregate report job",
    }
    for s in stages:
        escaped = s.replace("_", r"\_")
        tex.append(f"\\code{{{escaped}}} & {notes.get(s, '--')} \\\\")
    tex.append(r"\bottomrule")
    tex.append(r"\end{tabular}")
    (STATS_DIR / "pipeline_inventory.tex").write_text("\n".join(tex) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
