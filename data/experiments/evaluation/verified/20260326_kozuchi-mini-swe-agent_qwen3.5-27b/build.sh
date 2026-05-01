#!/usr/bin/env bash
#
# build.sh -- run the entire Kozuchi analysis pipeline end-to-end.
#
# What this script does, in order:
#
#   1. Verifies the canonical SWE-bench Verified artifact layout
#      (logs/, trajs/, results/) is present.
#   2. Creates a local Python venv under .venv (using uv if
#      available, otherwise the system python -m venv) and
#      installs the analysis dependencies.
#   3. Runs every analyser in src/ in topological order:
#        extract_metadata.py     -> instances.csv
#        extract_competitors.py  -> competitors_*.csv
#        analyze_results.py      -> headline.csv, by_repo.csv, by_year.csv, operational.csv
#        analyze_patches.py      -> patch_*.csv
#        analyze_trajectories.py -> trajectory_*.csv, effort_*.csv, phase_*.csv
#        analyze_failures.py     -> failure_*.csv, patch_apply_outcomes.csv, test_status_summary.csv
#        analyze_competitors.py    -> leaderboard.csv, peers.csv, mcnemar.csv, per_repo_vs_peers.csv, unique_resolved.csv
#        analyze_qwen_vs_others.py -> qwen_outcome_matrix.csv, qwen_consensus_*.csv, kozuchi_traj_by_qwen_consensus*.csv,
#                                     kozuchi_unique_solves.csv, kozuchi_blindspots.csv, kozuchi_unresolved_strata.csv,
#                                     frontier_solve_share.csv
#        analyze_statistics.py     -> multiple_comparison_corrected.csv, paired_effect_sizes.csv,
#                                     cluster_bootstrap_headline.csv, logistic_regression*.csv,
#                                     nonparametric_trajectory_tests.csv, cmh_stratified_mcnemar.csv,
#                                     consensus_permutation_test.csv, compute_resolution_pareto.csv
#        analyze_tts.py            -> tts_per_leg.csv, tts_pass_at_k_oracle.csv,
#                                     tts_oracle_summary.csv, tts_selector_picks.csv,
#                                     tts_per_repo_oracle_vs_selector.csv, tts_patch_diversity.csv,
#                                     tts_diversity_vs_outcome.csv, tts_leg_jaccard.csv,
#                                     tts_resolve_count_distribution.csv, tts_per_instance_outcomes.csv
#        analyze_conversations.py  -> conv_per_instance.csv, conv_role_length_stats.csv,
#                                     conv_thought_action_stats.csv, conv_phase_transition.csv,
#                                     conv_bash_verbs.csv, conv_bash_categories.csv,
#                                     conv_returncode_per_instance.csv, conv_error_indicators.csv,
#                                     conv_workflow_tokens.csv, conv_reflection_markers.csv,
#                                     conv_outcome_tests.csv, conv_interesting.csv
#        make_figures.py           -> 26 publication-grade PNGs (incl. fig00 4-panel overview,
#                                     fig16-fig20 TTS@8 panels, fig21-fig25 conversation panels)
#
# All artifacts land under src/csv/ and src/figures/ (both tracked
# in git so analysis.md image references resolve on GitHub etc.).
#
# Usage:
#   bash build.sh                 # full run
#   bash build.sh figures-only    # re-render figures only (assumes CSVs exist)
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${ROOT_DIR}/src"
VENV_DIR="${ROOT_DIR}/.venv"
CSV_DIR="${SRC_DIR}/csv"
FIG_DIR="${SRC_DIR}/figures"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log() {
    printf '\033[1;34m[%s]\033[0m %s\n' "$(date +%H:%M:%S)" "$*"
}

ensure_dirs() {
    mkdir -p "${CSV_DIR}" "${FIG_DIR}"
}

verify_inputs() {
    for d in logs trajs results src; do
        if [[ ! -d "${ROOT_DIR}/${d}" ]]; then
            echo "ERROR: missing ${ROOT_DIR}/${d}" >&2
            exit 1
        fi
    done
    # The TTS@8 candidate-level analyser also needs the unzipped
    # trajectory bundle published with the submission.  We warn but
    # do not fail when it is missing -- the rest of the pipeline is
    # unaffected and analyze_tts.py degrades gracefully.
    local bundle
    bundle="$(cd "${ROOT_DIR}/../../.." && pwd)/trajectories/q35_verified500_tts8_75p2_submission_bundle_20260326-055715_merged500"
    if [[ ! -d "${bundle}" ]]; then
        log "warning: TTS@8 trajectory bundle not found at ${bundle}; analyze_tts.py will be skipped."
    fi
}

