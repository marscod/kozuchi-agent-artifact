#!/usr/bin/env bash
#
# build.sh -- Multi-SWE-Bench Java analysis pipeline for the Kozuchi run.
#
# This is a local port of the SWE-Bench Verified analysis runner.  The
# original pipeline assumes SWE-Bench's 500-instance Python-style log layout
# and several Qwen-vs-SWE-Bench-specific comparison tables.  This version uses
# the Multi-SWE Java leaderboard package layout:
#
#   all_preds.jsonl
#   results/results.json
#   logs/<org>/<repo>/evals/pr-<id>/{fix.patch,fix-patch-run.log,report.json}
#   trajs/<instance_id>.traj.json
#   ../index.json
#
# It produces CSVs and figures under src/csv/ and src/figures/.
#
# Usage:
#   bash build.sh                 # full run
#   bash build.sh figures-only    # re-render figures only
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="${ROOT_DIR}/src"
VENV_DIR="${ROOT_DIR}/.venv"
CSV_DIR="${SRC_DIR}/csv"
FIG_DIR="${SRC_DIR}/figures"
INDEX_JSON="${ROOT_DIR}/../index.json"

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
    for f in all_preds.jsonl results/results.json metadata.yaml; do
        if [[ ! -f "${ROOT_DIR}/${f}" ]]; then
            echo "ERROR: missing ${ROOT_DIR}/${f}" >&2
            exit 1
        fi
    done
    if [[ ! -f "${INDEX_JSON}" ]]; then
        echo "ERROR: missing Multi-SWE Java index at ${INDEX_JSON}" >&2
        exit 1
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

run_extractors() {
    log "extract_metadata    -> instances.csv"
    python "${SRC_DIR}/extract_metadata.py" --output-dir "${CSV_DIR}"

    log "extract_competitors -> competitors_*.csv"
    python "${SRC_DIR}/extract_competitors.py" --output-dir "${CSV_DIR}"
}

run_analysers() {
    log "analyze_results       -> headline / by_repo / by_difficulty / operational"
    python "${SRC_DIR}/analyze_results.py" \
        --instances-csv "${CSV_DIR}/instances.csv" \
        --output-dir "${CSV_DIR}"

    log "analyze_patches       -> patch summary / patch buckets"
    python "${SRC_DIR}/analyze_patches.py" \
        --instances-csv "${CSV_DIR}/instances.csv" \
        --output-dir "${CSV_DIR}"

    log "analyze_trajectories  -> trajectory / effort / phase tables"
    python "${SRC_DIR}/analyze_trajectories.py" \
        --instances-csv "${CSV_DIR}/instances.csv" \
        --output-dir "${CSV_DIR}"

    log "analyze_failures      -> Multi-SWE report failure modes"
    python "${SRC_DIR}/analyze_failures.py" \
        --instances-csv "${CSV_DIR}/instances.csv" \
        --output-dir "${CSV_DIR}"

    log "analyze_competitors   -> leaderboard / peer comparisons"
    python "${SRC_DIR}/analyze_competitors.py" \
        --summary-csv "${CSV_DIR}/competitors_summary.csv" \
        --resolved-csv "${CSV_DIR}/competitors_resolved.csv" \
        --output-dir "${CSV_DIR}"
}

run_figures() {
    log "make_figures          -> overview and diagnostic PNGs"
    python "${SRC_DIR}/make_figures.py" --csv-dir "${CSV_DIR}" --fig-dir "${FIG_DIR}"
}

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

    log "done. artefacts in:"
    echo "  CSVs:    ${CSV_DIR}"
    echo "  Figures: ${FIG_DIR}"
    echo "  Report:  ${SRC_DIR}/analysis.md"
}

main "$@"
