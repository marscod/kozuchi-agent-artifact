#!/usr/bin/env bash
# reproduce.sh -- regenerate every paper-cited number, table, and figure
# from inside this artifact only. The artifact is fully self-contained;
# no external repository or network access is required.
#
# Outputs land under:
#   stats/    : numeric tables (.json, .csv, .tex)
#   figures/  : final paper figures (.png)
#   plots/    : auxiliary plot outputs
#   paper/    : refreshed PDF when --paper is passed
#
# Usage:
#   ./reproduce.sh                # numbers + figures
#   ./reproduce.sh --paper        # also rebuild the PDF (needs pdflatex)
#   ./reproduce.sh --skip-figures # numbers only
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

export KOZUCHI_ARTIFACT_ROOT="$HERE"

SKIP_FIGURES=0
BUILD_PAPER=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-figures) SKIP_FIGURES=1 ;;
    --paper) BUILD_PAPER=1 ;;
    -h|--help) sed -n '1,15p' "$0"; exit 0 ;;
    *) echo "error: unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

# ---------------------------------------------------------------------------
# 0. Ensure data archives are extracted.
# Numbers depend on the small files under data/trajectories/ (already
# checked-in) and the configs/ + experiments/.../src/csv/ folders. They do
# NOT need the gigabyte trajectory dumps that live in data/archives/.
# Figures referencing the workbook xlsx come from data/paper_comparison/.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 1. Regenerate numbers (stats/*.{json,csv,tex})
# ---------------------------------------------------------------------------
echo "[1/3] Regenerating paper numbers from artifact data ..."
bash scripts/numbers/run_all.sh

# ---------------------------------------------------------------------------
# 2. Regenerate figures
# ---------------------------------------------------------------------------
if [[ "$SKIP_FIGURES" == "0" ]]; then
  echo "[2/3] Regenerating figures ..."
  if command -v uv >/dev/null 2>&1; then
    uv run --with matplotlib python3 scripts/rq6_cross_track/build_rq6.py \
        --paper-root "$HERE/paper"
    uv run --with matplotlib --with numpy python3 scripts/figures/plot_python_vs_java.py
    uv run --with matplotlib --with numpy --with pandas --with seaborn --with openpyxl \
        python3 scripts/figures/plot_broad_with_java.py
  elif python3 -c "import matplotlib" >/dev/null 2>&1; then
    python3 scripts/rq6_cross_track/build_rq6.py --paper-root "$HERE/paper"
    python3 scripts/figures/plot_python_vs_java.py
    python3 scripts/figures/plot_broad_with_java.py
  else
    echo "warning: matplotlib unavailable; skipping figure regeneration" >&2
  fi

  # mirror RQ6 outputs to the artifact-level figures/ + stats/ so that
  # everything is also discoverable from the artifact root.
  if [[ -f "$HERE/paper/figures/cross_track_kozuchi.png" ]]; then
    cp "$HERE/paper/figures/cross_track_kozuchi.png" "$HERE/figures/"
  fi
  if [[ -f "$HERE/paper/stats/cross_track_summary.tex" ]]; then
    cp "$HERE/paper/stats/cross_track_summary.tex" "$HERE/stats/"
  fi
else
  echo "[2/3] Skipped figure regeneration (--skip-figures)"
fi

# ---------------------------------------------------------------------------
# 3. Optional: rebuild the PDF
# ---------------------------------------------------------------------------
if [[ "$BUILD_PAPER" == "1" ]]; then
  echo "[3/3] Rebuilding paper PDF (paper/main.pdf) ..."
  cd paper
  bash build.sh --skip-figures
  cd "$HERE"
else
  echo "[3/3] Skipped PDF build (pass --paper to enable)."
fi

echo
echo "Reproduction complete. Inspect:"
echo "  $HERE/stats/    -- numeric outputs"
echo "  $HERE/figures/  -- paper-ready figures"
echo "  $HERE/plots/    -- auxiliary plots"
echo "  $HERE/paper/main.pdf"
echo
echo "See INDEX.md for a number-to-script-to-section map."
