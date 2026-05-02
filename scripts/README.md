# `paper/artifacts/scripts/` — every reproduction script

All scripts here read only from `../data/` and write only to
`../stats/`, `../figures/`, or `../plots/`. None of them reach outside
the artifact folder.

| Sub-directory | Purpose | Entry-point |
|---|---|---|
| [`numbers/`](numbers/) | Regenerate every paper-cited integer / percentage / table fragment. Pure standard-library Python (no third-party deps). | [`numbers/run_all.sh`](numbers/run_all.sh) |
| [`figures/`](figures/) | Regenerate plots that aren't covered by the canonical `analysis/make_figures.py` (cross-track audit + parameter-efficiency Pareto). Needs `matplotlib`, `pandas`, `seaborn`, `numpy`, `openpyxl`. | each script can be run directly |
| [`rq6_cross_track/`](rq6_cross_track/) | Standalone RQ6 reproduction bundle (Python ↔ Java cross-track table + figure). Deterministic; consumes only the bundled CSVs in `rq6_cross_track/csv/`. | [`rq6_cross_track/build_rq6.py`](rq6_cross_track/build_rq6.py) |
| [`analysis/`](analysis/) | Original Python (RQ1–RQ5) analysis source: deeper analyses cited in §RQ1–§RQ5 (failures, trajectories, peers, conversations, statistics). Used together with `data/experiments/.../src/csv/`. | per-file (e.g. `python3 analyze_failures.py`) |

## Numbers (paper-table fragments)

```bash
bash scripts/numbers/run_all.sh                           # all of them
KOZUCHI_ARTIFACT_ROOT=/abs/path scripts/numbers/run_all.sh # explicit root
```

Each script writes JSON, CSV, and a `\input{}`-able LaTeX fragment
under `../stats/`. Inputs:

| Script | Reads | Writes (under ../stats/) |
|---|---|---|
| [`compute_per_run_stats.py`](numbers/compute_per_run_stats.py) | `data/trajectories/.../runs/r0X_s100X/report.json` (and Java `xcheck_preds_score.json` when present) | `per_run_pass1.{json,csv,tex}` |
| [`compute_xcheck_summary.py`](numbers/compute_xcheck_summary.py) | `data/trajectories/.../xcheck/results/...75p2.json`, `bundle_manifest.json`, `selector_audit.json` | `xcheck_summary.{json,tex}` |
| [`compute_selector_audit.py`](numbers/compute_selector_audit.py) | xcheck results / inputs / instance_test_tables | `selector_audit.{json,tex}` |
| [`compute_selector_ablation.py`](numbers/compute_selector_ablation.py) | per-run `report.json` / `preds.json` + xcheck instance tables | `selector_ablation.{json,csv,tex}` |
| [`compute_run_overlap.py`](numbers/compute_run_overlap.py) | per-run `report.json` | `run_overlap.json` |
| [`compute_repo_year_breakdown.py`](numbers/compute_repo_year_breakdown.py) | `data/experiments/.../README.md` | `resolved_by_repo.{json,tex}`, `resolved_by_year.{json,tex}` |
| [`compute_phase_inventory.py`](numbers/compute_phase_inventory.py) | `data/configs/agent_sota.yaml` | `phase_inventory.json`, `phase_edges.csv` |
| [`compute_action_format_inventory.py`](numbers/compute_action_format_inventory.py) | `data/configs/agent_sota.yaml` | `action_format_inventory.{json,tex}` |
| [`compute_model_inventory.py`](numbers/compute_model_inventory.py) | `data/configs/{model_*,chat-template_*,environment_*}.yaml` | `model_inventory.{json,tex}` |
| [`compute_tool_inventory.py`](numbers/compute_tool_inventory.py) | `data/configs/agent_sota.yaml`, `data/operational_metadata/tool_files.csv` | `tool_inventory.{json,tex}` |
| [`compute_skill_inventory.py`](numbers/compute_skill_inventory.py) | `data/configs/agent_sota.yaml` | `skill_inventory.json` |
| [`compute_pipeline_inventory.py`](numbers/compute_pipeline_inventory.py) | `data/operational_metadata/{ci_stages,ci_reuse_vars,ci_cluster_tags,cluster_env_names}.csv` | `pipeline_inventory.{json,tex}` |
| [`compute_workflow_replacement.py`](numbers/compute_workflow_replacement.py) | aggregates: configs, agent tools, headline / failure_modes / patch_apply CSVs, bundle_manifest, Java analysis | `workflow_replacement.{json,tex}`, `operational_outcomes.tex` |

## Figures

```bash
KOZUCHI_ARTIFACT_ROOT=$(cd ..; pwd) python3 scripts/rq6_cross_track/build_rq6.py --paper-root ../paper
KOZUCHI_ARTIFACT_ROOT=$(cd ..; pwd) python3 scripts/figures/plot_python_vs_java.py
KOZUCHI_ARTIFACT_ROOT=$(cd ..; pwd) python3 scripts/figures/plot_broad_with_java.py
```

These three scripts produce, respectively:

* `figures/cross_track_kozuchi.png` (RQ6 two-panel summary)
* `figures/fig_python_vs_java.png` (six-panel cross-track audit)
* `figures/broad_success_vs_params_with_java.png` and
  `plots/broad_success_vs_params_with_java.png` (cover Pareto frontier)

The richer `fig0X_*.png` figures (per-repo heatmap, peer scatter,
Pareto compute plot) are produced by
[`analysis/make_figures.py`](analysis/make_figures.py); they ship
already rendered under
`../data/experiments/evaluation/verified/.../src/figures/` *and* under
`../figures/` for the ones referenced by `paper/main.tex`.

## Conventions

* Every script defines its inputs and outputs at the top of the file
  in module-level constants. The artifact-relative `_paths.py` shim
  lives next to the scripts that need it.
* Scripts use only the Python standard library when feasible (the
  `numbers/` set deliberately has no `pyyaml` dependency, parsing the
  agent config with `re`).
* When a script writes a LaTeX fragment, the first line is a
  `% Auto-generated by ...` comment recording the script source.
* Long-running stages are idempotent: re-running them overwrites the
  outputs deterministically.
