#!/usr/bin/env bash
# Regenerate every JSON / CSV / LaTeX fragment under
# paper/artifacts/stats/ from files inside this artifact only.
# Idempotent; safe to re-run.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ART_ROOT="$(cd "$HERE/../.." && pwd)"
OUT_DIR="$ART_ROOT/stats"
mkdir -p "$OUT_DIR"

cd "$HERE"

export KOZUCHI_ARTIFACT_ROOT="$ART_ROOT"

python3 compute_per_run_stats.py
python3 compute_selector_audit.py
python3 compute_xcheck_summary.py
python3 compute_selector_ablation.py
python3 compute_repo_year_breakdown.py
python3 compute_phase_inventory.py
python3 compute_action_format_inventory.py
python3 compute_model_inventory.py
python3 compute_run_overlap.py
python3 compute_tool_inventory.py
python3 compute_skill_inventory.py
python3 compute_pipeline_inventory.py
python3 compute_workflow_replacement.py

python3 - <<PY
import json
from pathlib import Path
out_dir = Path("$OUT_DIR")
manifest = {
    "run_id": "artifact",
    "outputs": sorted(p.name for p in out_dir.iterdir() if p.is_file()),
}
(out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
print(json.dumps(manifest, indent=2))
PY

echo "Wrote: $OUT_DIR"
