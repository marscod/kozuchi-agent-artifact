# Kozuchi Agent — Reproducibility Artifact

This directory is the **self-contained artifact** for the paper:

> *Kozuchi Agent: A Language-Agnostic Open-Weight Agent for Software Repair*
> (Bahrami et al., manuscript under review)

The full paper PDF is at [`paper/main.pdf`](paper/main.pdf), and the
LaTeX sources are at [`paper/main.tex`](paper/main.tex). The bundled
LaTeX bibliography is [`paper/references.bib`](paper/references.bib);
its annotated index lives in
[`REFERENCES_INDEX.md`](REFERENCES_INDEX.md).

Everything cited in the paper — every numeric value, every figure,
every table, every trajectory-bundle counter — is regenerable from
files **inside this folder only**. Nothing ever points to a path
outside `paper/artifacts/`.

| Quick links | What it gives you |
|---|---|
| [`INDEX.md`](INDEX.md) | One row per paper number. Each row links to the deriving script, the cited section/figure/table, and the regenerated artifact under `stats/` or `figures/`. |
| [`REFERENCES_INDEX.md`](REFERENCES_INDEX.md) | Annotated bibliography indexing `paper/references.bib`: every cite key, URL, and why the paper uses it. |
| [`reproduce.sh`](reproduce.sh) | One-command rebuild of every number and figure. |
| [`compress.sh`](compress.sh) / [`decompress.sh`](decompress.sh) | Pack / unpack the heavy trajectory and log directories under `data/archives/`. |
| [`notebooks/reproduce.ipynb`](notebooks/reproduce.ipynb) | Rendered, narrative walkthrough of every paper number. |
| [`notebooks/reproduce.html`](notebooks/reproduce.html) | Static HTML render of the notebook (open in any browser, no Jupyter required). |

---

## 1. Layout

```
paper/artifacts/
├── README.md               <- you are here
├── INDEX.md                <- paper-number ↔ script ↔ section ↔ output
├── REFERENCES_INDEX.md     <- bibliography index for paper/references.bib
├── reproduce.sh            <- regenerate every cited number / figure
├── compress.sh             <- pack data/trajectories + heavy logs to data/archives/
├── decompress.sh           <- restore data/archives/*.zst back into place
│
├── paper/                  <- LaTeX sources, figures, stats, build.sh
│   ├── main.tex            <- final paper source
│   ├── main.pdf            <- compiled paper (mirrored)
│   ├── references.bib      <- bibliography
│   ├── source-index.md     <- list of cited external sources
│   ├── figures/            <- figures used by main.tex
│   ├── stats/              <- LaTeX fragments / JSON used by main.tex
│   └── build.sh            <- rebuild PDF (latexmk / pdflatex)
│
├── scripts/                <- every reproduction script
│   ├── numbers/            <- compute_*.py + run_all.sh (paper numbers)
│   ├── figures/            <- plot_*.py figure scripts
│   ├── analysis/           <- richer analyses cited in §RQ1–RQ6
│   └── rq6_cross_track/    <- standalone RQ6 reproduction bundle
│
├── stats/                  <- regenerated stats (mirrored from paper/stats)
├── figures/                <- regenerated figures (mirrored from paper/figures)
├── plots/                  <- auxiliary plot outputs (Pareto frontier etc.)
├── notebooks/              <- rendered Jupyter notebook
│
└── data/                   <- self-contained inputs
    ├── archives/           <- *.tar.zst bundles for the heavy artifacts
    ├── configs/            <- agent_sota.yaml, model_*.yaml, ...
    ├── operational_metadata/ <- redacted CI / cluster / tool inventory CSVs
    │                          (replaces the old repo_meta/ and
    │                          swe_sota_agent/tools/ mirrors; see
    │                          operational_metadata/README.md)
    ├── trajectories/       <- per-instance trajectory bundle (small files
    │                          checked in; raw trajectories archived)
    ├── experiments/        <- Python (Verified) and Java (Multi-SWE-bench)
    │                          evaluation directories with src/, results/,
    │                          metadata.yaml, README.md, comparison.md
    ├── paper_comparison/   <- xlsx workbook + java leaderboard plots
    └── paper_java_src/     <- Java analysis CSVs (used by figures)
```

---

## 2. Quick-start

### 2.1 Regenerate every paper number and figure

```bash
./reproduce.sh                # numbers + figures (stats/, figures/, plots/)
./reproduce.sh --paper        # same as above, plus rebuild paper/main.pdf
./reproduce.sh --skip-figures # numbers only (no matplotlib needed)
```

The script:

1. Runs every script under `scripts/numbers/` (see
   [`scripts/numbers/run_all.sh`](scripts/numbers/run_all.sh)) which
   emits 30 files under [`stats/`](stats/).
2. Regenerates the RQ6 cross-track table and figure
   ([`scripts/rq6_cross_track/build_rq6.py`](scripts/rq6_cross_track/build_rq6.py)).
3. Regenerates the Python-vs-Java six-panel figure
   ([`scripts/figures/plot_python_vs_java.py`](scripts/figures/plot_python_vs_java.py)).
4. Regenerates the parameter-efficiency Pareto figure
   ([`scripts/figures/plot_broad_with_java.py`](scripts/figures/plot_broad_with_java.py)).
5. Optionally rebuilds the paper PDF (`--paper`).

### 2.2 What you need

* Python 3.10+ (no third-party packages required for `scripts/numbers/`).
* `matplotlib`, `pandas`, `seaborn`, `numpy`, `openpyxl` for the figure
  scripts. Install with `pip install matplotlib pandas seaborn numpy openpyxl`,
  or run `reproduce.sh` directly: it auto-uses `uv run --with ...` when
  `uv` is on `$PATH`.
