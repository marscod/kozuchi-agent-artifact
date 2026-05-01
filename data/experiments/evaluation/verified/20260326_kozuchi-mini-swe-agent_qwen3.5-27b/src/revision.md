# `analysis.md` revision log — v2

> Companion changelog to
> `experiments/evaluation/verified/20260326_kozuchi-mini-swe-agent_qwen3.5-27b/src/analysis.md`.
> This file enumerates *what is new in v2* relative to the prior
> v1 baseline so that a reviewer who already read v1 can locate
> exactly the parts that have changed.

| revision | scope | sections added / modified | new modules | new CSVs | new figures |
|---|---|---|---|---:|---:|
| **v1** | Headline result, leaderboard, per-repo / per-year, failure modes, patch structure, trajectory analysis, cross-experiment consensus, statistical robustness, operational cost. | §§1–10 (headline through operational), §11 *Reproducing*, §12 *Summary*. | `extract_metadata`, `extract_competitors`, `analyze_results`, `analyze_patches`, `analyze_trajectories`, `analyze_failures`, `analyze_competitors`, `analyze_qwen_vs_others`, `analyze_statistics`, `make_figures`. | 50 | 16 (`fig00_overview` through `fig15_pareto`) |
| **v2 / part A** *(TTS@8 candidate-level decomposition)* | **New §11** *"TTS@8 candidate-level decomposition: leg, oracle, selector, diversity"*. Old §11 → §12, old §12 → §13. | `analyze_tts.py`. | **+10** (`tts_*.csv`) | **+5** (`fig16`–`fig20`) |
| **v2 / part B** *(Conversation-level deep dive — this update)* | **New §12** *"Conversation-level deep dive: what is the agent actually saying?"*. Old §12 (now §13) and §13 (now §14) renumbered. Six new bullets (#16–#21) appended to the summary. | `analyze_conversations.py`. | **+12** (`conv_*.csv`) | **+5** (`fig21`–`fig25`) |
| **v2 totals** | 2 new sections (§11, §12), 2 renumbered (§13, §14), 1 introduction paragraph rewritten, 1 closing paragraph extended, 6 new summary bullets. | **+2 modules** (`analyze_tts.py`, `analyze_conversations.py`) | **+22** (10 + 12) | **+10** (5 + 5) |

The headline number, primary leaderboard, McNemar tests, paired
effect sizes, cluster bootstrap, logistic regression, Pareto
analysis, and every other v1 result are **unchanged**.  Every v2
addition is a *new* analysis layer that consumes data sources
(per-leg trajectory bundle and full per-message conversation
content) that v1 did not touch.

---

## v2 / Part A — TTS@8 candidate-level decomposition (§11, prior turn)

Adds a within-trajectory decomposition of the same TTS@8 stream
that v1 only summarised at the post-selector level.

### What is new in `analysis.md`

* **§11 (new, ~390 lines)** *"TTS@8 candidate-level decomposition:
  leg, oracle, selector, diversity"*.  Six sub-sections:
  * §11.1 — Per-leg pass rates and the leg-to-leg ensemble effect
    (table `tts_per_leg.csv`, fig `fig16_tts_per_leg.png`).
  * §11.2 — Oracle pass@k ceiling and selector position
    (`tts_pass_at_k_oracle.csv`, `fig17_pass_at_k.png`).
  * §11.3 — Selector regret and the bimodality of instance
    hardness (`tts_resolve_count_distribution.csv`,
    `fig18_tts_resolve_distribution.png`).
  * §11.4 — Patch diversity and the diversity → regret coupling
    (`tts_diversity_vs_outcome.csv`,
    `fig20_oracle_vs_selector.png`).
  * §11.5 — Inter-leg agreement and the source of selector
    head-room (`tts_leg_jaccard.csv`, `fig19_leg_jaccard.png`).
  * §11.6 — Take-aways for selector engineering.
* **Old §11 → new §13** (Reproducing the analysis), updated to
  list `analyze_tts.py` and the increased CSV / figure counts.
* **Old §12 → new §14** (Summary of key findings).  Three new
  bullets (#13–#15) covering single-leg pass-rate distribution,
  oracle pass@k, and bimodal scaffold-hardness; closing
  paragraph extended with the joint upper plausible envelope
  $74.8 + 6.8\,\text{(selector)} + 8.2\,\text{(scaffold)} +
  6.2\,\text{(backbone)} \approx 96 \%$.

### New code module — `src/analyze_tts.py`

* `LegReport` dataclass + `_load_leg_reports()` to scan all 8
  per-leg `runs/r0{1..8}_s100{1..8}/report.json` files.
* `_load_selector_picks()` reads the bundle's
  `simple_passrate_*_selected_labels.json` map.
* `_load_final_resolved()` re-aligns to the canonical
  `results/results.json`.
* `per_leg_table()` — Wilson-CI per-leg pass rates.
* `resolve_count_distribution()` — distribution of *r* (legs
  resolving an instance ∈ {0..8}).
* `pass_at_k_oracle()` — closed-form expected oracle pass@k.
* `selector_summary()` — head-line / attainable / best /
  oracle pass rates, regret, hit-rate, instance-category split,
  and the **corrected `merge_recovery = n_sel −
  sel_hits_attainable`** formulation (1 instance for this
  dataset, traced to a flaky-test re-evaluation in the merged
  harness pass).
* `selector_picks_table()` — per-leg selection share.
* `per_repo_oracle_vs_selector()` — per-repository oracle vs.
  selector pass rates.
* `patch_diversity_per_instance()` — unique-patch counts read
  from `xcheck/instance_test_tables/<instance_id>.json`.
* `diversity_vs_outcome()` — pass rate stratified by patch
  diversity.
* `leg_jaccard_matrix()` — pairwise Jaccard similarity of
  resolved sets across the 8 legs.

### New CSVs (10) under `src/csv/`

```
tts_per_leg.csv                       per-leg pass rate + Wilson CI
tts_resolve_count_distribution.csv    distribution of r ∈ {0..8}
tts_pass_at_k_oracle.csv              closed-form oracle pass@k
tts_oracle_summary.csv                selector vs. oracle headline
tts_selector_picks.csv                per-leg selection share
tts_per_repo_oracle_vs_selector.csv   per-repo regret table
tts_patch_diversity.csv               unique-patch counts per instance
tts_diversity_vs_outcome.csv          pass rate stratified by diversity
tts_leg_jaccard.csv                   8x8 leg agreement matrix
tts_per_instance_outcomes.csv         instance-level wide table
```

### New figures (5)

```
fig16_tts_per_leg.png                 per-leg pass rates with Wilson CI
fig17_pass_at_k.png                   oracle pass@k vs selector
fig18_tts_resolve_distribution.png    instance-hardness bimodality
fig19_leg_jaccard.png                 inter-leg agreement heatmap
fig20_oracle_vs_selector.png          per-repo oracle vs. selector
```

### New numerical claims grounded in §11

* **Per-leg pass rate**: 67.7 % mean (range 67.0 %–68.4 %); the
  selector's headline of **74.8 %** is **+7.0 pp** above the
  per-leg mean.
* **Oracle pass@8** = **81.6 %**; the selector achieves
  **74.8 %**, leaving a **6.8 pp** *attainable* selector regret
  inside the same compute envelope.
* **Selector ≅ oracle@2.19**: linear interpolation puts the
  selector's effective $k$ between 2 and 3 — i.e. the selector
  monetises only ~27 % of the 8-way candidate budget.
  ⇒ **~73 % of test-time-scaling compute is currently
  un-monetised**.
* **Bimodal scaffold-hardness**: 234 / 500 = 46.8 % of instances
  are solved by *all 8* legs; 92 / 500 = 18.4 % by *no* leg;
  only 174 / 500 = 34.8 % are *marginal* ($r \in [1, 7]$).
* **Single-leg vs. open-weight peers**: Kozuchi's 67.7 % single-
  leg pass-rate is competitive with `OpenHands + Qwen3-Coder-
  480B` (69.6 %, no TTS) and **+14 pp above any same-class
  30-32 B open-weight non-TTS peer** (Frogboss-32B,
  Skywork-SWE-32B, Devstral-Small).

### Auxiliary changes

* `src/utils.py` — added `TRAJ_BUNDLE_DIR` constant pointing to
  the unzipped bundle.
* `build.sh` — `analyze_tts.py` wired into `run_analysers()`;
  graceful skip if `TRAJ_BUNDLE_DIR` is absent.
* `make_figures.py` — five new `fig_tts_*` functions wired
  conditionally on `tts_per_leg.csv` existence.

---

## v2 / Part B — Conversation-level deep dive (§12, this update)

Adds an *intra-message* analysis of the agent's actual text and
tool stream that v1 (and v2 / part A) did not touch.  Built from
a single streaming pass over every
`trajs/<instance>.traj.json` (495 files, ~2.7 GB).

### What is new in `analysis.md`

* **§12 (new, ~510 lines)** *"Conversation-level deep dive: what
  is the agent actually saying?"*.  Nine sub-sections:
  * §12.1 — How long is the conversation? (turn / character
    distributions).
  * §12.2 — The 8x8 phase transition matrix (rigid forward
    flow + the single `VERIFY_PATCH → CODE_FIX` back-edge).
  * §12.3 — Bash tool-use fingerprint (top-30 verbs, 10
    functional categories).
  * §12.4 — Bash success rate and Python error markers.
  * §12.5 — THOUGHT vs. FINAL_ANSWER and the language of
    reflection.
  * §12.6 — Workflow-token economy (COMPLETE, HANDOVER,
    GIVEUP).
  * §12.7 — Outcome tests: Mann-Whitney U + Cliff's $\delta$
    + BH-FDR over ~90 conversation features.
  * §12.8 — Notable trajectories: four conversation case
    studies (`matplotlib-25122`, `django-13089`,
    `pylint-7080`, `sphinx-9367`).
  * §12.9 — Take-aways for conversation-level engineering.
* **Introduction paragraph rewritten** (lines 60–95 of
  `analysis.md`) to add a short pointer to §12 and the new
  fig21–fig25 panels next to the existing pointers to §11.
* **Old §12 → new §13** (Reproducing the analysis).  Code
  listing now also names `analyze_conversations.py`; the CSV
  count is bumped to **70+** and the figure count to **26**;
  the runtime line is updated to **~70 s** (the conversation
  pass is the dominant cost).
* **Old §13 → new §14** (Summary of key findings).  Six new
  bullets (#16–#21) appended:
  * #16 — conversation-level scale (median 556 messages,
    1.04 M chars).
  * #17 — phase scaffold rigidity (zero non-canonical
    transitions except the 1.0 % VERIFY_PATCH→CODE_FIX
    back-edge).
  * #18 — bash fingerprint solved (95.3 % rc=0; outcome-
    invariant verb mix).
  * #19 — outcome-asymmetric error grammar (`NameError` 9.3 ×
    more common in resolved).
  * #20 — `thought_action_ratio` is the **only** positive-
    direction trajectory feature.
  * #21 — verbal red-flag *"go back / back to / reverting"*
    (1.78 × more common in unresolved).
