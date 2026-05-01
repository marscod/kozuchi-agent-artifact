#!/usr/bin/env bash
# compress.sh -- compress the heavy data sources inside the artifact.
#
# This script does *not* package the whole artifact. It operates only on the
# few large directories and files (trajectories, harness logs, raw
# predictions) that are too big to commit as loose files. Each recipe maps a
# loose source path inside the artifact to a single archive under
# ``data/archives/``. The rest of the artifact is small enough to commit
# directly to git.
#
# Usage:
#   ./compress.sh                 # build/refresh missing or stale archives
#   ./compress.sh --force         # rebuild every archive
#   ./compress.sh --prune         # delete the loose source after archiving
#                                  (useful right before ``git add``)
#   ./compress.sh --list          # show recipe status without doing anything
#   ./compress.sh -h              # help
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

ARCHIVES_DIR="$HERE/data/archives"
mkdir -p "$ARCHIVES_DIR"

# Recipe format: <archive_name>|<src_path_relative_to_HERE>|<kind>
#   kind=dir   -> tar+zstd a directory
#   kind=file  -> zstd-compress a single file
RECIPES=(
  "q35_verified500_tts8_75p2_submission_bundle_20260326-055715_merged500.tar.zst|data/trajectories/q35_verified500_tts8_75p2_submission_bundle_20260326-055715_merged500|dir"
  "python_evaluation_trajs.tar.zst|data/experiments/evaluation/verified/20260326_kozuchi-mini-swe-agent_qwen3.5-27b/trajs|dir"
  "python_evaluation_logs.tar.zst|data/experiments/evaluation/verified/20260326_kozuchi-mini-swe-agent_qwen3.5-27b/logs|dir"
  "java_evaluation_trajs.tar.zst|data/experiments/java/kozuchi-mswe-java-20260429/trajs|dir"
  "java_evaluation_logs.tar.zst|data/experiments/java/kozuchi-mswe-java-20260429/logs|dir"
  "java_evaluation_all_preds.jsonl.zst|data/experiments/java/kozuchi-mswe-java-20260429/all_preds.jsonl|file"
)

mode_op="build"
force=0
prune=0
while [ $# -gt 0 ]; do
  case "$1" in
    --list)  mode_op="list" ;;
    --force) force=1 ;;
    --prune) prune=1 ;;
    -h|--help) sed -n '1,19p' "$0"; exit 0 ;;
    *) echo "error: unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

if ! command -v zstd >/dev/null 2>&1; then
  echo "error: zstd is required (apt install zstd)" >&2; exit 1
fi
if ! command -v tar >/dev/null 2>&1; then
  echo "error: tar is required" >&2; exit 1
fi

human_size() {
  if [ -e "$1" ]; then
    du -sh "$1" 2>/dev/null | awk '{print $1}'
  fi
  return 0
}

archive_one() {
  local archive_name="$1" src_rel="$2" kind="$3"
  local archive_path="$ARCHIVES_DIR/$archive_name"
  local src_path="$HERE/$src_rel"

  if [ ! -e "$src_path" ]; then
    if [ -e "$archive_path" ]; then
      echo "[skip ] $archive_name -- source missing, archive already present ($(human_size "$archive_path"))"
    else
      echo "[warn ] $archive_name -- both source ($src_rel) and archive missing"
    fi
    return 0
  fi

  if [ "$force" -eq 0 ] && [ -e "$archive_path" ]; then
    echo "[fresh] $archive_name -- already built ($(human_size "$archive_path")); pass --force to rebuild"
    if [ "$prune" -eq 1 ]; then
      echo "[prune] removing loose $src_rel"
      rm -rf "$src_path"
    fi
    return 0
  fi

  echo "[pack ] $archive_name <- $src_rel"
  case "$kind" in
    dir)
      local parent base
      parent="$(dirname "$src_path")"
      base="$(basename "$src_path")"
      tar -C "$parent" \
          --use-compress-program='zstd -T0 -19' \
          --exclude='*.pyc' \
          --exclude='__pycache__' \
          --exclude='.DS_Store' \
          -cf "$archive_path" "$base"
      ;;
    file)
      zstd -19 -T0 -q -f -o "$archive_path" "$src_path"
      ;;
    *) echo "unknown kind: $kind" >&2; return 1 ;;
  esac
  echo "        -> $(human_size "$archive_path")"

  if [ "$prune" -eq 1 ]; then
    echo "[prune] removing loose $src_rel"
    rm -rf "$src_path"
  fi
}

list_one() {
  local archive_name="$1" src_rel="$2" kind="$3"
  local archive_path="$ARCHIVES_DIR/$archive_name"
  local src_path="$HERE/$src_rel"
  local arc_size src_size status
  arc_size="$(human_size "$archive_path" 2>/dev/null)"; arc_size="${arc_size:--}"
  src_size="$(human_size "$src_path"     2>/dev/null)"; src_size="${src_size:--}"
  if   [ ! -e "$src_path" ] && [ ! -e "$archive_path" ]; then status="missing"
  elif [ ! -e "$src_path" ]; then status="archive-only"
  elif [ ! -e "$archive_path" ]; then status="needs-pack"
  else status="ok"
  fi
  printf "  %-12s  %-4s  arc=%-7s  src=%-7s  %s\n" "$status" "$kind" "$arc_size" "$src_size" "$archive_name"
}

if [ "$mode_op" = "list" ]; then
  echo "Archive recipes -> $ARCHIVES_DIR/"
  for r in "${RECIPES[@]}"; do
    IFS='|' read -r archive_name src_rel kind <<<"$r"
    list_one "$archive_name" "$src_rel" "$kind"
  done
  exit 0
fi

for r in "${RECIPES[@]}"; do
  IFS='|' read -r archive_name src_rel kind <<<"$r"
  archive_one "$archive_name" "$src_rel" "$kind"
done

cat <<EOF

Done. Archives are under: $ARCHIVES_DIR/
Use ./decompress.sh to restore them in place when needed.
EOF
