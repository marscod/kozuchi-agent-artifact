"""Selector/candidate-generation ablation from existing TTS@8 artifacts.

This script does not rerun inference or SWE-bench grading. It combines:

* per-run ``report.json`` files for K=1 and oracle outcomes;
* the cross-agent selector summary for the published cross-agent selector;
* per-instance cross-agent selection tables for artifact-derived selector variants.

The artifact-derived variants estimate whether a chosen deduplicated patch
would resolve an instance from the per-run reports of the run(s) that produced
that patch. The five instances without cross-agent selection tables remain
unresolved under the canonical N=500 denominator.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
from pathlib import Path
from typing import Literal

from _paths import STATS_DIR, TRAJ_RUNS_DIR, TRAJ_XCHECK_DIR, TRAJ_XCHECK_RESULT


N_EXPECTED = 500
RUN_RE = re.compile(r"/(r\d{2}_s\d{4})(?:/|$)")
Mode = Literal["self", "all", "fail_to_pass", "pass_to_pass"]


def load_run_data() -> tuple[list[str], dict[int, set[str]], dict[int, dict[str, int]]]:
    run_dirs = sorted(p for p in TRAJ_RUNS_DIR.iterdir() if p.is_dir())
    labels = [p.name for p in run_dirs]
    resolved: dict[int, set[str]] = {}
    patch_lengths: dict[int, dict[str, int]] = {}
    for idx, run_dir in enumerate(run_dirs):
        report = json.loads((run_dir / "report.json").read_text())
        resolved[idx] = set(report.get("resolved_ids", []))

        preds = json.loads((run_dir / "preds.json").read_text())
        patch_lengths[idx] = {
            inst: len(str(entry.get("model_patch", "") or ""))
            for inst, entry in preds.items()
            if isinstance(entry, dict)
        }
    return labels, resolved, patch_lengths


def suite_run_indices(table: dict, labels: list[str]) -> dict[str, int]:
    label_to_idx = {label: idx for idx, label in enumerate(labels)}
    out: dict[str, int] = {}
    for suite in table.get("suites", []):
        match = RUN_RE.search(str(suite.get("archive_path", "")))
        if match and match.group(1) in label_to_idx:
            out[str(suite["suite_key"])] = label_to_idx[match.group(1)]
    return out


def candidate_patch(table: dict, candidate_idx: int) -> dict | None:
    for patch in table.get("patches", []):
        if candidate_idx in {int(i) for i in patch.get("candidate_indices", [])}:
            return patch
    return None


def candidate_score(table: dict, candidate_idx: int, suite_to_idx: dict[str, int], mode: Mode) -> float:
    patch = candidate_patch(table, candidate_idx)
    if not patch or patch.get("apply_status") != "ok":
        return -1.0
    outcomes = patch.get("suite_outcomes", {})
    vals: list[float] = []
    for suite_key, outcome in outcomes.items():
        if mode == "self" and suite_to_idx.get(suite_key) != candidate_idx:
            continue
        if mode in {"self", "all", "fail_to_pass"}:
            if "fail_to_pass" in outcome:
                vals.append(0.3 * float(bool(outcome["fail_to_pass"])))
        if mode in {"self", "all", "pass_to_pass"}:
            if "pass_to_pass" in outcome:
                vals.append(0.7 * float(bool(outcome["pass_to_pass"])))
    return sum(vals) / len(vals) if vals else -1.0


def select_candidate(
    table: dict, labels: list[str], patch_lengths: dict[int, dict[str, int]], mode: Mode
) -> int | None:
    suite_to_idx = suite_run_indices(table, labels)
    instance_id = str(table.get("instance_id", ""))
    candidates = [
        idx
        for idx in range(len(labels))
        if candidate_patch(table, idx) is not None
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda idx: (
            candidate_score(table, idx, suite_to_idx, mode),
            -patch_lengths.get(idx, {}).get(instance_id, 10**12),
            -idx,
        ),
    )


def candidate_resolves(instance_id: str, candidate_idx: int | None, resolved: dict[int, set[str]]) -> bool:
    if candidate_idx is None:
        return False
    return instance_id in resolved.get(candidate_idx, set())


def evaluate_variant(
    mode: Mode,
    labels: list[str],
    resolved: dict[int, set[str]],
    patch_lengths: dict[int, dict[str, int]],
) -> dict[str, object]:
    table_dir = TRAJ_XCHECK_DIR / "instance_test_tables"
    resolved_count = 0
    selected_count = 0
    for path in sorted(table_dir.glob("*.json")):
        table = json.loads(path.read_text())
        instance_id = str(table.get("instance_id", path.stem))
        candidate_idx = select_candidate(table, labels, patch_lengths, mode)
        if candidate_idx is not None:
            selected_count += 1
        if candidate_resolves(instance_id, candidate_idx, resolved):
            resolved_count += 1
    return {
        "resolved_count": resolved_count,
        "selected_count": selected_count,
        "score_over_expected": resolved_count / N_EXPECTED,
    }


def table_fragment(rows: list[dict[str, object]]) -> str:
    lines = [
        "% Auto-generated by paper/final/sources/paper-src-test-prompt/compute_selector_ablation.py",
        r"\begin{tabular}{@{}p{0.34\columnwidth}rrp{0.27\columnwidth}@{}}",
        r"\toprule",
        r"Variant & Resolved & Rate & Note \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(
            f"{row['variant_tex']} & {row['resolved_tex']} & {row['rate_tex']} & {row['note_tex']} \\\\"
        )
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    return "\n".join(lines) + "\n"


def main() -> None:
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    labels, resolved, patch_lengths = load_run_data()
    per_run_counts = [len(resolved[idx]) for idx in range(len(labels))]
    xcheck = json.loads(TRAJ_XCHECK_RESULT.read_text())
    order = xcheck["order_baseline"]
    variants = {
        "self_tests_only": evaluate_variant("self", labels, resolved, patch_lengths),
        "cross_agent_bug_tests_only": evaluate_variant(
            "fail_to_pass", labels, resolved, patch_lengths
        ),
        "cross_agent_regression_tests_only": evaluate_variant(
            "pass_to_pass", labels, resolved, patch_lengths
        ),
        "cross_agent_all_tests_estimate": evaluate_variant(
            "all", labels, resolved, patch_lengths
        ),
    }

    oracle = len(set().union(*resolved.values()))
    summary = {
        "expected_count": N_EXPECTED,
        "n_runs": len(labels),
        "per_run_mean_resolved": statistics.mean(per_run_counts),
        "per_run_best_resolved": max(per_run_counts),
        "per_run_worst_resolved": min(per_run_counts),
        "order_baseline_resolved": order["resolved_count"],
        "cross_agent_selector_resolved_internal": xcheck["resolved_count"],
        "cross_agent_selector_resolved_official": 374,
        "oracle_tts8_resolved": oracle,
        "artifact_estimate_note": (
            "Variants derived from cross-agent selection tables use per-run "
            "report outcomes for the chosen candidate run; missing selection "
            "tables count as unresolved."
        ),
        "variants": variants,
    }
    (STATS_DIR / "selector_ablation.json").write_text(json.dumps(summary, indent=2))

    csv_rows = [
        ("k1_mean_no_selector", summary["per_run_mean_resolved"], "per-run mean"),
        ("k1_best_no_selector", summary["per_run_best_resolved"], "best single run"),
        ("k8_order_baseline", summary["order_baseline_resolved"], "existing selector summary"),
        ("k8_self_tests_only", variants["self_tests_only"]["resolved_count"], "artifact estimate"),
        (
            "k8_cross_agent_bug_tests_only",
            variants["cross_agent_bug_tests_only"]["resolved_count"],
            "artifact estimate",
        ),
        (
            "k8_cross_agent_regression_tests_only",
            variants["cross_agent_regression_tests_only"]["resolved_count"],
            "artifact estimate",
        ),
        (
            "k8_cross_agent_all_tests_estimate",
            variants["cross_agent_all_tests_estimate"]["resolved_count"],
            "artifact estimate",
        ),
        (
            "k8_cross_agent_selector",
            summary["cross_agent_selector_resolved_internal"],
            "published internal Docker",
        ),
        ("k8_oracle", summary["oracle_tts8_resolved"], "upper bound"),
    ]
    with (STATS_DIR / "selector_ablation.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["variant", "resolved", "rate", "note"])
        for name, count, note in csv_rows:
            writer.writerow([name, count, float(count) / N_EXPECTED, note])

    tex_rows = [
        {
            "variant_tex": r"$K{=}1$, no selector (mean)",
            "resolved_tex": "338.6",
            "rate_tex": "67.7\\%",
            "note_tex": "eight-run mean",
        },
        {
            "variant_tex": r"$K{=}1$, no selector (best)",
            "resolved_tex": str(summary["per_run_best_resolved"]),
            "rate_tex": f"{summary['per_run_best_resolved'] / 5:.1f}\\%",
            "note_tex": "best leg",
        },
        {
            "variant_tex": r"$K{=}8$, order baseline",
            "resolved_tex": str(summary["order_baseline_resolved"]),
            "rate_tex": f"{summary['order_baseline_resolved'] / 5:.1f}\\%",
            "note_tex": "no cross-agent ranking",
        },
        {
            "variant_tex": r"$K{=}8$, self-tests only",
            "resolved_tex": str(variants["self_tests_only"]["resolved_count"]),
            "rate_tex": f"{variants['self_tests_only']['resolved_count'] / 5:.1f}\\%",
            "note_tex": "estimated",
        },
        {
            "variant_tex": r"$K{=}8$, cross-agent selector",
            "resolved_tex": str(summary["cross_agent_selector_resolved_internal"]),
            "rate_tex": f"{summary['cross_agent_selector_resolved_internal'] / 5:.1f}\\%",
            "note_tex": "selected",
        },
        {
            "variant_tex": r"$K{=}8$, oracle",
            "resolved_tex": str(summary["oracle_tts8_resolved"]),
            "rate_tex": f"{summary['oracle_tts8_resolved'] / 5:.1f}\\%",
            "note_tex": "upper bound",
        },
    ]
    (STATS_DIR / "selector_ablation.tex").write_text(table_fragment(tex_rows))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