* **Closing paragraph extended** with a new sentence noting
  that §12 identifies the cheapest path to claim the lower
  half of the §11 selector head-room without re-training,
  re-scaffolding, or re-running candidates.

### New code module — `src/analyze_conversations.py` (865 LOC)

Single streaming pass over every assistant + user + system
message of every trajectory.  Extracts eleven feature families:

| family | description |
|---|---|
| F1 | per-message length distributions split by `role` and `phase` |
| F2 | THOUGHT vs. FINAL_ANSWER decomposition for every assistant turn |
| F3 | bash command verbs (top-30) and 10 functional categories |
| F4 | `<returncode>...</returncode>` success vs failure counts; output-size distribution |
| F5 | 13 Python error markers in tool-output content (`Traceback`, `AssertionError`, …) |
| F6 | workflow tokens (`Wn`, `COMPLETE`, `GIVEUP`, `HANDOVER`) per phase |
| F7 | empirical 8x8 phase transition matrix (overall, resolved, unresolved) |
| F8 | 11 reflective-language patterns ("let me try", "I expect", "go back", …) |
| F9 | `/_share/` heredoc memo writes |
| F10 | inter-assistant-turn timestamps (latency proxy) |
| F11 | top-N notable trajectories along 10 ranking dimensions |

Every numeric feature is also re-aggregated by outcome and tested
with Mann-Whitney U + Cliff's $\delta$ + BH-FDR adjustment.

