"""Artifact-only audit of the cross-agent selector.

The script reads the released TTS@8 trajectory bundle and writes compact
provenance for reviewer-facing claims about selector weights, ties, test
admission, deduplication, hidden-test isolation, and matrix cost. It does
not rerun inference, generated tests, or SWE-bench grading.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from _paths import STATS_DIR, TRAJ_BUNDLE, TRAJ_RUNS_DIR, TRAJ_XCHECK_DIR, TRAJ_XCHECK_RESULT


N_EXPECTED = 500
RUN_RE = re.compile(r"/(r\d{2}_s\d{4})(?:/|$)")
WEIGHT_GRID = [(0.5, 0.5), (0.4, 0.6), (0.3, 0.7), (0.2, 0.8), (0.1, 0.9), (0.7, 0.3), (0.9, 0.1)]


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


def patch_score(patch: dict, w_bug: float, w_regression: float) -> float:
    if patch.get("apply_status") != "ok":
        return -1.0
    vals = [
        w_bug * float(bool(outcome.get("fail_to_pass")))
        + w_regression * float(bool(outcome.get("pass_to_pass")))
        for outcome in patch.get("suite_outcomes", {}).values()
    ]
    return sum(vals) / len(vals) if vals else -1.0


def candidate_score(table: dict, candidate_idx: int, w_bug: float, w_regression: float) -> float:
    patch = candidate_patch(table, candidate_idx)
    return patch_score(patch, w_bug, w_regression) if patch else -1.0


def select_candidate(
    table: dict,
    labels: list[str],
    patch_lengths: dict[int, dict[str, int]],
    w_bug: float,
    w_regression: float,
) -> int | None:
    instance_id = str(table.get("instance_id", ""))
    candidates = [idx for idx in range(len(labels)) if candidate_patch(table, idx) is not None]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda idx: (
            candidate_score(table, idx, w_bug, w_regression),
            -patch_lengths.get(idx, {}).get(instance_id, 10**12),
            -idx,
        ),
    )


def sensitivity(
    tables: list[dict],
    labels: list[str],
    resolved: dict[int, set[str]],
    patch_lengths: dict[int, dict[str, int]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    reference = {
        str(table.get("instance_id", "")): select_candidate(table, labels, patch_lengths, 0.3, 0.7)
        for table in tables
    }
    for w_bug, w_regression in WEIGHT_GRID:
        selected = 0
        resolved_count = 0
        changed_from_reference = 0
        for table in tables:
            instance_id = str(table.get("instance_id", ""))
            idx = select_candidate(table, labels, patch_lengths, w_bug, w_regression)
            if idx is not None:
                selected += 1
            if idx is not None and instance_id in resolved.get(idx, set()):
                resolved_count += 1
            changed_from_reference += int(idx != reference[instance_id])
        rows.append(
            {
                "w_B": w_bug,
                "w_R": w_regression,
                "selected_count": selected,
                "artifact_resolved_count": resolved_count,
                "artifact_rate_over_expected": resolved_count / N_EXPECTED,
                "changed_from_current_weight_choice": changed_from_reference,
            }
        )
    return rows


def tie_audit(tables: list[dict], tie_eps: float, w_bug: float, w_regression: float) -> dict[str, object]:
    tie_size_hist: Counter[int] = Counter()
    tied_instances = 0
    for table in tables:
        scores = [
            patch_score(patch, w_bug, w_regression)
            for patch in table.get("patches", [])
            if patch_score(patch, w_bug, w_regression) >= 0
        ]
        if not scores:
            continue
        best = max(scores)
        tied = [score for score in scores if abs(score - best) <= tie_eps]
        if len(tied) >= 2:
            tied_instances += 1
            tie_size_hist[len(tied)] += 1
    return {
        "tie_definition": f">=2 deduplicated patches within {tie_eps} of the top score",
        "tie_instances_recomputed": tied_instances,
        "tie_size_histogram": dict(sorted(tie_size_hist.items())),
        "tie_breaker_applied_to_instances": tied_instances,
        "tie_breaker_applied_share_covered": tied_instances / len(tables),
        "tie_breaker_applied_share_expected": tied_instances / N_EXPECTED,
    }


def test_archive_audit() -> dict[str, object]:
    inputs_dir = TRAJ_XCHECK_DIR / "inputs"
    per_run_counts: dict[str, int] = {}
    dropped_per_run: dict[str, int] = {}
    missing_f2p = 0
    missing_p2p = 0
    missing_both = 0
    for path in sorted(inputs_dir.glob("r*_s*.share_assets.json")):
        run = path.name.removesuffix(".share_assets.json")
        assets = json.loads(path.read_text())
        per_run_counts[run] = len(assets)
        dropped_per_run[run] = N_EXPECTED - len(assets)
        for meta in assets.values():
            has_f2p = bool(meta.get("has_fail_to_pass"))
            has_p2p = bool(meta.get("has_pass_to_pass"))
            missing_f2p += int(not has_f2p and has_p2p)
            missing_p2p += int(has_f2p and not has_p2p)
            missing_both += int(not has_f2p and not has_p2p)
    return {
        "admission_rule": "suite enters xcheck only if has_fail_to_pass and has_pass_to_pass are both true",
        "per_run_archived_suite_counts": per_run_counts,
        "per_run_dropped_before_xcheck": dropped_per_run,
        "archived_suite_count_range": [min(per_run_counts.values()), max(per_run_counts.values())],
        "missing_fail_to_pass_among_archived": missing_f2p,
        "missing_pass_to_pass_among_archived": missing_p2p,
        "missing_both_among_archived": missing_both,
    }


def matrix_audit(tables: list[dict]) -> dict[str, object]:
    unique_patch_counts = [len(table.get("patches", [])) for table in tables]
    suite_counts = [len(table.get("suites", [])) for table in tables]
    apply_status = Counter(
        str(patch.get("apply_status", "unknown"))
        for table in tables
        for patch in table.get("patches", [])
    )
    cache_status = Counter(
        str(patch.get("cache_status", "unknown"))
        for table in tables
        for patch in table.get("patches", [])
    )
    matrix_executions = sum(
        len(patch.get("suite_outcomes", {}))
        for table in tables
        for patch in table.get("patches", [])
    )
    naive_executions = 8 * 8 * len(tables)
    manifest = json.loads((TRAJ_BUNDLE / "provenance" / "xcheck_manifest.json").read_text())
    return {
        "table_count": len(tables),
        "missing_artifact_count": N_EXPECTED - len(tables),
        "all_table_status_ok": all(table.get("status") == "ok" for table in tables),
        "unique_patch_count_mean": sum(unique_patch_counts) / len(unique_patch_counts),
        "unique_patch_count_histogram": dict(sorted(Counter(unique_patch_counts).items())),
        "suite_count_mean": sum(suite_counts) / len(suite_counts),
        "suite_count_histogram": dict(sorted(Counter(suite_counts).items())),
        "deduplicated_patch_total": sum(unique_patch_counts),
        "apply_status_counts": dict(sorted(apply_status.items())),
        "cache_status_counts": dict(sorted(cache_status.items())),
        "matrix_patch_suite_executions": matrix_executions,
        "naive_8x8_executions_for_covered": naive_executions,
        "dedup_and_filter_savings_share": 1 - matrix_executions / naive_executions,
        "xcheck_shard_job_count": len(manifest.get("shard_job_ids", [])),
        "xcheck_method": manifest.get("xcheck_method"),
        "xcheck_allow_fallback": manifest.get("xcheck_allow_fallback"),
    }


def hidden_boundary() -> dict[str, object]:
    return {
        "selector_inputs": [
            "xcheck/instance_test_tables/*.json:suites",
            "xcheck/instance_test_tables/*.json:patches.apply_status",
            "xcheck/instance_test_tables/*.json:patches.suite_outcomes",
            "runs/r0*_s100*/preds.json:model_patch length for tie-break",
        ],
        "not_selector_inputs": [
            "official SWE-bench cloud result",
            "internal Docker grading result",
            "hidden benchmark test outcomes",
        ],
        "mechanics": "candidate tests are archived in share_assets before xcheck tables are produced; selector output is a selected-label/preds map consumed by downstream evaluation",
    }


def table_fragment(audit: dict[str, object]) -> str:
    matrix = audit["matrix_audit"]
    tie = audit["tie_audit"]
    sensitivity_rows = audit["weight_sensitivity"]
    current = next(row for row in sensitivity_rows if row["w_B"] == 0.3 and row["w_R"] == 0.7)
    return "\n".join(
        [
            "% Auto-generated by paper/final/sources/paper-src-test-prompt/compute_selector_audit.py",
            "% Artifact-only audit: no inference, generated tests, or SWE-bench grading rerun.",
            r"\begin{tabular}{lr}",
            r"\toprule",
            r"Audit quantity & Value \\",
            r"\midrule",
            f"Weight grid best (artifact est.) & {max(row['artifact_resolved_count'] for row in sensitivity_rows)}/500 \\\\",
            f"Current weights (artifact est.) & {current['artifact_resolved_count']}/500 \\\\",
            f"Tie-break applied & {tie['tie_breaker_applied_to_instances']}/{matrix['table_count']} \\\\",
            f"Mean unique patches & {matrix['unique_patch_count_mean']:.2f}/8 \\\\",
            f"Matrix executions & {matrix['matrix_patch_suite_executions']:,} \\\\",
            r"\bottomrule",
            r"\end{tabular}",
        ]
    ) + "\n"


def collect() -> dict[str, object]:
    tables = [
        json.loads(path.read_text())
        for path in sorted((TRAJ_XCHECK_DIR / "instance_test_tables").glob("*.json"))
    ]
    summary = json.loads(TRAJ_XCHECK_RESULT.read_text())
    labels, resolved, patch_lengths = load_run_data()
    audit = {
        "sources": {
            "xcheck_tables": str(TRAJ_XCHECK_DIR / "instance_test_tables"),
            "xcheck_result": str(TRAJ_XCHECK_RESULT),
            "xcheck_inputs": str(TRAJ_XCHECK_DIR / "inputs"),
            "per_run_reports": str(TRAJ_RUNS_DIR / "r0*_s100*/report.json"),
            "per_run_predictions": str(TRAJ_RUNS_DIR / "r0*_s100*/preds.json"),
            "xcheck_manifest": str(TRAJ_BUNDLE / "provenance" / "xcheck_manifest.json"),
        },
        "selector_weights": {
            "w_B": summary.get("f2p_weight"),
            "w_R": summary.get("p2p_weight"),
            "provenance_statement": "Fixed globally before official SWE-bench Verified evaluation; not tuned on hidden-test outcomes or per repository.",
            "artifact_estimate_note": "Weight sensitivity uses archived xcheck tables and per-run report outcomes for the selected candidate; it is not a fresh SWE-bench grade.",
        },
        "weight_sensitivity": sensitivity(tables, labels, resolved, patch_lengths),
        "tie_audit": tie_audit(
            tables,
            float(summary.get("tie_score_eps", 0.001)),
            float(summary.get("f2p_weight", 0.3)),
            float(summary.get("p2p_weight", 0.7)),
        ),
        "test_archive_audit": test_archive_audit(),
        "matrix_audit": matrix_audit(tables),
        "hidden_test_boundary": hidden_boundary(),
    }
    return audit


def main() -> None:
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    audit = collect()
    (STATS_DIR / "selector_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    (STATS_DIR / "selector_audit.tex").write_text(table_fragment(audit))
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
