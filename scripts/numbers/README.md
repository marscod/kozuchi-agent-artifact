# `paper/artifacts/scripts/numbers/`

Reproducibility scripts for paper-cited numbers, tables, and inventory
fragments.

Every script in this directory is a small, dependency-free Python file
that derives a verifiable number, table, or inventory from files
under [`../../data/`](../../data/). None of the scripts fetches data
from the network. Outputs land under
[`../../stats/`](../../stats/) as JSON, CSV, and LaTeX fragments.

## Run

```bash
# from artifacts root:
./reproduce.sh --skip-figures

# or directly:
bash scripts/numbers/run_all.sh
```

## What each script reads and writes

All paths are relative to `paper/artifacts/`.

| Script | Reads | Writes (under `stats/`) |
|---|---|---|
| `compute_per_run_stats.py` | `data/trajectories/q35_.../runs/r0X_s100X/report.json`, optional Java `xcheck_preds_score.json` | `per_run_pass1.{json,csv,tex}` |
| `compute_xcheck_summary.py` | `data/trajectories/q35_.../xcheck/results/*_75p2.json`, `bundle_manifest.json` | `xcheck_summary.{json,tex}` |
| `compute_selector_audit.py` | xcheck results / inputs / instance test tables | `selector_audit.{json,tex}` |
| `compute_selector_ablation.py` | per-run `report.json` / `preds.json` + xcheck tables | `selector_ablation.{json,csv,tex}` |
| `compute_run_overlap.py` | `data/trajectories/q35_.../runs/r0X_s100X/report.json` | `run_overlap.json` |
| `compute_repo_year_breakdown.py` | `data/experiments/.../README.md` | `resolved_by_repo.{json,tex}`, `resolved_by_year.{json,tex}` |
| `compute_phase_inventory.py` | `data/configs/agent_sota.yaml` | `phase_inventory.json`, `phase_edges.csv` |
| `compute_action_format_inventory.py` | `data/configs/agent_sota.yaml` | `action_format_inventory.{json,tex}` |
| `compute_model_inventory.py` | `data/configs/{model_*,chat-template_*,environment_*}.yaml` | `model_inventory.{json,tex}` |
| `compute_tool_inventory.py` | `data/configs/agent_sota.yaml`, `data/operational_metadata/tool_files.csv` | `tool_inventory.{json,tex}` |
| `compute_skill_inventory.py` | `data/configs/agent_sota.yaml` | `skill_inventory.json` |
| `compute_pipeline_inventory.py` | `data/operational_metadata/{ci_stages,ci_reuse_vars,ci_cluster_tags,cluster_env_names}.csv` | `pipeline_inventory.{json,tex}` |
| `compute_workflow_replacement.py` | configs, tools, Python and Java CSVs, bundle manifest, comparison.md | `workflow_replacement.{json,tex}`, `operational_outcomes.tex` |

After all scripts have run, `stats/manifest.json` lists every emitted
file.

## Conventions

* Scripts use only the Python standard library (`json`, `csv`, `re`,
  `pathlib`, `statistics`). No `pyyaml` dependency on purpose, so the
  scripts run in any environment that has Python 3.10+.
* Every LaTeX fragment is wrapped in a `tabular` block and annotated
  with the source file as a LaTeX comment. The manuscript pulls them in
  with `\input{}`.
* Numbers in the manuscript are quoted by re-deriving them at build time
  from these JSON outputs; we do not type any score by hand.

## Path resolution

The shared [`_paths.py`](_paths.py) module computes an artifact root
relative to its own location, so the scripts work regardless of where
the artifact is unpacked. Override with the env var:

```bash
KOZUCHI_ARTIFACT_ROOT=/some/abs/path bash run_all.sh
```