* `pdflatex` / `latexmk` (TeX Live) only if you want
  `./reproduce.sh --paper`.

### 2.3 Heavy data (raw trajectories and harness logs)

The full 22 GB of agent trajectories and 4.5 GB of SWE-bench harness
logs are not needed to recompute paper numbers — the small JSON
reports under `data/trajectories/.../runs/r0X/report.json` are
sufficient. The heavy directories are stored as compressed `*.tar.zst`
archives under [`data/archives/`](data/archives/). Restore them in
place with:

```bash
./decompress.sh                                 # extract every archive (idempotent)
./decompress.sh --list                          # show recipe status
./decompress.sh --force                         # re-extract, overwriting the loose tree
```

To regenerate the archives after editing the loose data, or to clear
the loose copies before `git add`, use the matching `compress.sh`:

```bash
./compress.sh                                   # build any missing/stale archives
./compress.sh --list                            # show recipe status
./compress.sh --force                           # rebuild every archive
./compress.sh --prune                           # archive AND delete the loose source
```

Both scripts are recipe-driven; the recipe table is the only source of
truth and is duplicated identically in `compress.sh` and
`decompress.sh`. Current recipes:

| Archive (under `data/archives/`) | Compressed | Expanded | Loose location |
|---|---:|---:|---|
| `q35_verified500_tts8_75p2_submission_bundle_20260326-055715_merged500.tar.zst` | 533 MB | 22 GB | `data/trajectories/q35_..._merged500/` |
| `python_evaluation_trajs.tar.zst` | 80 MB | 2.7 GB | `data/experiments/evaluation/verified/.../trajs/` |
| `python_evaluation_logs.tar.zst` | 1.4 MB | 33 MB | `data/experiments/evaluation/verified/.../logs/` |
| `java_evaluation_trajs.tar.zst` | 421 MB | 1.2 GB | `data/experiments/java/.../trajs/` |
| `java_evaluation_logs.tar.zst` | 202 MB | 308 MB | `data/experiments/java/.../logs/` |
| `java_evaluation_all_preds.jsonl.zst` | 197 MB | 255 MB | `data/experiments/java/.../all_preds.jsonl` |

### 2.4 Submitting to git

There is no top-level "lite vs full" bundle — the artifact tree is
checked into git as-is. Only `data/archives/*.zst` (≈1.4 GB) needs an
out-of-band channel (e.g. Git LFS, OSF, Zenodo) if your repository
host imposes file-size limits. Typical submission flow:

```bash
./compress.sh --prune    # produce every archive AND remove the loose source
git add -A               # commit the artifact (archives included or LFS-tracked)
# reviewers run:
./decompress.sh          # restore the loose trajectories where reproduction expects them
```

---

## 3. Walkthrough notebook

For a reviewer-friendly narrative pass that prints every paper number
side-by-side with its source script and its location in `main.tex`:

* **No tools required** — open
  [`notebooks/reproduce.html`](notebooks/reproduce.html) in any
  browser to see the fully rendered walkthrough with all outputs
  inlined.
* **Interactive re-execution** — open
  [`notebooks/reproduce.ipynb`](notebooks/reproduce.ipynb) in Jupyter
  and re-run every cell to regenerate numbers and figures from
  scratch:

```bash
jupyter notebook notebooks/reproduce.ipynb
```

Both files are committed in **rendered** form so that opening them on
GitHub / GitLab shows every output without re-execution.

---

## 4. Trust model and license boundary

* Numbers and figures are derivable from artifacts only. We never
  reach for the SWE-bench hidden test labels at selection time, nor do
  we use any closed-source verifier.
* Model weights for `Qwen/Qwen3.5-27B`, `Devstral`, and the Nemotron
  backbones are *not* shipped here; they are gated by their providers'
  licenses. The model inventory under
  `paper/stats/model_inventory.tex` records which configs reference
  them.
* Internal cluster paths, SLURM partitions, runner tokens, and the
  agent's tool source code are not shipped with this artifact. The CI
  / cluster / tool-inventory claims cited in the paper are reproduced
  from the redacted CSVs under `data/operational_metadata/`; the
  upstream `.gitlab-ci.yml`, `scripts/module_load.sh`, and
  `swe_sota_agent/tools/*.py` are intentionally omitted.
* Source attribution for cited external work is in
  [`REFERENCES_INDEX.md`](REFERENCES_INDEX.md) and
  [`paper/source-index.md`](paper/source-index.md); each ties a
  bibliography key to a publicly resolvable URL.

---

## 5. Reading order

1. [`INDEX.md`](INDEX.md) — tour the paper through its numbers; every
   row links to the script that produces it and the section that
   discusses it.
2. [`paper/main.pdf`](paper/main.pdf) — the paper itself.
3. [`notebooks/reproduce.html`](notebooks/reproduce.html) (static) or
   [`notebooks/reproduce.ipynb`](notebooks/reproduce.ipynb) (live) —
   narrative reproduction with inlined data.
4. [`scripts/numbers/`](scripts/numbers/) and
   [`scripts/figures/`](scripts/figures/) — implementation.
5. [`data/`](data/) — primary inputs (configs, CSVs, JSON reports,
   archives).

---

## 6. Building the paper PDF locally

```bash
cd paper
./build.sh --skip-figures
```

The build script writes `paper/main.pdf` (and a copy at
`paper/build/main.pdf`). It uses the bundled ACM class files
([`paper/acmart.cls`](paper/acmart.cls), etc.) so no internet access
is required.
