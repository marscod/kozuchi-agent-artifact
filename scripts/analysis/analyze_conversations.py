"""Conversation-level deep analysis of the 495 Kozuchi trajectories.

Sections 1-11 of ``analysis.md`` treat each trajectory as a
*coarse* object: a count of phases, messages, api-calls, and a
final patch. They cannot answer questions about the observable
textual and tool-use structure of the agent's conversation: how it
apportions transcript text vs. tool calls, what shell commands it
runs, what proportion of those calls succeed, where errors and
rework cluster, and how the eight phases hand off to one another.
This module is that conversation-level analysis.

We perform a single streaming pass over every
``trajs/<instance>.traj.json`` file (mean 5.7 MB, 495 files
totalling ~2.7 GB) and accumulate eleven feature families:

  F1  per-message length distributions split by ``role`` and
      ``phase`` (assistant / user / system).
  F2  for every assistant message we split out the
      ``THOUGHT:`` block from the ``FINAL_ANSWER:`` block to
      decompose emitted text volume vs. tool effort. We treat this
      block as observable trajectory text, not as faithful reasoning.
  F3  every ``<tool: bash> ... </tool>`` block is captured and
      its first command verb (``cd`` / ``cat`` / ``python`` /
      ``grep`` / ``sed`` / ``pytest`` / ``pip`` / ...) recorded.
      We also categorise verbs into 7 functional buckets.
  F4  ``<returncode>(-?\\d+)</returncode>`` and ``<output>...
      </output>`` blocks in user (tool-output) messages give
      per-instance shell success / failure counts and output
      sizes.
  F5  user-content tracebacks: occurrences of common Python
      error markers (``Traceback``, ``AssertionError``,
      ``ImportError``, ``AttributeError``, ``NameError``,
      ``TypeError``, ``ValueError``, ``KeyError``,
      ``SyntaxError``, ``ModuleNotFoundError``, ``IndentationError``,
      ``RuntimeError``, ``FileNotFoundError``).
  F6  ``WORKFLOW`` token sequences: counts of ``Wn`` step tokens,
      ``COMPLETE``, ``GIVEUP``, ``HANDOVER`` per phase.
  F7  consecutive phase transitions: an 8x8 conditional
      probability matrix ``P(phase_{t+1} | phase_t)`` (from
      assistant-message-level changes) that exposes the dominant
      flow paths through the scaffold.
  F8  reflection / introspection markers in assistant content:
      counts of phrases like ``I expect``, ``I will check``,
      ``let me try``, ``unsure``, ``not sure``, ``alternatively``.
  F9  per-phase output volume from ``/_share/`` handover memos:
      cat-heredoc counts and approximate memo size are recovered
      from the bash-command stream.
  F10 turn-level *cadence*: time gap between consecutive
      assistant messages (a proxy for per-call inference latency).
  F11 *interesting* trajectories: top-N anomalous instances
      ranked by various dimensions (longest, highest-error,
      most-rework, smallest, etc.) — designed to surface case
      studies for the discussion section.

Every numeric output is also re-aggregated *by outcome*
(resolved vs. unresolved) and tested with Mann-Whitney U +
Cliff's δ + BH-FDR adjustment so the resulting table can be
quoted directly with effect sizes.

CSVs emitted (under ``src/csv/``):

  conv_per_instance.csv                Wide per-instance feature row.
  conv_role_length_stats.csv           Role x outcome x summary.
  conv_thought_action_stats.csv        Thought / action length per phase.
  conv_phase_transition.csv            8x8 phase transition matrix
                                       (overall, resolved, unresolved).
  conv_bash_verbs.csv                  Top-N bash verb frequencies
                                       (overall + by outcome).
  conv_bash_categories.csv             7 functional buckets.
  conv_returncode_per_instance.csv     Per-instance rc=0 vs rc!=0.
  conv_error_indicators.csv            Per-instance counts of common
                                       Python traceback markers.
  conv_workflow_tokens.csv             Workflow-token frequencies by phase
                                       and outcome.
  conv_reflection_markers.csv          Reflective-phrase counts per
                                       trajectory.
  conv_outcome_tests.csv               MWU + Cliff's δ + BH-FDR for every
                                       conversation feature.
  conv_interesting.csv                 Notable trajectories (longest,
                                       most-error, most-rework, etc.).
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from utils import (
    CSV_DIR,
    PHASES_ORDERED,
    RESULTS_JSON,
    TRAJS_DIR,
    ensure_out_dirs,
    parse_workflow_token,
    repo_of,
)


# ---------------------------------------------------------------------------
# Regex catalogue
# ---------------------------------------------------------------------------


_BASH_RE = re.compile(r"<tool:\s*bash>\s*(.*?)\s*</tool>", re.DOTALL | re.IGNORECASE)
_RETURNCODE_RE = re.compile(r"<returncode>(-?\d+)</returncode>")
_OUTPUT_RE = re.compile(r"<output>(.*?)</output>", re.DOTALL)
_THOUGHT_RE = re.compile(r"^\s*THOUGHT:\s*(.*?)(?=^\s*FINAL_ANSWER:|^\s*WORKFLOW:|\Z)",
                         re.DOTALL | re.MULTILINE)
_FINAL_RE = re.compile(r"^\s*FINAL_ANSWER:\s*(.*)\Z", re.DOTALL | re.MULTILINE)
_HEREDOC_PATH_RE = re.compile(r"cat\s*<<\s*['\"]?EOF['\"]?\s*>\s*([\w./_-]+)", re.IGNORECASE)


# Common Python traceback markers we count occurrences of.
_ERROR_MARKERS = (
    "Traceback",
    "AssertionError",
    "ImportError",
    "ModuleNotFoundError",
    "AttributeError",
    "NameError",
    "TypeError",
    "ValueError",
    "KeyError",
    "SyntaxError",
    "IndentationError",
    "RuntimeError",
    "FileNotFoundError",
)


# Functional bucket assignment for the first command verb.  Verbs not
# in any bucket are tagged ``other``.
_BASH_CATEGORIES: dict[str, str] = {
    # File I/O / inspection.
    "cat": "file_io", "head": "file_io", "tail": "file_io",
    "ls": "file_io", "stat": "file_io", "wc": "file_io",
    "tree": "file_io", "file": "file_io", "cp": "file_io",
    "mv": "file_io", "rm": "file_io", "mkdir": "file_io",
    "touch": "file_io", "ln": "file_io",
    # Editing.
    "sed": "edit", "awk": "edit", "patch": "edit",
    "tee": "edit", "echo": "edit", "printf": "edit",
    # Search.
    "grep": "search", "rg": "search", "find": "search",
    "fgrep": "search", "egrep": "search", "ack": "search",
    # Execution.
    "python": "exec", "python3": "exec", "ipython": "exec",
    "bash": "exec", "sh": "exec", "/bin/bash": "exec",
    "make": "exec", "node": "exec",
    # Testing.
    "pytest": "test", "py.test": "test", "tox": "test",
    "unittest": "test", "nosetests": "test",
    # Version control.
    "git": "vcs", "hg": "vcs",
    # Shell / env.
    "cd": "shell_env", "pwd": "shell_env",
    "env": "shell_env", "export": "shell_env",
    "which": "shell_env", "type": "shell_env",
    "alias": "shell_env", "source": "shell_env",
    # Package mgmt.
    "pip": "pkg", "pip3": "pkg", "uv": "pkg",
    "conda": "pkg", "apt": "pkg", "apt-get": "pkg",
    # Containers / orchestration.
    "docker": "infra", "podman": "infra", "ssh": "infra",
}


# Reflection / introspection bigrams or substrings.
_REFLECT_PATTERNS: dict[str, re.Pattern[str]] = {
    "i_expect": re.compile(r"\bI\s+expect\b", re.IGNORECASE),
    "i_will_check": re.compile(r"\bI\s+will\s+(check|verify|inspect|investigate)\b",
                               re.IGNORECASE),
    "let_me_try": re.compile(r"\blet\s+me\s+(try|see|check|verify|test)\b",
                             re.IGNORECASE),
    "not_sure": re.compile(r"\b(not\s+sure|unsure|uncertain)\b", re.IGNORECASE),
    "alternatively": re.compile(r"\balternative(ly)?\b", re.IGNORECASE),
    "however": re.compile(r"\bhowever\b", re.IGNORECASE),
    "wait": re.compile(r"^\s*Wait[,!.\s]", re.MULTILINE),
    "hmm": re.compile(r"\bhmm[,.\s]", re.IGNORECASE),
    "i_realised": re.compile(r"\bI\s+(realise[d]?|realize[d]?|notic[ed]+)\b",
                             re.IGNORECASE),
    "should_have": re.compile(r"\b(should\s+have|should['’]ve|ought\s+to\s+have)\b",
                              re.IGNORECASE),
    "going_back": re.compile(r"\b(go\s+back|back\s+to|reverting)\b", re.IGNORECASE),
}


# ---------------------------------------------------------------------------
# Per-trajectory streaming extractor
# ---------------------------------------------------------------------------


def _bash_verb(cmd: str) -> str:
    """Return the first command verb of a bash one-liner.

    Ignores ``sudo`` / ``time`` / ``env VAR=...`` prefixes, peels
    parentheses and ``{ ... }`` braces, and falls back to "other"
    for an unparseable command.
    """
    s = cmd.strip()
    # Strip leading parentheses / { used to group commands.
    while s and s[0] in "({":
        s = s[1:].lstrip()
    # Strip a leading command-prefix that does not change the
    # primary verb, e.g. ``sudo``, ``time``, ``nice``, env-vars.
    skip = {"sudo", "time", "nice", "nohup", "exec"}
    while True:
        head = s.split(maxsplit=1)
        if not head:
            return "other"
        first = head[0]
        if first in skip:
            s = head[1] if len(head) > 1 else ""
            continue
        # NAME=VALUE prefixes.
        if "=" in first and not first.startswith("="):
            lhs = first.split("=", 1)[0]
            if lhs.replace("_", "").isalnum():
                s = head[1] if len(head) > 1 else ""
                continue
        break
    head = s.split(maxsplit=1)
    if not head:
        return "other"
    verb = head[0]
    # Trim path: /usr/bin/python -> python.
    if "/" in verb:
        verb = verb.rsplit("/", 1)[1]
    # Strip a trailing semicolon / pipe / redirect that snuck in.
    verb = verb.split(";", 1)[0].split("|", 1)[0].split(">", 1)[0]
    return verb.lower() or "other"


def _split_thought_action(content: str) -> tuple[str, str]:
    """Return (thought_text, action_text) from a single assistant turn.

    Kozuchi assistant turns follow the canonical
    ``WORKFLOW: ...\\nTHOUGHT: ...\\nFINAL_ANSWER: ...`` layout.
    We slice the THOUGHT block (text only, no tool blocks) and the
    FINAL_ANSWER block (which contains the bash tool calls).
    """
    th_m = _THOUGHT_RE.search(content)
    fa_m = _FINAL_RE.search(content)
    th = th_m.group(1).strip() if th_m else ""
    fa = fa_m.group(1).strip() if fa_m else ""
    return th, fa


def _process_trajectory(
    path: Path,
    final_resolved: set[str],
) -> dict | None:
    """Stream a single trajectory file and return a feature row.

    Returns ``None`` if the file does not exist or fails to parse.
    """
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:
        return None
    inst_id = data.get("instance_id") or path.stem.replace(".traj", "")
    msgs = data.get("messages") or []

    # ---- Initialise per-instance accumulators ---------------------------
    role_count: Counter[str] = Counter()
    role_chars: dict[str, int] = defaultdict(int)
    role_max_chars: dict[str, int] = defaultdict(int)
    phase_msgs: Counter[str] = Counter()
    phase_thought_chars: dict[str, int] = defaultdict(int)
    phase_action_chars: dict[str, int] = defaultdict(int)
    phase_assistant_count: Counter[str] = Counter()
    phase_user_chars: dict[str, int] = defaultdict(int)
    workflow_tokens: Counter[str] = Counter()
    workflow_w_steps: Counter[str] = Counter()
    bash_cmds: list[str] = []
    bash_verb_counter: Counter[str] = Counter()
    bash_category_counter: Counter[str] = Counter()
    rc_zero = rc_nonzero = rc_unknown = 0
    output_total_chars = 0
    output_max_chars = 0
    error_marker_counts: Counter[str] = Counter()
    reflect_counts: Counter[str] = Counter()
    handover_count = 0
    share_memo_writes = 0
    phase_seq: list[str] = []
    inter_assistant_gaps: list[float] = []
    last_assistant_ts: float | None = None

    # ---- Single-pass scan ----------------------------------------------
    for m in msgs:
        role = m.get("role", "unknown")
        ph = m.get("phase") or "unknown"
        content = m.get("content") or ""
        clen = len(content)
        role_count[role] += 1
        role_chars[role] += clen
        if clen > role_max_chars[role]:
            role_max_chars[role] = clen
        phase_msgs[ph] += 1
        if role == "assistant":
            phase_assistant_count[ph] += 1
            phase_seq.append(ph)
            ts = m.get("timestamp")
            if isinstance(ts, (int, float)):
                if last_assistant_ts is not None:
                    gap = float(ts) - last_assistant_ts
                    if 0 <= gap < 1800:  # cap at 30 min to avoid stragglers
                        inter_assistant_gaps.append(gap)
                last_assistant_ts = float(ts)
            tok = parse_workflow_token(content)
            if tok in {"COMPLETE", "GIVEUP", "HANDOVER"}:
                workflow_tokens[tok] += 1
                if tok == "HANDOVER":
                    handover_count += 1
            elif tok and tok.startswith("W"):
                workflow_w_steps[tok] += 1
            th, ac = _split_thought_action(content)
            phase_thought_chars[ph] += len(th)
            phase_action_chars[ph] += len(ac)
            for cmd in _BASH_RE.findall(content):
                cmd = cmd.strip()
                bash_cmds.append(cmd)
                v = _bash_verb(cmd)
                bash_verb_counter[v] += 1
                bash_category_counter[_BASH_CATEGORIES.get(v, "other")] += 1
                # Heredoc target counts (handover memo writes).
                if _HEREDOC_PATH_RE.search(cmd):
                    share_memo_writes += 1
            for name, pat in _REFLECT_PATTERNS.items():
                reflect_counts[name] += len(pat.findall(content))
        elif role == "user":
            phase_user_chars[ph] += clen
            for rc in _RETURNCODE_RE.findall(content):
                if int(rc) == 0:
                    rc_zero += 1
                else:
                    rc_nonzero += 1
            outs = _OUTPUT_RE.findall(content)
            if not outs and "<returncode>" not in content:
                rc_unknown += 1
            for o in outs:
                output_total_chars += len(o)
                if len(o) > output_max_chars:
                    output_max_chars = len(o)
            for marker in _ERROR_MARKERS:
                if marker in content:
                    error_marker_counts[marker] += content.count(marker)

    # ---- Derived per-instance fields -----------------------------------
    n_assistant = role_count.get("assistant", 0)
    n_user = role_count.get("user", 0)
    n_msgs = sum(role_count.values())
    bash_total = sum(bash_verb_counter.values())
    bash_unique = len(bash_verb_counter)
    rc_total = rc_zero + rc_nonzero
    rc_failure_rate = (rc_nonzero / rc_total) if rc_total else 0.0
    error_total = sum(error_marker_counts.values())
    reflect_total = sum(reflect_counts.values())

    asst_chars_mean = (role_chars["assistant"] / n_assistant) if n_assistant else 0.0
    user_chars_mean = (role_chars["user"] / n_user) if n_user else 0.0
    thought_chars_total = sum(phase_thought_chars.values())
    action_chars_total = sum(phase_action_chars.values())
    thought_action_ratio = (
        thought_chars_total / action_chars_total if action_chars_total else 0.0
    )

    row: dict[str, object] = {
        "instance_id": inst_id,
        "repo": repo_of(inst_id),
        "resolved": int(inst_id in final_resolved),
        "n_messages": n_msgs,
        "n_assistant": n_assistant,
        "n_user": n_user,
        "n_system": role_count.get("system", 0),
        "asst_chars_total": role_chars["assistant"],
        "asst_chars_mean": asst_chars_mean,
        "asst_chars_max": role_max_chars["assistant"],
        "user_chars_total": role_chars["user"],
        "user_chars_mean": user_chars_mean,
        "user_chars_max": role_max_chars["user"],
        "system_chars_total": role_chars.get("system", 0),
        "thought_chars_total": thought_chars_total,
        "action_chars_total": action_chars_total,
        "thought_action_ratio": thought_action_ratio,
        "n_bash_total": bash_total,
        "n_bash_unique_verbs": bash_unique,
        "n_workflow_complete": workflow_tokens.get("COMPLETE", 0),
        "n_workflow_giveup": workflow_tokens.get("GIVEUP", 0),
        "n_workflow_handover": handover_count,
        "n_share_memo_writes": share_memo_writes,
        "rc_zero": rc_zero,
        "rc_nonzero": rc_nonzero,
        "rc_failure_rate": rc_failure_rate,
        "output_total_chars": output_total_chars,
        "output_max_chars": output_max_chars,
        "error_marker_total": error_total,
        "reflect_marker_total": reflect_total,
        "median_inter_assistant_sec": float(np.median(inter_assistant_gaps))
        if inter_assistant_gaps
        else 0.0,
        "p95_inter_assistant_sec": float(np.percentile(inter_assistant_gaps, 95))
        if inter_assistant_gaps
        else 0.0,
    }
    for ph in PHASES_ORDERED:
        row[f"phase_{ph}_thought_chars"] = phase_thought_chars.get(ph, 0)
        row[f"phase_{ph}_action_chars"] = phase_action_chars.get(ph, 0)
        row[f"phase_{ph}_user_chars"] = phase_user_chars.get(ph, 0)
        row[f"phase_{ph}_assistant_msgs"] = phase_assistant_count.get(ph, 0)
    for marker in _ERROR_MARKERS:
        row[f"err_{marker}"] = error_marker_counts.get(marker, 0)
    for name in _REFLECT_PATTERNS:
        row[f"reflect_{name}"] = reflect_counts.get(name, 0)
    for cat in (
        "file_io", "edit", "search", "exec", "test", "vcs", "shell_env", "pkg", "infra",
        "other",
    ):
        row[f"bash_cat_{cat}"] = bash_category_counter.get(cat, 0)

    # Stash auxiliary structures for cross-instance aggregation.
    row["__phase_seq"] = phase_seq
    row["__bash_verbs"] = dict(bash_verb_counter)
    row["__workflow_w_steps"] = dict(workflow_w_steps)
    return row


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


def _phase_transition_matrix(rows: list[dict]) -> pd.DataFrame:
    """Build the 8x8 conditional probability matrix
    ``P(phase_{t+1} | phase_t)`` aggregated across all instances.

    We separately report the matrix on the resolved and unresolved
    subsets to expose any qualitative phase-flow differences between
    successful and failed trajectories.
    """
    counts_all: dict[str, Counter[str]] = defaultdict(Counter)
    counts_res: dict[str, Counter[str]] = defaultdict(Counter)
    counts_unr: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        seq = row.get("__phase_seq", [])
        target = counts_res if row["resolved"] else counts_unr
        for a, b in zip(seq[:-1], seq[1:]):
            if a in PHASES_ORDERED and b in PHASES_ORDERED:
                counts_all[a][b] += 1
                target[a][b] += 1

    out_rows: list[dict] = []
    for split, mat in (("all", counts_all), ("resolved", counts_res),
                       ("unresolved", counts_unr)):
        for a in PHASES_ORDERED:
            tot = sum(mat[a].values())
            for b in PHASES_ORDERED:
                out_rows.append(
                    dict(
                        split=split, from_phase=a, to_phase=b,
                        count=mat[a][b],
                        prob=(mat[a][b] / tot if tot else 0.0),
                        from_total=tot,
                    )
                )
    return pd.DataFrame(out_rows)


def _bash_verb_table(rows: list[dict], top_n: int = 30) -> pd.DataFrame:
    """Top-N bash verbs and their conditional outcome distribution."""
    tot_all: Counter[str] = Counter()
    tot_res: Counter[str] = Counter()
    tot_unr: Counter[str] = Counter()
    n_inst_all = 0
    n_inst_res = 0
    inst_with_verb_all: Counter[str] = Counter()
    inst_with_verb_res: Counter[str] = Counter()
    inst_with_verb_unr: Counter[str] = Counter()
    for row in rows:
        n_inst_all += 1
        if row["resolved"]:
            n_inst_res += 1
        for v, c in row["__bash_verbs"].items():
            tot_all[v] += c
            if row["resolved"]:
                tot_res[v] += c
            else:
                tot_unr[v] += c
            inst_with_verb_all[v] += 1
            if row["resolved"]:
                inst_with_verb_res[v] += 1
            else:
                inst_with_verb_unr[v] += 1
    n_inst_unr = n_inst_all - n_inst_res
    out_rows: list[dict] = []
    for v, c in tot_all.most_common(top_n):
        # Per-call resolution rate among instances using the verb.
        share = c / sum(tot_all.values())
        out_rows.append(
            dict(
                verb=v,
                total=c,
                share_of_calls=share,
                instances_used=inst_with_verb_all[v],
                instance_share=inst_with_verb_all[v] / n_inst_all,
                resolved_calls=tot_res[v],
                unresolved_calls=tot_unr[v],
                resolved_instances=inst_with_verb_res[v],
                unresolved_instances=inst_with_verb_unr[v],
                instance_share_resolved=(
                    inst_with_verb_res[v] / n_inst_res if n_inst_res else 0.0
                ),
                instance_share_unresolved=(
                    inst_with_verb_unr[v] / n_inst_unr if n_inst_unr else 0.0
                ),
            )
        )
    return pd.DataFrame(out_rows)


def _bash_category_table(per_inst: pd.DataFrame) -> pd.DataFrame:
    """Aggregate across the seven functional buckets."""
    cats = ["file_io", "edit", "search", "exec", "test", "vcs",
            "shell_env", "pkg", "infra", "other"]
    rows = []
    total_calls = sum(per_inst[f"bash_cat_{c}"].sum() for c in cats)
    for c in cats:
        col = f"bash_cat_{c}"
        if col not in per_inst.columns:
            continue
        total = int(per_inst[col].sum())
        res_total = int(per_inst.loc[per_inst["resolved"] == 1, col].sum())
        unr_total = int(per_inst.loc[per_inst["resolved"] == 0, col].sum())
        rows.append(
            dict(
                category=c,
                total=total,
                share=total / total_calls if total_calls else 0.0,
                resolved_calls=res_total,
                unresolved_calls=unr_total,
                p50_per_instance=float(per_inst[col].median()),
                mean_per_instance=float(per_inst[col].mean()),
            )
        )
    return pd.DataFrame(rows).sort_values("total", ascending=False).reset_index(drop=True)


def _outcome_summary_tests(per_inst: pd.DataFrame) -> pd.DataFrame:
    """Compare resolved vs. unresolved on every conversation feature.

    Reports the medians, the Mann-Whitney U one-sided p-value (in
    both directions), Cliff's δ, a normal-approximation MWU p-value,
    and a BH-FDR adjusted q-value across the whole feature set.
    """
    feature_cols = [
        c for c in per_inst.columns
        if c.startswith(("phase_", "n_", "asst_", "user_", "thought_",
                         "action_", "rc_", "output_", "err_",
                         "reflect_", "bash_cat_"))
        and per_inst[c].dtype != object
    ]
    res = per_inst[per_inst["resolved"] == 1]
    unr = per_inst[per_inst["resolved"] == 0]
    rows: list[dict] = []
    for col in feature_cols:
        a = res[col].astype(float).values
        b = unr[col].astype(float).values
        if len(a) == 0 or len(b) == 0:
            continue
        # Cliff's delta = (#A>B - #A<B) / (n_a * n_b)
        gt = lt = 0
        for x in a:
            gt += int((b < x).sum())
            lt += int((b > x).sum())
        delta = (gt - lt) / (len(a) * len(b))
        # Mann-Whitney U (normal approximation).
        # U = #(A > B) ties broken by 0.5; equivalent for our use.
        ranks = pd.Series(np.concatenate([a, b])).rank().values
        Ra = ranks[: len(a)].sum()
        U_a = Ra - len(a) * (len(a) + 1) / 2
        n_a, n_b = len(a), len(b)
        mu = n_a * n_b / 2
        sig = math.sqrt(n_a * n_b * (n_a + n_b + 1) / 12)
        z = (U_a - mu) / sig if sig > 0 else 0.0
        # Two-sided p-value via normal CDF.
        p_two = math.erfc(abs(z) / math.sqrt(2))
        rows.append(
            dict(
                feature=col,
                median_resolved=float(np.median(a)),
                median_unresolved=float(np.median(b)),
                mean_resolved=float(np.mean(a)),
                mean_unresolved=float(np.mean(b)),
                cliffs_delta=delta,
                z=z,
                p_value=p_two,
            )
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        m = len(df)
        ranks = df["p_value"].rank(method="average")
        df["bh_fdr_q"] = (df["p_value"] * m / ranks).clip(upper=1.0)
        df = df.sort_values("p_value").reset_index(drop=True)
    return df


def _interesting(per_inst: pd.DataFrame, k: int = 10) -> pd.DataFrame:
    """Highlight notable trajectories along ten ranking dimensions."""
    cols_with_label: list[tuple[str, bool, str]] = [
        ("n_messages", False, "longest_conversation"),
        ("n_messages", True, "shortest_conversation"),
        ("n_bash_total", False, "most_bash_calls"),
        ("rc_failure_rate", False, "highest_rc_failure_rate"),
        ("error_marker_total", False, "most_traceback_signals"),
        ("n_workflow_giveup", False, "most_giveups"),
        ("thought_action_ratio", False, "most_thought_per_action"),
        ("thought_action_ratio", True, "most_action_per_thought"),
        ("output_max_chars", False, "largest_single_tool_output"),
        ("reflect_marker_total", False, "most_reflective"),
    ]
    rows: list[dict] = []
    for col, asc, label in cols_with_label:
        sub = per_inst.sort_values(col, ascending=asc).head(k)
        for _, r in sub.iterrows():
            rows.append(
                dict(
                    rank_dim=label,
                    instance_id=r["instance_id"],
                    repo=r["repo"],
                    resolved=int(r["resolved"]),
                    metric_name=col,
                    metric_value=float(r[col]) if isinstance(r[col], (int, float, np.integer, np.floating)) else r[col],
                    n_messages=int(r["n_messages"]),
                    n_bash_total=int(r["n_bash_total"]),
                    n_workflow_giveup=int(r["n_workflow_giveup"]),
                    error_marker_total=int(r["error_marker_total"]),
                )
            )
    return pd.DataFrame(rows)


def _role_length_stats(rows: list[dict]) -> pd.DataFrame:
    out: list[dict] = []
    for outcome_label, rs in (
        ("all", rows),
        ("resolved", [r for r in rows if r["resolved"]]),
        ("unresolved", [r for r in rows if not r["resolved"]]),
    ):
        if not rs:
            continue
        for col_total, col_count, role in (
            ("asst_chars_total", "n_assistant", "assistant"),
            ("user_chars_total", "n_user", "user"),
            ("system_chars_total", "n_system", "system"),
        ):
            totals = [r[col_total] for r in rs]
            counts = [r[col_count] for r in rs]
            mean_chars = [t / c if c else 0.0 for t, c in zip(totals, counts)]
            out.append(
                dict(
                    outcome=outcome_label,
                    role=role,
                    n_instances=len(rs),
                    total_messages=int(sum(counts)),
                    mean_messages_per_instance=float(np.mean(counts)) if counts else 0.0,
                    p50_chars_per_message=float(np.median(mean_chars)) if mean_chars else 0.0,
                    mean_chars_per_message=float(np.mean(mean_chars)) if mean_chars else 0.0,
                    p95_chars_per_message=float(np.percentile(mean_chars, 95))
                    if mean_chars
                    else 0.0,
                    total_chars=int(sum(totals)),
                )
            )
    return pd.DataFrame(out)


def _thought_action_phase_table(per_inst: pd.DataFrame) -> pd.DataFrame:
    """Per-phase mean thought / action character counts (overall + by outcome)."""
    rows: list[dict] = []
    for outcome_label, df in (
        ("all", per_inst),
        ("resolved", per_inst[per_inst["resolved"] == 1]),
        ("unresolved", per_inst[per_inst["resolved"] == 0]),
    ):
        for ph in PHASES_ORDERED:
            t_col = f"phase_{ph}_thought_chars"
            a_col = f"phase_{ph}_action_chars"
            n_col = f"phase_{ph}_assistant_msgs"
            if t_col not in df.columns:
                continue
            n_msg = df[n_col].replace(0, np.nan)
            mean_th = float((df[t_col] / n_msg).mean(skipna=True)) if not n_msg.isna().all() else 0.0
            mean_ac = float((df[a_col] / n_msg).mean(skipna=True)) if not n_msg.isna().all() else 0.0
            rows.append(
                dict(
                    outcome=outcome_label,
                    phase=ph,
                    n_instances=len(df),
                    p50_msgs=float(df[n_col].median()),
                    mean_thought_chars_per_msg=mean_th,
                    mean_action_chars_per_msg=mean_ac,
                    thought_action_ratio=(mean_th / mean_ac) if mean_ac else 0.0,
                )
            )
    return pd.DataFrame(rows)


def _workflow_token_table(per_inst: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for token in ("complete", "giveup", "handover"):
        col = f"n_workflow_{token}"
        rows.append(
            dict(
                token=token,
                total=int(per_inst[col].sum()),
                p50=float(per_inst[col].median()),
                mean=float(per_inst[col].mean()),
                share_with_any=float((per_inst[col] > 0).mean()),
                resolved_total=int(per_inst.loc[per_inst["resolved"] == 1, col].sum()),
                unresolved_total=int(per_inst.loc[per_inst["resolved"] == 0, col].sum()),
            )
        )
    return pd.DataFrame(rows)


def _reflect_table(per_inst: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name in _REFLECT_PATTERNS:
        col = f"reflect_{name}"
        if col not in per_inst.columns:
            continue
        rows.append(
            dict(
                marker=name,
                total=int(per_inst[col].sum()),
                p50_per_instance=float(per_inst[col].median()),
                mean_per_instance=float(per_inst[col].mean()),
                share_instances_with_any=float((per_inst[col] > 0).mean()),
                resolved_total=int(per_inst.loc[per_inst["resolved"] == 1, col].sum()),
                unresolved_total=int(per_inst.loc[per_inst["resolved"] == 0, col].sum()),
            )
        )
    return pd.DataFrame(rows).sort_values("total", ascending=False).reset_index(drop=True)


def _error_table(per_inst: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for marker in _ERROR_MARKERS:
        col = f"err_{marker}"
        if col not in per_inst.columns:
            continue
        rows.append(
            dict(
                marker=marker,
                total=int(per_inst[col].sum()),
                p50_per_instance=float(per_inst[col].median()),
                mean_per_instance=float(per_inst[col].mean()),
                share_instances_with_any=float((per_inst[col] > 0).mean()),
                resolved_total=int(per_inst.loc[per_inst["resolved"] == 1, col].sum()),
                unresolved_total=int(per_inst.loc[per_inst["resolved"] == 0, col].sum()),
            )
        )
    return pd.DataFrame(rows).sort_values("total", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, default=CSV_DIR)
    args = p.parse_args()
    ensure_out_dirs()
    out = args.output_dir

    if not RESULTS_JSON.exists():
        raise SystemExit(f"results.json not found at {RESULTS_JSON}")
    res = json.loads(RESULTS_JSON.read_text())
    final_resolved = set(res.get("resolved", []))

    files = sorted(TRAJS_DIR.glob("*.traj.json"))
    if not files:
        raise SystemExit(f"no trajectories under {TRAJS_DIR}")

    rows: list[dict] = []
    for i, f in enumerate(files):
        r = _process_trajectory(f, final_resolved)
        if r is not None:
            rows.append(r)
        if (i + 1) % 100 == 0:
            print(f"[analyze_conversations] processed {i + 1}/{len(files)}")

    # Build the wide per-instance frame; drop the helper aux columns so
    # the CSV remains tabular and human-readable.
    aux_cols = {"__phase_seq", "__bash_verbs", "__workflow_w_steps"}
    per_inst = pd.DataFrame(
        [{k: v for k, v in r.items() if k not in aux_cols} for r in rows]
    )
    per_inst.to_csv(out / "conv_per_instance.csv", index=False)

    role_stats = _role_length_stats(rows)
    role_stats.to_csv(out / "conv_role_length_stats.csv", index=False)

    ta_phase = _thought_action_phase_table(per_inst)
    ta_phase.to_csv(out / "conv_thought_action_stats.csv", index=False)

    transitions = _phase_transition_matrix(rows)
    transitions.to_csv(out / "conv_phase_transition.csv", index=False)

    bash_verbs = _bash_verb_table(rows, top_n=30)
    bash_verbs.to_csv(out / "conv_bash_verbs.csv", index=False)

    bash_categories = _bash_category_table(per_inst)
    bash_categories.to_csv(out / "conv_bash_categories.csv", index=False)

    rc_per_inst = per_inst[
        ["instance_id", "repo", "resolved",
         "rc_zero", "rc_nonzero", "rc_failure_rate"]
    ]
    rc_per_inst.to_csv(out / "conv_returncode_per_instance.csv", index=False)

    err_table = _error_table(per_inst)
    err_table.to_csv(out / "conv_error_indicators.csv", index=False)

    wt_table = _workflow_token_table(per_inst)
    wt_table.to_csv(out / "conv_workflow_tokens.csv", index=False)

    refl = _reflect_table(per_inst)
    refl.to_csv(out / "conv_reflection_markers.csv", index=False)

    tests = _outcome_summary_tests(per_inst)
    tests.to_csv(out / "conv_outcome_tests.csv", index=False)

    interesting = _interesting(per_inst, k=10)
    interesting.to_csv(out / "conv_interesting.csv", index=False)

    print(
        "[analyze_conversations] wrote conv_per_instance.csv, "
        "conv_role_length_stats.csv, conv_thought_action_stats.csv, "
        "conv_phase_transition.csv, conv_bash_verbs.csv, "
        "conv_bash_categories.csv, conv_returncode_per_instance.csv, "
        "conv_error_indicators.csv, conv_workflow_tokens.csv, "
        "conv_reflection_markers.csv, conv_outcome_tests.csv, "
        "conv_interesting.csv"
    )
    print(
        f"[analyze_conversations] {len(rows)} trajectories scanned; "
        f"{int(per_inst['resolved'].sum())} resolved, "
        f"{int((1 - per_inst['resolved']).sum())} unresolved."
    )


if __name__ == "__main__":
    main()
