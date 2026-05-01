"""Self-contained paths for the artifact reproduction scripts.

Every input lives under ``paper/artifacts/data/`` and every output under
``paper/artifacts/stats/``. No path escapes the artifact root, so the
folder can be unzipped and run anywhere.

The ``REPO_ROOT`` alias is kept so legacy scripts that import it (e.g.
``compute_workflow_replacement.py``) keep working: it now points at the
artifact ``data/repo_meta`` view of the original repo files.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Artifact root resolution
# ---------------------------------------------------------------------------
# scripts/numbers/_paths.py  ->  scripts/numbers  ->  scripts  ->  artifacts/
HERE = Path(__file__).resolve().parent
ARTIFACT_ROOT = Path(
    os.environ.get("KOZUCHI_ARTIFACT_ROOT", HERE.parents[1])
).resolve()

DATA_DIR = ARTIFACT_ROOT / "data"
STATS_DIR = ARTIFACT_ROOT / "stats"
FIGURES_DIR = ARTIFACT_ROOT / "figures"
PAPER_DIR = ARTIFACT_ROOT / "paper"

# ---------------------------------------------------------------------------
# Repo meta (configs, scripts, README, .gitlab-ci.yml, AGENTS.md, docs/)
# ---------------------------------------------------------------------------
# A few legacy scripts (compute_workflow_replacement, compute_repo_year_breakdown)
# read repo files via REPO_ROOT. We point that alias at our copied subset.
REPO_ROOT = DATA_DIR / "repo_meta"

CONFIG_DIR = DATA_DIR / "configs"
CONFIG_AGENT_SOTA = CONFIG_DIR / "agent_sota.yaml"
TOOLS_DIR = DATA_DIR / "swe_sota_agent" / "tools"

GITLAB_CI = REPO_ROOT / ".gitlab-ci.yml"
README = REPO_ROOT / "README.md"
HOW_TO_DEVELOP = REPO_ROOT / "docs" / "HOW_TO_DEVELOP.md"
MODULE_LOAD = REPO_ROOT / "scripts" / "module_load.sh"

# ---------------------------------------------------------------------------
# SWE-bench Verified submission (Python headline; RQ1-RQ5)
# ---------------------------------------------------------------------------
EXPERIMENTS_VERIFIED = DATA_DIR / "experiments" / "evaluation" / "verified"
SUBMISSION_DIR = EXPERIMENTS_VERIFIED / "20260326_kozuchi-mini-swe-agent_qwen3.5-27b"
SUBMISSION_README = SUBMISSION_DIR / "README.md"
SUBMISSION_METADATA = SUBMISSION_DIR / "metadata.yaml"
SUBMISSION_RESULTS_JSON = SUBMISSION_DIR / "results" / "results.json"

# ---------------------------------------------------------------------------
# Per-instance trajectory bundle (eight Orchestra runs + xcheck)
# ---------------------------------------------------------------------------
TRAJ_BUNDLE = (
    DATA_DIR
    / "trajectories"
    / "q35_verified500_tts8_75p2_submission_bundle_20260326-055715_merged500"
)
TRAJ_BUNDLE_README = TRAJ_BUNDLE / "README.md"
TRAJ_BUNDLE_MANIFEST = TRAJ_BUNDLE / "bundle_manifest.json"
TRAJ_RUNS_DIR = TRAJ_BUNDLE / "runs"
TRAJ_XCHECK_DIR = TRAJ_BUNDLE / "xcheck"
TRAJ_XCHECK_RESULT = (
    TRAJ_XCHECK_DIR
    / "results"
    / "simple_passrate_f03_p07_shortest_patch_raw_75p2.json"
)
TRAJ_XCHECK_SELECTED = (
    TRAJ_XCHECK_DIR
    / "results"
    / "simple_passrate_f03_p07_shortest_patch_raw_selected_labels.json"
)

# ---------------------------------------------------------------------------
# Multi-SWE-bench Java submission (RQ6 / cross-language track)
# ---------------------------------------------------------------------------
JAVA_SUBMISSION_DIR = (
    DATA_DIR / "experiments" / "java" / "kozuchi-mswe-java-20260429"
)
JAVA_XCHECK_PREDS_SCORE = JAVA_SUBMISSION_DIR / "logs" / "_harness" / "xcheck_preds_score.json"

# ---------------------------------------------------------------------------
# Cross-track / comparison helpers
# ---------------------------------------------------------------------------
JAVA_ANALYSIS = DATA_DIR / "paper_comparison" / "analysis.md"
PAPER_COMPARISON_DIR = DATA_DIR / "paper_comparison"
PAPER_JAVA_SRC_DIR = DATA_DIR / "paper_java_src"

# ---------------------------------------------------------------------------
# Output directory
# ---------------------------------------------------------------------------
STATS_DIR.mkdir(parents=True, exist_ok=True)