bootstrap_venv() {
    if [[ -d "${VENV_DIR}" ]]; then
        log "venv already present at ${VENV_DIR}; skipping bootstrap"
        return
    fi
    if command -v uv >/dev/null 2>&1; then
        log "creating venv with uv"
        uv venv "${VENV_DIR}" --python 3.12
        # shellcheck disable=SC1091
        source "${VENV_DIR}/bin/activate"
        uv pip install --quiet pandas numpy matplotlib scipy pyyaml
    else
        log "creating venv with python -m venv"
        python3 -m venv "${VENV_DIR}"
        # shellcheck disable=SC1091
        source "${VENV_DIR}/bin/activate"
        pip install --upgrade --quiet pip
        pip install --quiet pandas numpy matplotlib scipy pyyaml
    fi
}

activate_venv() {
    # shellcheck disable=SC1091
    source "${VENV_DIR}/bin/activate"
}

# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

run_extractors() {
    log "extract_metadata    -> instances.csv"
    python "${SRC_DIR}/extract_metadata.py" --output-dir "${CSV_DIR}"

    log "extract_competitors -> competitors_*.csv"
    python "${SRC_DIR}/extract_competitors.py" --output-dir "${CSV_DIR}"
}

run_analysers() {
    log "analyze_results       -> headline / by_repo / by_year / operational"
    python "${SRC_DIR}/analyze_results.py" \
        --instances-csv "${CSV_DIR}/instances.csv" \
        --output-dir "${CSV_DIR}"

    log "analyze_patches       -> patch_summary / patch_size_buckets / patch_files_buckets / patch_repo_loc"
    python "${SRC_DIR}/analyze_patches.py" \
        --instances-csv "${CSV_DIR}/instances.csv" \
        --output-dir "${CSV_DIR}"

    log "analyze_trajectories  -> trajectory_stats / effort_buckets / phase_distribution / phase_giveup_rate / phase_by_outcome / effort_resolution_corr"
    python "${SRC_DIR}/analyze_trajectories.py" \
        --instances-csv "${CSV_DIR}/instances.csv" \
        --output-dir "${CSV_DIR}"

    log "analyze_failures      -> failure_modes / failure_modes_by_repo / patch_apply_outcomes / test_status_summary / failure_mode_per_instance"
    python "${SRC_DIR}/analyze_failures.py" \
        --instances-csv "${CSV_DIR}/instances.csv" \
        --output-dir "${CSV_DIR}"

    log "analyze_competitors   -> leaderboard / peers / mcnemar / per_repo_vs_peers / unique_resolved"
    python "${SRC_DIR}/analyze_competitors.py" \
        --summary-csv "${CSV_DIR}/competitors_summary.csv" \
        --output-dir "${CSV_DIR}"

    log "analyze_qwen_vs_others -> qwen_outcome_matrix / qwen_consensus_* / kozuchi_traj_by_qwen_consensus* / kozuchi_unique_solves / kozuchi_blindspots / kozuchi_unresolved_strata / frontier_solve_share"
    python "${SRC_DIR}/analyze_qwen_vs_others.py" \
        --instances-csv "${CSV_DIR}/instances.csv" \
        --output-dir "${CSV_DIR}"

    log "analyze_statistics     -> Holm/BH-FDR correction / paired effect sizes / cluster bootstrap / logistic regression / non-parametric tests / CMH / permutation / Pareto"
    python "${SRC_DIR}/analyze_statistics.py" \
        --instances-csv "${CSV_DIR}/instances.csv" \
        --mcnemar-csv "${CSV_DIR}/mcnemar.csv" \
        --matrix-csv "${CSV_DIR}/qwen_outcome_matrix.csv" \
        --output-dir "${CSV_DIR}"

    log "analyze_tts            -> per-leg / pass@k oracle / selector regret / patch diversity / leg agreement"
    python "${SRC_DIR}/analyze_tts.py" \
        --output-dir "${CSV_DIR}"

    log "analyze_conversations  -> per-instance / role-stats / phase transitions / bash verbs / errors / outcome tests / interesting"
    python "${SRC_DIR}/analyze_conversations.py" \
        --output-dir "${CSV_DIR}"
}

run_figures() {
    log "make_figures          -> 16 publication-grade PNGs (incl. fig00 4-panel overview)"
    python "${SRC_DIR}/make_figures.py" --csv-dir "${CSV_DIR}" --fig-dir "${FIG_DIR}"
}

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

main() {
    verify_inputs
    ensure_dirs
    bootstrap_venv
    activate_venv

    case "${1:-all}" in
        figures-only|figures)
            run_figures
            ;;
        all|*)
            run_extractors
            run_analysers
            run_figures
            ;;
    esac

    log "done. artifacts in:"
    echo "  CSVs:    ${CSV_DIR}"
    echo "  Figures: ${FIG_DIR}"
    echo "  Report:  ${SRC_DIR}/analysis.md"
}

main "$@"
