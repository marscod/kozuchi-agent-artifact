"""Materialise the per-instance metadata table for the Kozuchi run.

The extractor scans:
  * ``logs/<instance>/report.json`` -> resolution + test-status fields,
  * ``logs/<instance>/patch.diff`` -> patch structure (LOC, files, hunks),
  * ``trajs/<instance>.traj.json`` -> exit_status, api_calls, token usage,
    runtime, and per-phase activity (number of turns, completion vs.
    giveup, distinct workflow steps visited).

The output is a single CSV that drives every downstream analysis.
We always iterate over the canonical 500-instance Verified set so
that missing artifacts (the original prompt: "if you see less logs
in compared to 500, means there has been an issue with those tasks,
so dominator always is 500") are explicitly recorded with the
``has_log`` / ``has_traj`` flags rather than being silently
dropped.

We deliberately stream each trajectory file once and discard it
because the directory totals ~2.7 GB; loading them all in memory is
unnecessary.

Run as:

    python -m extract_metadata --output-dir src/csv
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from utils import (
    CSV_DIR,
    LOGS_DIR,
    PHASES_ORDERED,
    RESULTS_JSON,
    TRAJS_DIR,
    ensure_out_dirs,
    load_verified_instance_set,
    parse_patch,
    parse_workflow_token,
    repo_of,
)


def _read_json(path: Path) -> Any | None:
    """Return JSON decoded from ``path`` or ``None`` if missing."""

    if not path.exists():
        return None
    return json.loads(path.read_text())


def _read_report(instance_id: str) -> dict[str, Any]:
    """Extract solver-side fields from ``logs/<instance>/report.json``.

    The report mirrors the SWE-bench harness output and contains four
    test buckets (FAIL_TO_PASS, FAIL_TO_FAIL, PASS_TO_PASS,
    PASS_TO_FAIL).  We expose:
      * ``resolved`` -- final SWE-bench pass/fail label
      * ``patch_*`` -- whether the patch existed/applied
      * counts for each bucket (success/failure)
    """

    rep_path = LOGS_DIR / instance_id / "report.json"
    rep = _read_json(rep_path)
    fields: dict[str, Any] = {
        "has_report": rep is not None,
        "patch_exists": None,
        "patch_is_None": None,
        "patch_successfully_applied": None,
        "resolved_in_report": None,
    }
    for cat in ("FAIL_TO_PASS", "FAIL_TO_FAIL", "PASS_TO_PASS", "PASS_TO_FAIL"):
        fields[f"{cat}_success"] = 0
        fields[f"{cat}_failure"] = 0
    if rep is None:
        return fields
    body = rep.get(instance_id) or next(iter(rep.values()), {})
    fields["patch_exists"] = body.get("patch_exists")
    fields["patch_is_None"] = body.get("patch_is_None")
    fields["patch_successfully_applied"] = body.get("patch_successfully_applied")
    fields["resolved_in_report"] = body.get("resolved")
    ts = body.get("tests_status", {}) or {}
    for cat in ("FAIL_TO_PASS", "FAIL_TO_FAIL", "PASS_TO_PASS", "PASS_TO_FAIL"):
        b = ts.get(cat, {}) or {}
        fields[f"{cat}_success"] = len(b.get("success", []))
        fields[f"{cat}_failure"] = len(b.get("failure", []))
    return fields


def _read_patch(instance_id: str) -> dict[str, Any]:
    """Patch structure metrics extracted from the unified diff."""

    p = LOGS_DIR / instance_id / "patch.diff"
    if not p.exists():
        return dict(
            has_patch_diff=False,
            patch_files=0,
            patch_hunks=0,
            patch_added=0,
            patch_removed=0,
            patch_churn=0,
            patch_is_empty=True,
        )
    stats = parse_patch(p.read_text(errors="ignore"))
    return dict(
        has_patch_diff=True,
        patch_files=len(stats.files),
        patch_hunks=stats.hunks,
        patch_added=stats.added,
        patch_removed=stats.removed,
        patch_churn=stats.churn,
        patch_is_empty=stats.is_empty,
    )


def _read_traj(instance_id: str) -> dict[str, Any]:
    """Per-phase trajectory metrics derived from the full traj.json.

    We deliberately keep this O(messages) and avoid retaining the
    raw payload after extraction; trajectories are up to 38 MB each
    and the total directory is ~2.7 GB.
    """

    p = TRAJS_DIR / f"{instance_id}.traj.json"
    out: dict[str, Any] = dict(
        has_traj=False,
        exit_status=None,
        submission_present=False,
        n_messages=0,
        n_assistant=0,
        n_user=0,
        n_system=0,
        n_bash_calls=0,
        api_calls=0,
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        runtime_sec=0.0,
        mini_version=None,
    )
    for ph in PHASES_ORDERED:
        out[f"phase_{ph}_msgs"] = 0
        out[f"phase_{ph}_steps"] = 0
        out[f"phase_{ph}_complete"] = 0
        out[f"phase_{ph}_giveup"] = 0
        out[f"phase_{ph}_visited"] = 0
    out["phase_unknown_msgs"] = 0
    if not p.exists():
        return out
    out["has_traj"] = True
    data = json.loads(p.read_text())
    info = data.get("info", {}) or {}
    out["exit_status"] = info.get("exit_status")
    sub = info.get("submission")
    out["submission_present"] = bool(sub) and sub != "null"
    ms = info.get("model_stats") or {}
    out["api_calls"] = int(ms.get("api_calls", 0) or 0)
    out["mini_version"] = info.get("mini_version")

    msgs = data.get("messages", []) or []
    out["n_messages"] = len(msgs)
    if not msgs:
        return out

    # Aggregate trajectory-level metrics in a single pass.
    timestamps: list[float] = []
    role_counter: Counter[str] = Counter()
    phase_msgs: Counter[str] = Counter()
    phase_complete: Counter[str] = Counter()
    phase_giveup: Counter[str] = Counter()
    phase_step_set: dict[str, set[str]] = {ph: set() for ph in PHASES_ORDERED}
    prompt_tok = comp_tok = 0
    bash_calls = 0
    for m in msgs:
        ts = m.get("timestamp")
        if isinstance(ts, (int, float)):
            timestamps.append(float(ts))
        role = m.get("role", "unknown")
        role_counter[role] += 1
        ph = m.get("phase", "unknown") or "unknown"
        phase_msgs[ph] += 1

        # Aggregate token usage from per-call responses if present.
        extra = m.get("extra") or {}
        resp = extra.get("response") if isinstance(extra, dict) else None
        if isinstance(resp, dict):
            usage = resp.get("usage") or {}
            prompt_tok += int(usage.get("prompt_tokens", 0) or 0)
            comp_tok += int(usage.get("completion_tokens", 0) or 0)

        if role == "assistant":
            content = m.get("content") or ""
            if "<tool: bash>" in content:
                bash_calls += 1
            tok = parse_workflow_token(content)
            if tok == "COMPLETE":
                phase_complete[ph] += 1
            elif tok == "GIVEUP":
                phase_giveup[ph] += 1
            elif tok and tok.startswith("W") and ph in phase_step_set:
                phase_step_set[ph].add(tok)

    out["n_assistant"] = role_counter.get("assistant", 0)
    out["n_user"] = role_counter.get("user", 0)
    out["n_system"] = role_counter.get("system", 0)
    out["n_bash_calls"] = bash_calls
    out["prompt_tokens"] = prompt_tok
    out["completion_tokens"] = comp_tok
    out["total_tokens"] = prompt_tok + comp_tok
    if timestamps:
        out["runtime_sec"] = max(timestamps) - min(timestamps)
    for ph in PHASES_ORDERED:
        out[f"phase_{ph}_msgs"] = int(phase_msgs.get(ph, 0))
        out[f"phase_{ph}_complete"] = int(phase_complete.get(ph, 0))
        out[f"phase_{ph}_giveup"] = int(phase_giveup.get(ph, 0))
        out[f"phase_{ph}_steps"] = len(phase_step_set[ph])
        out[f"phase_{ph}_visited"] = int(phase_msgs.get(ph, 0) > 0)
    out["phase_unknown_msgs"] = int(phase_msgs.get("unknown", 0))
    return out


def build_instance_table(output_dir: Path) -> Path:
    """Materialise ``instances.csv`` covering all 500 Verified tasks."""

    ensure_out_dirs()
    res = json.loads(RESULTS_JSON.read_text())
    resolved = set(res.get("resolved", []))
    no_gen = set(res.get("no_generation", []))
    no_logs = set(res.get("no_logs", []))

    verified = sorted(load_verified_instance_set())
    rows: list[dict[str, Any]] = []
    for iid in verified:
        rec: dict[str, Any] = dict(
            instance_id=iid,
            repo=repo_of(iid),
            resolved=iid in resolved,
            in_no_generation=iid in no_gen,
            in_no_logs=iid in no_logs,
        )
        rec.update(_read_report(iid))
        rec.update(_read_patch(iid))
        rec.update(_read_traj(iid))
        # Derived flags useful for downstream analyses.
        rec["artifact_missing"] = (not rec["has_traj"]) or (not rec["has_report"])
        rec["all_phases_visited"] = all(
            rec[f"phase_{ph}_visited"] for ph in PHASES_ORDERED
        )
        rows.append(rec)

    out_path = output_dir / "instances.csv"
    fieldnames = list(rows[0].keys())
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--output-dir",
        type=Path,
        default=CSV_DIR,
        help="Directory in which to write the per-instance CSV.",
    )
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = build_instance_table(args.output_dir)
    print(f"[extract_metadata] wrote {out}")


if __name__ == "__main__":
    main()
