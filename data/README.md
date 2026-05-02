# `paper/artifacts/data/` — primary inputs

Every reproduction script consumes files only from inside this folder.
Nothing here points outside `paper/artifacts/`.

| Sub-directory | Used by | Contents |
|---|---|---|
| `archives/` | [`../compress.sh`](../compress.sh) / [`../decompress.sh`](../decompress.sh) | Compressed `*.tar.zst` bundles for the heavy artifacts: full trajectory bundle, per-track raw trajectories and harness logs, Java predictions. The only artifact directory that needs out-of-band hosting (Git LFS / OSF / Zenodo) on size-restricted git hosts. |
| `configs/` | every `compute_*_inventory.py`, `compute_phase_inventory.py`, `compute_action_format_inventory.py`, `compute_skill_inventory.py`, `compute_tool_inventory.py`, `compute_model_inventory.py`, `compute_workflow_replacement.py` | Agent runtime config (`agent_sota.yaml`) plus all `model_*.yaml`, `chat-template_*.yaml`, and `environment_*.yaml`. |
| `operational_metadata/` | `compute_pipeline_inventory.py`, `compute_tool_inventory.py`, `compute_workflow_replacement.py` | Redacted CI / cluster / tool inventory CSVs: `ci_stages.csv`, `ci_reuse_vars.csv`, `ci_cluster_tags.csv`, `cluster_env_names.csv`, `tool_files.csv`. The raw `.gitlab-ci.yml`, `scripts/module_load.sh`, and `swe_sota_agent/tools/*.py` are not shipped (internal runner tags / SLURM partitions / tokens / tool implementations). See `operational_metadata/README.md`. |
| `trajectories/` | `compute_per_run_stats.py`, `compute_run_overlap.py`, `compute_xcheck_summary.py`, `compute_selector_audit.py`, `compute_selector_ablation.py` | Per-instance trajectory bundle. The small files (per-run reports, predictions, xcheck inputs/results) are checked in directly. The 22 GB raw trajectories live as `archives/q35_..._merged500.tar.zst` and can be restored with `decompress.sh`. |
| `experiments/evaluation/verified/20260326_kozuchi-mini-swe-agent_qwen3.5-27b/` | `compute_workflow_replacement.py`, `compute_repo_year_breakdown.py`, all `analyze_*.py` scripts | Python (SWE-bench Verified) submission directory: `README.md`, `metadata.yaml`, `results/results.json`, `src/csv/*.csv`, `src/figures/*.png`, `src/*.py`, `src/analysis.md`, `src/revision.md`. |
| `experiments/java/kozuchi-mswe-java-20260429/` | `compute_per_run_stats.py`, `build_rq6.py`, Java analysis | Java (Multi-SWE-bench Verified) submission directory with the same shape as Python plus `logs/_harness/xcheck_preds_score.json`. |
| `experiments/comparison_src/`, `experiments/comparison.md` | RQ6 narrative; `plot_python_vs_java.py` | Cross-track comparison report and helper script. |
| `paper_comparison/` | `plot_broad_with_java.py`, `analyze_comparison.py` | The *SWE-bench comparison* workbook (`SWE-bench comparison.xlsx`) + analysis report. |
| `paper_java_src/` | `plot_broad_with_java.py` | Java leaderboard CSV mirror used by the parameter-efficiency figure. |

## Provenance

The original workspace paths for each subfolder are recorded in
[`../paper/source-index.md`](../paper/source-index.md) and in the LaTeX
comments of `paper/main.tex`. Every script under
[`../scripts/`](../scripts/) only reads from this folder and writes to
[`../stats/`](../stats/) or [`../figures/`](../figures/).

## Packing / unpacking heavy data

`compress.sh` and `decompress.sh` are recipe-driven. Each recipe maps
one archive under `archives/` to one loose directory or single file
elsewhere under `data/`. They never touch any other part of the
artifact.

```bash
../compress.sh   --list             # show recipe status (which sources need packing)
../compress.sh                      # build any missing/stale archives
../compress.sh   --force            # rebuild every archive
../compress.sh   --prune            # archive AND delete the loose source
                                    # (use right before `git add`)

../decompress.sh --list             # show recipe status (which destinations need unpacking)
../decompress.sh                    # extract every archive (skip if destination present)
../decompress.sh --force            # re-extract, overwriting the loose tree
```

Each archive expands to (or is built from) the location below:

```
archives/q35_..._merged500.tar.zst
   <-> trajectories/q35_..._merged500/{runs/r0X_s100X/trajectories/...}
archives/python_evaluation_trajs.tar.zst
   <-> experiments/evaluation/verified/.../trajs/...
archives/python_evaluation_logs.tar.zst
   <-> experiments/evaluation/verified/.../logs/...
archives/java_evaluation_trajs.tar.zst
   <-> experiments/java/kozuchi-mswe-java-20260429/trajs/...
archives/java_evaluation_logs.tar.zst
   <-> experiments/java/kozuchi-mswe-java-20260429/logs/...
archives/java_evaluation_all_preds.jsonl.zst
   <-> experiments/java/kozuchi-mswe-java-20260429/all_preds.jsonl
```