### New CSVs (12) under `src/csv/`

```
conv_per_instance.csv               wide per-instance feature row (~90 cols)
conv_role_length_stats.csv          assistant/user/system length stats by outcome
conv_thought_action_stats.csv       THOUGHT / FINAL_ANSWER per phase × outcome
conv_phase_transition.csv           8x8 transition matrix (overall + by outcome)
conv_bash_verbs.csv                 top-30 verbs with conditional outcome shares
conv_bash_categories.csv            10 functional buckets aggregated
conv_returncode_per_instance.csv    rc = 0 / rc != 0 / failure rate per instance
conv_error_indicators.csv           13 Python error markers by outcome
conv_workflow_tokens.csv            COMPLETE / HANDOVER / GIVEUP frequencies
conv_reflection_markers.csv         11 reflective phrases by outcome
conv_outcome_tests.csv              MWU + Cliff's δ + BH-FDR over ~90 features
conv_interesting.csv                top-10 trajectories along 10 dimensions
```

### New figures (5)

```
fig21_conversation_lengths.png      length / bash-budget / shell-error rate (3 panels)
fig22_phase_transitions.png         8x8 phase transition heatmap with off-diagonal scale
fig23_bash_verbs.png                top-15 verb counts and per-outcome verb mix
fig24_error_indicators.png          13 error-marker means per outcome (forest)
fig25_thought_action.png            per-phase thought / action chars + ratio by outcome
```

