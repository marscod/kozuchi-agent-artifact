#!/usr/bin/env bash
# decompress.sh -- restore the heavy data sources from data/archives/.
#
# Counterpart to compress.sh. Each recipe maps an archive under
# ``data/archives/`` to the loose location it should be extracted to. By
# default a destination that already exists is skipped so the script is
# idempotent.
#
# Usage:
#   ./decompress.sh                # extract every recipe (skip if present)
#   ./decompress.sh --force        # re-extract even if destination exists
#   ./decompress.sh --list         # show recipe status only
#   ./decompress.sh -h             # help
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

ARCHIVES_DIR="$HERE/data/archives"

# Recipe format: <archive_name>|<dest_path_relative_to_HERE>|<kind>
#   kind=dir   -> tar+zstd that expands into the dest's parent directory
#   kind=file  -> zstd-compressed single file written to dest
RECIPES=(
  "q35_verified500_tts8_75p2_submission_bundle_20260326-055715_merged500.tar.zst|data/trajectories/q35_verified500_tts8_75p2_submission_bundle_20260326-055715_merged500|dir"
  "python_evaluation_trajs.tar.zst|data/experiments/evaluation/verified/20260326_kozuchi-mini-swe-agent_qwen3.5-27b/trajs|dir"
  "python_evaluation_logs.tar.zst|data/experiments/evaluation/verified/20260326_kozuchi-mini-swe-agent_qwen3.5-27b/logs|dir"
  "java_evaluation_trajs.tar.zst|data/experiments/java/kozuchi-mswe-java-20260429/trajs|dir"
  "java_evaluation_logs.tar.zst|data/experiments/java/kozuchi-mswe-java-20260429/logs|dir"
  "java_evaluation_all_preds.jsonl.zst|data/experiments/java/kozuchi-mswe-java-20260429/all_preds.jsonl|file"
)

mode_op="extract"
force=0
while [ $# -gt 0 ]; do
  case "$1" in
    --list)  mode_op="list" ;;
    --force) force=1 ;;
    -h|--help) sed -n '1,15p' "$0"; exit 0 ;;
    *) echo "error: unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

if ! command -v zstd >/dev/null 2>&1; then
  echo "error: zstd is required (apt install zstd)" >&2; exit 1
fi

human_size() {
  if [ -e "$1" ]; then
    du -sh "$1" 2>/dev/null | awk '{print $1}'
  fi
  return 0
}

extract_one() {
  local archive_name="$1" dest_rel="$2" kind="$3"
  local archive_path="$ARCHIVES_DIR/$archive_name"
  local dest_path="$HERE/$dest_rel"

  if [ ! -e "$archive_path" ]; then
    echo "[skip ] $archive_name -- archive missing under data/archives/"
    return 0
  fi

  if [ "$force" -eq 0 ] && [ -e "$dest_path" ]; then
    echo "[fresh] $dest_rel -- already present ($(human_size "$dest_path")); pass --force to overwrite"
    return 0
  fi

  case "$kind" in
    dir)
      local parent
      parent="$(dirname "$dest_path")"
      mkdir -p "$parent"
      [ -e "$dest_path" ] && rm -rf "$dest_path"
      echo "[unpk ] $archive_name -> $dest_rel/"
      zstd -d -c "$archive_path" | tar -C "$parent" -xf -
      ;;
    file)
      mkdir -p "$(dirname "$dest_path")"
      [ -e "$dest_path" ] && rm -f "$dest_path"
      echo "[unpk ] $archive_name -> $dest_rel"
      zstd -d -f -q -o "$dest_path" "$archive_path"
      ;;
    *) echo "unknown kind: $kind" >&2; return 1 ;;
  esac
  echo "        -> $(human_size "$dest_path")"
}

list_one() {
  local archive_name="$1" dest_rel="$2" kind="$3"
  local archive_path="$ARCHIVES_DIR/$archive_name"
  local dest_path="$HERE/$dest_rel"
  local arc_size dest_size status
  arc_size="$(human_size "$archive_path" 2>/dev/null)"; arc_size="${arc_size:--}"
  dest_size="$(human_size "$dest_path"   2>/dev/null)"; dest_size="${dest_size:--}"
  if   [ ! -e "$archive_path" ] && [ ! -e "$dest_path" ]; then status="missing"
  elif [ ! -e "$archive_path" ]; then status="loose-only"
  elif [ ! -e "$dest_path" ]; then status="needs-unpack"
  else status="ok"
  fi
  printf "  %-13s  %-4s  arc=%-7s  dest=%-7s  %s\n" "$status" "$kind" "$arc_size" "$dest_size" "$archive_name"
}

if [ ! -d "$ARCHIVES_DIR" ] && [ "$mode_op" != "list" ]; then
  echo "error: $ARCHIVES_DIR not found" >&2
  exit 1
fi

if [ "$mode_op" = "list" ]; then
  echo "Recipes (archive -> destination):"
  for r in "${RECIPES[@]}"; do
    IFS='|' read -r archive_name dest_rel kind <<<"$r"
    list_one "$archive_name" "$dest_rel" "$kind"
  done
  exit 0
fi

for r in "${RECIPES[@]}"; do
  IFS='|' read -r archive_name dest_rel kind <<<"$r"
  extract_one "$archive_name" "$dest_rel" "$kind"
done

echo
echo "Done."
