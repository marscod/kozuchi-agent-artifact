#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MAIN_TEX="main.tex"
BUILD_DIR="$SCRIPT_DIR/build"
SKIP_FIGURES=0
FORCE_FIGURES=0

sync_comparison_figures() {
  local plots_dir="$SCRIPT_DIR/../comparison/plots"
  local figures_dir="$SCRIPT_DIR/figures"
  mkdir -p "$figures_dir"

  local name
  for name in broad_success_vs_params.png broad_success_vs_params_with_java.png; do
    local source="$plots_dir/$name"
    local destination="$figures_dir/$name"
    if [[ ! -f "$source" ]]; then
      echo "warning: missing comparison plot: $source" >&2
      continue
    fi
    cp "$source" "$destination"
    echo "Copied comparison plot: figures/$name"
  done
}

usage() {
  cat <<'EOF'
Usage: ./build.sh [--skip-figures] [--force-figures]

Build the standalone final paper package from paper/final/main.tex.
The build writes build/main.pdf, refreshes main.pdf, and creates
build/paper-final.zip containing the standalone source package.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --skip-figures)
      SKIP_FIGURES=1
      shift
      ;;
    --force-figures)
      FORCE_FIGURES=1
      shift
      ;;
    *)
      echo "error: unexpected argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

render_drawio_figures() {
  if [[ "$SKIP_FIGURES" == "1" ]]; then
    echo "Skipped draw.io figure rendering (--skip-figures)"
    return 0
  fi

  shopt -s nullglob
  local sources=(figures/*.drawio)
  shopt -u nullglob
  if [[ "${#sources[@]}" -eq 0 ]]; then
    echo "Rendered 0 draw.io figure source(s)"
    return 0
  fi

  local drawio_bin=""
  for candidate in drawio draw.io drawio-desktop; do
    if command -v "$candidate" >/dev/null 2>&1; then
      drawio_bin="$candidate"
      break
    fi
  done

  local npx_bin=""
  if [[ -z "$drawio_bin" ]] && command -v npx >/dev/null 2>&1; then
    npx_bin="$(command -v npx)"
  fi

  if [[ -z "$drawio_bin" && -z "$npx_bin" ]]; then
    echo "warning: draw.io renderer not found; using checked-in rendered figures" >&2
    return 0
  fi

  local rendered=0
  local source base format output
  for source in "${sources[@]}"; do
    base="${source%.drawio}"
    for format in pdf png; do
      output="$base.$format"
      if [[ "$FORCE_FIGURES" != "1" && -f "$output" && "$output" -nt "$source" ]]; then
        continue
      fi
      if [[ -n "$drawio_bin" ]]; then
        "$drawio_bin" --export --format "$format" --output "$output" "$source"
      else
        "$npx_bin" --yes --prefer-offline draw.io-export "$source" -F "$format" -o "$output"
      fi
      rendered=$((rendered + 1))
    done
  done
  echo "Rendered $rendered draw.io output(s)"
}

build_rq6_assets() {
  local script="$SCRIPT_DIR/sources/rq6-cross-track/build_rq6.py"
  if [[ ! -f "$script" ]]; then
    return 0
  fi

  if command -v uv >/dev/null 2>&1; then
    uv run --with matplotlib python "$script" --paper-root "$SCRIPT_DIR"
    return 0
  fi

  if python3 - <<'PY' >/dev/null 2>&1
import matplotlib  # noqa: F401
PY
  then
    python3 "$script" --paper-root "$SCRIPT_DIR"
    return 0
  fi

  echo "warning: matplotlib unavailable; using checked-in RQ6 table/figure" >&2
}

build_pdf() {
  mkdir -p "$BUILD_DIR"
  export TEXINPUTS="$SCRIPT_DIR//:${TEXINPUTS:-}"
  export BIBINPUTS="$SCRIPT_DIR:${BIBINPUTS:-}"
  export BSTINPUTS="$SCRIPT_DIR:${BSTINPUTS:-}"

  if command -v latexmk >/dev/null 2>&1; then
    latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir="$BUILD_DIR" "$MAIN_TEX"
  else
    if ! command -v pdflatex >/dev/null 2>&1; then
      echo "error: neither latexmk nor pdflatex is installed" >&2
      exit 1
    fi
    pdflatex -interaction=nonstopmode -halt-on-error -output-directory "$BUILD_DIR" "$MAIN_TEX"
    if [[ -f "$BUILD_DIR/main.aux" ]] && command -v bibtex >/dev/null 2>&1; then
      (cd "$BUILD_DIR" && bibtex main) || true
    fi
    for _ in 1 2 3 4; do
      pdflatex -interaction=nonstopmode -halt-on-error -output-directory "$BUILD_DIR" "$MAIN_TEX"
    done
  fi

  cp "$BUILD_DIR/main.pdf" "$SCRIPT_DIR/main.pdf"
}

write_zip() {
  local zip_path="$BUILD_DIR/paper-final.zip"
  ZIP_PATH="$zip_path" python3 - <<'PY'
from __future__ import annotations

import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path.cwd()
zip_path = Path(os.environ["ZIP_PATH"])
zip_path.unlink(missing_ok=True)

include_roots = [
    "README.md",
    "build.sh",
    "main.tex",
    "main.pdf",
    "references.bib",
    "source-index.md",
    "ACM-Reference-Format.bst",
    "acmart.cls",
    "acmart-tagged.cls",
    "acmauthoryear.bbx",
    "acmauthoryear.cbx",
    "acmnumeric.bbx",
    "acmnumeric.cbx",
    "acmdatamodel.dbx",
    "figures",
    "stats",
    "sources",
]

with ZipFile(zip_path, "w", ZIP_DEFLATED) as zf:
    for name in include_roots:
        path = root / name
        if not path.exists():
            continue
        if path.is_file():
            zf.write(path, Path("paper-final") / name)
            continue
        for child in sorted(path.rglob("*")):
            if child.is_file():
                zf.write(child, Path("paper-final") / child.relative_to(root))
PY
  echo "Wrote zip: ${zip_path#$SCRIPT_DIR/}"
}

sync_comparison_figures
render_drawio_figures
build_rq6_assets
build_pdf
write_zip

echo "Built PDF: build/main.pdf"
