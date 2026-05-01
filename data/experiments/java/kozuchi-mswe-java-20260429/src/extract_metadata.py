"""Materialize the per-instance table for the Multi-SWE Java Kozuchi run."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from utils import (
    CSV_DIR,
    PHASES_ORDERED,
    TRAJS_DIR,
    ensure_out_dirs,
    load_all_ids,
    load_all_preds,
    load_difficulty_map,
    load_resolved_set,
    load_results,
    log_dir_for_instance,
    parse_patch,
    parse_workflow_token,
    repo_of,
)


PATCH_APPLY_RE = re.compile(
    r"(patch failed|error: patch failed|failed to apply|could not apply|rejected hunk)",
    re.IGNORECASE,
)


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(errors="ignore"))


def _stage_counts(report: dict[str, Any], key: str) -> dict[str, int]:
    body = report.get(key) or {}
    return {
        f"{key}_passed": int(body.get("passed_count", 0) or 0),
        f"{key}_failed": int(body.get("failed_count", 0) or 0),
        f"{key}_skipped": int(body.get("skipped_count", 0) or 0),
    }


def _read_report(instance_id: str) -> dict[str, Any]:
    report_path = log_dir_for_instance(instance_id) / "report.json"
    report = _read_json(report_path)
    fields: dict[str, Any] = {
        "has_report": report is not None,
        "report_valid": False,
        "report_error_headline": "",
        "fixed_tests": 0,
        "p2p_tests": 0,
        "f2p_tests": 0,
        "s2p_tests": 0,
        "n2p_tests": 0,
    }
    for key in ("run_result", "test_patch_result", "fix_patch_result"):
        fields.update({f"{key}_passed": 0, f"{key}_failed": 0, f"{key}_skipped": 0})
    if report is None:
        return fields

    fields["report_valid"] = bool(report.get("valid"))
    error_msg = report.get("error_msg") or ""
    fields["report_error_headline"] = error_msg.splitlines()[0] if error_msg else ""
    for bucket in ("fixed_tests", "p2p_tests", "f2p_tests", "s2p_tests", "n2p_tests"):
        fields[bucket] = len(report.get(bucket) or {})
    for key in ("run_result", "test_patch_result", "fix_patch_result"):
        fields.update(_stage_counts(report, key))
    return fields


def _read_patch_apply(instance_id: str) -> dict[str, Any]:
    run_log = log_dir_for_instance(instance_id) / "fix-patch-run.log"
    if not run_log.exists():
        return {
            "has_fix_patch_run_log": False,
            "patch_apply_failed": False,
            "patch_apply_error_headline": "",
        }
    text = run_log.read_text(errors="ignore")
    failed = PATCH_APPLY_RE.search(text) is not None
    first_line = text.splitlines()[0] if failed and text.splitlines() else ""
    return {
        "has_fix_patch_run_log": True,
        "patch_apply_failed": failed,
        "patch_apply_error_headline": first_line[:500],
    }


def _read_patch(instance_id: str, all_preds: dict[str, str]) -> dict[str, Any]:
    patch_path = log_dir_for_instance(instance_id) / "fix.patch"
    patch_text: str | None = None
    source = "missing"
    if patch_path.exists():
        patch_text = patch_path.read_text(errors="ignore")
        source = "logs/fix.patch"
    elif instance_id in all_preds:
        patch_text = all_preds[instance_id]
        source = "all_preds.jsonl"

    if patch_text is None:
        return {
            "has_patch_diff": False,
            "patch_source": source,
            "patch_files": 0,
            "patch_hunks": 0,
            "patch_added": 0,
            "patch_removed": 0,
            "patch_churn": 0,
            "patch_net": 0,
            "patch_is_empty": True,
        }

    stats = parse_patch(patch_text)
    return {
        "has_patch_diff": True,
        "patch_source": source,
        "patch_files": len(stats.files),
        "patch_hunks": stats.hunks,
        "patch_added": stats.added,
        "patch_removed": stats.removed,
        "patch_churn": stats.churn,
        "patch_net": stats.net,
        "patch_is_empty": stats.is_empty,
    }


def _usage_from_message(message: dict[str, Any]) -> tuple[int, int]:
    extra = message.get("extra") or {}
    if not isinstance(extra, dict):
        return 0, 0
    response = extra.get("response") or {}
    if not isinstance(response, dict):
        return 0, 0
    usage = response.get("usage") or {}
    if not isinstance(usage, dict):
        return 0, 0
    return (
        int(usage.get("prompt_tokens", 0) or 0),
        int(usage.get("completion_tokens", 0) or 0),
    )


def _read_traj(instance_id: str) -> dict[str, Any]:
    path = TRAJS_DIR / f"{instance_id}.traj.json"
    out: dict[str, Any] = {
        "has_traj_file": path.exists(),
        "has_traj": False,
        "traj_is_stub": False,
        "exit_status": None,
        "submission_present": False,
        "n_messages": 0,
        "n_assistant": 0,
        "n_user": 0,
        "n_system": 0,
        "n_bash_calls": 0,
        "api_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "runtime_sec": 0.0,
        "mini_version": None,
    }
    for phase in PHASES_ORDERED:
        out[f"phase_{phase}_msgs"] = 0
        out[f"phase_{phase}_steps"] = 0
        out[f"phase_{phase}_complete"] = 0
        out[f"phase_{phase}_giveup"] = 0
        out[f"phase_{phase}_visited"] = 0
    out["phase_unknown_msgs"] = 0

    if not path.exists():
        return out

    data = json.loads(path.read_text(errors="ignore"))
    info = data.get("info") or {}
    messages = data.get("messages") or []
    out["traj_is_stub"] = not bool(messages)
    out["has_traj"] = bool(messages)
    out["exit_status"] = info.get("exit_status") or data.get("agent_exit_status")
    submission = info.get("submission") or data.get("model_patch")
    out["submission_present"] = bool(submission) and submission != "null"
    out["mini_version"] = info.get("mini_version")
    model_stats = info.get("model_stats") or {}
    out["api_calls"] = int(model_stats.get("api_calls", 0) or 0)
    out["n_messages"] = len(messages)
    if not messages:
        return out

    timestamps: list[float] = []
    role_counter: Counter[str] = Counter()
    phase_msgs: Counter[str] = Counter()
    phase_complete: Counter[str] = Counter()
    phase_giveup: Counter[str] = Counter()
    phase_step_set: dict[str, set[str]] = {phase: set() for phase in PHASES_ORDERED}
    prompt_tokens = 0
    completion_tokens = 0
    bash_calls = 0

    for message in messages:
        ts = message.get("timestamp")
        if isinstance(ts, (int, float)):
            timestamps.append(float(ts))
        role = message.get("role", "unknown")
        role_counter[role] += 1
        phase = message.get("phase") or "unknown"
        phase_msgs[phase] += 1

        p_tok, c_tok = _usage_from_message(message)
        prompt_tokens += p_tok
        completion_tokens += c_tok

        if role == "assistant":
            content = message.get("content") or ""
            if "<tool: bash>" in content:
                bash_calls += 1
            token = parse_workflow_token(content)
            if token == "COMPLETE":
                phase_complete[phase] += 1
            elif token == "GIVEUP":
                phase_giveup[phase] += 1
            elif token and token.startswith("W") and phase in phase_step_set:
                phase_step_set[phase].add(token)

    out["n_assistant"] = role_counter.get("assistant", 0)
    out["n_user"] = role_counter.get("user", 0)
    out["n_system"] = role_counter.get("system", 0)
    out["n_bash_calls"] = bash_calls
    out["prompt_tokens"] = prompt_tokens
    out["completion_tokens"] = completion_tokens
    out["total_tokens"] = prompt_tokens + completion_tokens
    if timestamps:
        out["runtime_sec"] = max(timestamps) - min(timestamps)

    for phase in PHASES_ORDERED:
        out[f"phase_{phase}_msgs"] = int(phase_msgs.get(phase, 0))
        out[f"phase_{phase}_complete"] = int(phase_complete.get(phase, 0))
        out[f"phase_{phase}_giveup"] = int(phase_giveup.get(phase, 0))
        out[f"phase_{phase}_steps"] = len(phase_step_set[phase])
        out[f"phase_{phase}_visited"] = int(phase_msgs.get(phase, 0) > 0)
    out["phase_unknown_msgs"] = int(phase_msgs.get("unknown", 0))
    return out


def build_instance_table(output_dir: Path) -> Path:
    ensure_out_dirs()
    output_dir.mkdir(parents=True, exist_ok=True)

    results = load_results()
    resolved = load_resolved_set(results)
    submitted = set(results.get("submitted_ids") or [])
    completed = set(results.get("completed_ids") or [])
    incomplete = set(results.get("incomplete_ids") or [])
    empty_patch = set(results.get("empty_patch_ids") or [])
    error_ids = set(results.get("error_ids") or [])
    difficulty = load_difficulty_map()
    all_preds = load_all_preds()

    rows: list[dict[str, Any]] = []
    for instance_id in load_all_ids():
        rec: dict[str, Any] = {
            "instance_id": instance_id,
            "repo": repo_of(instance_id),
            "difficulty": difficulty.get(instance_id, "unknown"),
            "resolved": instance_id in resolved,
            "in_results_submitted": instance_id in submitted,
            "in_results_completed": instance_id in completed,
            "in_results_incomplete": instance_id in incomplete,
            "in_results_empty_patch": instance_id in empty_patch,
            "in_results_error": instance_id in error_ids,
        }
        rec.update(_read_report(instance_id))
        rec.update(_read_patch_apply(instance_id))
        rec.update(_read_patch(instance_id, all_preds))
        rec.update(_read_traj(instance_id))
        rec["patch_successfully_applied"] = (
            rec["has_fix_patch_run_log"] and not rec["patch_apply_failed"]
        )
        rec["artefact_missing"] = (
            not rec["has_report"] or not rec["has_traj_file"] or not rec["has_patch_diff"]
        )
        rec["all_phases_visited"] = bool(rec["has_traj"]) and all(
            rec[f"phase_{phase}_visited"] for phase in PHASES_ORDERED
        )
        rows.append(rec)

    out_path = output_dir / "instances.csv"
    fieldnames = list(rows[0].keys())
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=CSV_DIR)
    args = parser.parse_args()
    out = build_instance_table(args.output_dir)
    print(f"[extract_metadata] wrote {out}")


if __name__ == "__main__":
    main()