### New numerical claims grounded in §12

| claim | value |
|---|---|
| total messages scanned | **318,672** (495 trajectories) |
| total bash calls scanned | **146,814** |
| median trajectory length | **556 messages** |
| median chars per trajectory (asst + user) | **~1.04 M** |
| dominant bash verb (`cat`) | **35.3 % of all calls** |
| `cat` + `nl` combined share | **43.6 %** |
| bash `rc = 0` rate | **95.3 %** (resolved 95.6 % vs unresolved 95.2 %) |
| GIVEUP coverage (≥ 1) | **18.8 %** of trajectories |
| only positive-Δ feature | `thought_action_ratio` (**Cliff's δ = +0.13**, $p = 0.028$) |
| BH-FDR survivors at $q < 0.05$ | 3 features, **all length features in CODE_LOCALIZE / ISSUE_REPRODUCT**, all negative Δ |
| `NameError` resolved : unresolved | **9.3 ×** (2.14 vs. 0.23 / instance) |
| `going_back` verbal red-flag | **1.78 ×** more common in unresolved (Cliff's δ = -0.18, $q = 0.056$) |

### Notable trajectories surfaced as case studies (§12.8)

| instance_id | n_msg | bash | giveups | err | rc≠0 | resolved | role |
|---|---:|---:|---:|---:|---:|:-:|---|
| `matplotlib__matplotlib-25122` | 1,957 | 883 | 12 | 95 | 1.9 % | yes | marathon recovery |
| `django__django-13089` | 1,775 | 805 | 10 | **1,630** | 3.4 % | no | drowning in tracebacks |
| `pylint-dev__pylint-7080` | 849 | 401 | 0 | 56 | 8.1 % | **yes** | globally-novel solve |
| `sphinx-doc__sphinx-9367` | 364 | 162 | 0 | 62 | 3.8 % | yes | shortest-win single-shot |

### Auxiliary changes

* `make_figures.py` — five new `fig_conv_*` functions wired
  conditionally on `conv_per_instance.csv` existence; figure
  count per run advertised as **26** when the conversation
  pass succeeded.
* `build.sh` — `analyze_conversations.py` wired into
  `run_analysers()` after `analyze_tts.py`; pipeline-comment
  block updated to advertise **70+ CSVs** and **26 PNGs**.

---

## Renumbering map (v1 → v2)

| v1 section | v2 section | change |
|---|---|---|
| §1–§10 | §1–§10 | unchanged |
| — | **§11 *(new)*** | TTS@8 candidate-level decomposition |
| — | **§12 *(new)*** | Conversation-level deep dive |
| §11 *Reproducing* | **§13 *Reproducing*** | renumbered + listing of two new modules + CSV/figure counts |
| §12 *Summary* | **§14 *Summary*** | renumbered + 9 new bullets (#13–#21) + extended closing paragraph |

---

## File-level diff overview

```
NEW   src/analyze_tts.py                  ~460 LOC, 10 CSV writers
NEW   src/analyze_conversations.py        ~865 LOC, 12 CSV writers
NEW   src/csv/tts_*.csv                   10 files, ~80 KB
NEW   src/csv/conv_*.csv                  12 files, ~3.5 MB (per-instance row dominates)
NEW   src/figures/fig16_tts_per_leg.png
NEW   src/figures/fig17_pass_at_k.png
NEW   src/figures/fig18_tts_resolve_distribution.png
NEW   src/figures/fig19_leg_jaccard.png
NEW   src/figures/fig20_oracle_vs_selector.png
NEW   src/figures/fig21_conversation_lengths.png
NEW   src/figures/fig22_phase_transitions.png
NEW   src/figures/fig23_bash_verbs.png
NEW   src/figures/fig24_error_indicators.png
NEW   src/figures/fig25_thought_action.png

EDIT  src/utils.py                        + TRAJ_BUNDLE_DIR constant
EDIT  src/make_figures.py                 + 5 fig_tts_* + 5 fig_conv_* + driver
EDIT  build.sh                            + analyze_tts + analyze_conversations
EDIT  src/analysis.md                     + §11 (~390 lines), + §12 (~510 lines),
                                          + 9 summary bullets, + intro/closing edits
```

---

## How to reproduce v2

```bash
cd experiments/evaluation/verified/20260326_kozuchi-mini-swe-agent_qwen3.5-27b
bash build.sh
```

`build.sh` rebuilds the local `uv` virtual environment, runs all
analysers in topological order, and writes:

```
src/csv/      <-- 70+ CSV tables  (50 v1 + 10 tts_*.csv + 12 conv_*.csv)
src/figures/  <-- 26 PNG figures  (16 v1 + 5 fig16-20 + 5 fig21-25)
```

Total wall-clock runtime end-to-end on a workstation with the
artifacts already cached is **~70 s**; the dominant cost is
the §12 streaming conversation pass over the 495 trajectory
JSONs (mean 5.7 MB, total ~2.7 GB).  The §11 analyser
additionally reads the unzipped 8-leg bundle under
`trajectories/q35_verified500_tts8_75p2_submission_bundle_*/`
(~22 GB on disk; only the per-leg `report.json` and
`xcheck/instance_test_tables/<instance>.json` files are loaded
— ~120 MB total — adding < 2 s).  Either auxiliary input is
treated as optional: `analyze_tts.py` skips gracefully if the
bundle is absent and `analyze_conversations.py` skips
gracefully if the trajectory directory is absent.

---

## Verification status (v2 build)

* `bash -n build.sh` &mdash; OK.
* `python src/analyze_tts.py` &mdash; OK; 10 CSVs written.
* `python src/analyze_conversations.py` &mdash; OK; 12 CSVs
  written; **495 trajectories scanned, 374 resolved, 121
  unresolved** (matches v1's 374-resolved headline).
* `python src/make_figures.py` &mdash; OK; **26 figures**
  written.
* `ReadLints` over `analyze_tts.py`, `analyze_conversations.py`,
  `make_figures.py`, `build.sh`, `analysis.md` &mdash; **no
  errors**.

All v2 prose claims have been re-validated against the
generated CSVs in a final sanity-check pass; numerical inputs to
prose (e.g. `n_messages` median 556, `cat` share 35.3 %,
`NameError` ratio 9.3 ×, `going_back` ratio 1.78 ×, oracle
pass@8 81.6 %, selector regret 6.8 pp) all match the
corresponding `*.csv` cells.

---

## How v2 changes the headline narrative

v1 produced a single closing claim: a **74.8 % pass rate**
benchmarked against open- and closed-weight peers, with a
~10–11 pp residual that no system in the comparator solved.

v2 reframes that claim as a **decomposition** of the gap to a
plausible upper envelope:

$$
\text{plausible-best} \;\approx\;
\underbrace{74.8 \%}_{\text{v1 headline}}
+ \underbrace{6.8\,\text{pp}}_{\text{§11 selector head-room}}
+ \underbrace{8.2\,\text{pp}}_{\text{§8 scaffold head-room (Qwen-blind-spot)}}
+ \underbrace{6.2\,\text{pp}}_{\text{§8 backbone head-room}}
\;\approx\; 96 \%
$$

with a **~4 % universal residual** that no system in our 11-peer
comparator solves and that no configuration constructible from
the current artifacts can recover.  §12 (this update) adds the
last operational refinement: of the §11 6.8 pp selector head-
room, the lower half is **directly addressable** by reading
content-level signals (THOUGHT : FINAL_ANSWER ratio, "go
back / reverting" red-flag, asymmetric error-marker grammar)
that the present weighted-pass-rate selector ignores entirely.
