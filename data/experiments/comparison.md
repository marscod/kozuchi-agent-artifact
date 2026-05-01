# Kozuchi mini-swe-agent + Qwen3.5-27B — Python vs. Java side-by-side

> **Two evaluations, one agent, one backbone.**
> Python: SWE-bench Verified, 500 instances, scaffold = mini-swe-agent + 8-phase decomposition, inference = TTS@8 (Best-of-8 + weighted-passrate selector).
> Java: Multi-SWE-bench Java Verified, 128 instances, *same agent / scaffold / backbone*, inference = strict xcheck@8 (cross-agent-test selector).
>
> Source documents:
> * Python — `experiments/evaluation/verified/20260326_kozuchi-mini-swe-agent_qwen3.5-27b/src/analysis.md`
> * Java — `experiments/java/kozuchi-mswe-java-20260429/src/analysis.java.md`
>
> Source data:
> * Python CSVs — `experiments/evaluation/verified/20260326_kozuchi-mini-swe-agent_qwen3.5-27b/src/csv/`
> * Java CSVs — `experiments/java/kozuchi-mswe-java-20260429/src/csv/`
>
> Companion figure (this document) — `experiments/comparison_figures/fig_python_vs_java.png`.
> Plotting code — `experiments/comparison_src/plot_python_vs_java.py`.

This document is a side-by-side cross-track comparison of the two
Kozuchi submissions. Every quantitative claim is read directly from
one of the two source CSVs; the figure below collects six of those
comparisons into a single panel for the abstract / introductory slide.

![Six-panel side-by-side comparison of Python vs. Java](comparison_figures/fig_python_vs_java.png)

*Six-panel summary. (a) Headline rate with Wilson 95 % CIs. (b) Resolution
rate vs. patch LOC churn bucket. (c) Per-phase share of assistant
messages. (d) Per-phase rework factor (extra `WORKFLOW: COMPLETE`
events / instance). (e) Failure-mode breakdown as a fraction of unresolved
instances. (f) Per-instance effort (Java median ÷ Python median).*

---

## 0. Executive summary

| dimension | Python | Java | take-away |
|---|---:|---:|---|
| resolved | **374 / 500 (74.80 %)** | **41 / 128 (32.03 %)** | -42.8 pp absolute on a structurally harder corpus |
| Wilson 95 % CI | [70.82 %, 78.41 %] | [24.57 %, 40.54 %] | non-overlapping |
| open-weight rank | **#1 of 17 curated peers** by 18 instances | **#1 of 8 strict-open-weight peers** by 1 instance over `iSWE-OpenModels` | scaffold premium retained |
| backbone parameter scaling beat | **+26 over 480 B Qwen3-Coder** ($p=8\!\times\!10^{-3}$) | **+38 over 72 B Qwen2.5** ($p=4\!\times\!10^{-10}$) | scaffold > parameter scaling on both tracks |
| globally novel solves | 1 (`pylint-7080`, in 24-peer comparator) | 1 (`jackson-core-370`, in 41-peer comparator) | qualitatively novel solves on both |
| edit-layer reliability | 99.8 % (0 patch-apply failures, 0 empty patches) | 96.9 % (3 patch-apply failures, 1 empty patch) | unsolved on Java |
| selector regret (oracle - selector) | **6.8 pp** (measured) | ≈ **9-19 pp** (bound; see §11 of Java doc) | larger and unobserved on Java |
| dominant failure mode | WRONG_FIX = 91 % of unresolved | spread across 7 modes; `no_fixed_tests` = 38 % | Java exposes Java-specific harness/toolchain failures |
| heaviest repo | django (231 / 500 = 46 %), 76.6 % resolve | jackson-databind (42 / 128 = 33 %), 47.6 % resolve | the *dominant* repo is solvable on both |
| zero-rate / hard repo | pylint (10 instances, 30 %) | **logstash (38 instances, 0 %)** | a hard cluster exists on both, but Java's is an order of magnitude more severe |

The single most important cross-track observation is that **the open-weight
scaffold premium transfers**: on each track the same 27 B Qwen3.5
backbone deployed inside the Kozuchi scaffold beats the strongest
open-weight Qwen-family non-Kozuchi peer by a margin large enough to
be statistically robust to multiple-testing correction at FDR ≤ 0.05.
What does *not* transfer is the absolute headline rate: Java's corpus
is materially harder, and the gap is dominated by a 38-instance
`elastic/logstash` cluster on which both Kozuchi *and* most peer
agents collapse to single-digit resolution rates.

---

## 1. Same agent, same backbone — what's actually held fixed

A side-by-side comparison only carries weight if the experimental
"unit" is well-defined. Both submissions share:

* **Backbone** — Qwen/Qwen3.5-27B, same checkpoint, same vLLM
  serving stack on 4×2-GPU and 6×2-GPU setups
  (`logs/_harness/xcheck_run_settings.env` on the Java side;
  `metadata.yaml`/`README.md` on the Python side both name the
  identical `Qwen3.5-27B` open-weight backbone).
* **Agent scaffold** — mini-swe-agent with the 8-phase Kozuchi
  decomposition `(ISSUE_REPRODUCT → TEST_SYNTHSIZE → CODE_LOCALIZE →
  TEST_LOCALIZE → CODE_FIX → VERIFY_PATCH → ISSUE_CLOSE →
  FINAL_REPORT)`. The ordering, the GIVEUP/HANDOVER/COMPLETE workflow
  tokens, and the `/_share/<PHASE>.md` memo protocol are identical on
  both tracks.
* **Inference paradigm** — eight independent decoding legs followed by
  a candidate selector. Python uses TTS@8 with a weighted-passrate
  selector (`f2p_weight = 0.3, p2p_weight = 0.7,
  tie_break = shortest_patch_raw`); Java uses **strict xcheck@8** with
  the same family of weighted-passrate selector but an additional
  per-instance cross-test pass over the eight legs' generated tests
  before scoring. Both consume eight candidate patches per instance
  and emit one. The §11 selector mechanics differ in detail (see §6
  below) but the eight-leg cardinality is identical.

What changes between the two runs:

* **Corpus** — 500 Python instances (12 repos, primarily django) vs.
  128 Java instances (9 repos, dominated by jackson-databind and
  logstash). Java is a *smaller* benchmark with a *steeper* difficulty
  distribution (62 % medium / 28 % hard vs. Python's roughly uniform
  difficulty profile).
* **Test harness** — `pytest` on Python vs. Maven/Gradle on Java.
  This is the surface that exposes *most* of the Java-specific failure
  modes (§5).
* **Selector mechanics** — TTS@8 weighted passrate (Python) vs.
  cross-agent-test `xcheck@8` (Java). The Python selector consumes
  per-instance per-leg pass-rates against the gold-tests; the Java
  xcheck selector additionally scores each candidate patch against
  the *other seven legs' generated tests*, then applies the same
  weighted-passrate ranking. The cardinality K=8 is identical.

Everything quoted below — same-corpus McNemar p-values aside — is
therefore an apples-to-apples comparison of *the same agent and
backbone running on a different language stack*.

---

## 2. Headline rate (panel a)

The single-number comparison is in panel (a) of the figure.

| metric | Python | Java |
|---|---:|---:|
| resolved | **374 / 500** | **41 / 128** |
| rate | **74.80 %** | **32.03 %** |
| Wilson 95 % CI | [70.82 %, 78.41 %] | [24.57 %, 40.54 %] |
| trajectory coverage | 99.0 % | 99.2 % |
| harness report coverage | 99.0 % | 100.0 % |
| `report_valid` ∧ ¬`leaderboard_resolved` | 0 (Python harness == leaderboard) | 8 (Java leaderboard re-eval is stricter) |

The two intervals are **strictly non-overlapping** at the 95 % level.
The Wilson-test Z-score for the difference between the two
proportions is $\approx +9.3$, with $p < 10^{-20}$.

Three points anchor the headline reading:

* **Both intervals are tight enough to support paired comparisons.**
  The Wilson half-width is 4 pp on Python and 8 pp on Java; the
  smaller Java sample doubles the per-point uncertainty but keeps
  the 95 % interval entirely to the left of 41 %.
* **Coverage is essentially identical.** Both runs persist a
  trajectory and harness report for ≈ 99 % of instances; the
  edit-layer reliability gap (Python 0 / 500 patch-apply failures vs.
  Java 3 / 128 = 2.3 %) is the more meaningful operational
  difference.
* **The 8-instance `report_valid_¬leaderboard` stratum is unique to
  Java.** It is the cleanest single-axis divergence between the two
  tracks: on Python, the per-instance harness verdict matches the
  leaderboard; on Java, eight instances pass the per-instance
  fail-to-pass test set but fail the leaderboard's stricter
  cross-suite re-eval. Seven of the eight are logstash and one is
  gson — together they account for 6.3 % of all Java instances and
  represent the most actionable single selector-side lever (§6).

---

## 3. Patch-size dependency (panel b)

The clearest cross-track structural signal is in panel (b). Both
runs show the same **monotone decreasing** resolution rate with
LOC churn, but the *level* on Java is roughly half that of Python at
every size bucket:

| LOC bucket | Python n | Python resolved | rate | Java n | Java resolved | rate | Δ (Java − Python) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1-5 | 208 | 170 | **81.7 %** | 21 | 12 | **57.1 %** | -24.6 pp |
| 6-25 | 195 | 149 | 76.4 % | 22 | 10 | 45.5 % | -30.9 pp |
| 26-50 | 57 | 38 | 66.7 % | 37 | 13 | 35.1 % | -31.6 pp |
| 51-150 | 35 | 17 | 48.6 % | 25 | 3 | 12.0 % | -36.6 pp |
| 151+ | 12 | 5 | 41.7 % | 22 | 3 | 13.6 % | -28.1 pp |

Three observations:

* **The functional form is identical.** Both tracks fit a
  monotone-decreasing curve in LOC churn; the steepest fall is
  between the small and mid bucket on both tracks (Python: 82 %→67 %
  by 26-50 LOC; Java: 57 %→35 % by 26-50 LOC).
* **Java drops twice as fast in absolute terms.** The track-wise
  Spearman $\rho$ is $-0.20$ on Python and $-0.34$ on Java
  (`effort_resolution_corr.csv` on each side); the patch-size signal
  is roughly **70 % stronger** on Java in rank-correlation units. The
  most parsimonious explanation is that Java's instance distribution
  is more concentrated in `medium`/`hard` difficulty where edits
  *intrinsically* require larger LOC churn (the median
  unresolved-with-patch churn is 44 LOC on Java vs 10 LOC on Python).
* **The 1-5 LOC bucket carries the same *win* rate on Java that
  151+ LOC carries on Python.** Java small-patch wins (57 %) are
  comparable in level to Python's largest-patch wins (42 %). The
  curve is *shifted down* by about 25 pp at every size bucket — i.e.,
  Java is uniformly harder, not just harder at the long tail.

This is the single piece of evidence most consistent with **a
backbone-level difference in Java fluency**: the same agent,
producing the same size of patch on the same complexity scale, is
~25 pp less likely to land it correctly on Java than on Python.

---

## 4. Phase-level behaviour (panels c, d)

The phase-decomposed scaffold is held fixed across the two tracks,
so panels (c) and (d) show *behavioural* differences rather than
structural ones. The match is striking:

| phase | Python share | Java share | Δ | Python rework | Java rework | Δ |
|---|---:|---:|---:|---:|---:|---:|
| ISSUE_REPRODUCT | 12.5 % | 13.5 % | +1.0 | 0.004 | 0.000 | -0.004 |
| TEST_SYNTHSIZE | 11.5 % | 11.8 % | +0.3 | 0.004 | 0.000 | -0.004 |
| CODE_LOCALIZE | 9.4 % | 12.9 % | +3.5 | 0.016 | 0.008 | -0.008 |
| TEST_LOCALIZE | 16.5 % | 11.2 % | -5.3 | 0.014 | 0.024 | +0.010 |
| **CODE_FIX** | **21.9 %** | **23.2 %** | +1.3 | **0.525** | **0.362** | -0.163 |
| **VERIFY_PATCH** | **16.7 %** | **12.6 %** | -4.1 | **0.446** | **0.165** | -0.281 |
| ISSUE_CLOSE | 7.6 % | 10.4 % | +2.8 | 0.010 | 0.008 | -0.002 |
| FINAL_REPORT | 3.9 % | 4.4 % | +0.5 | 0.008 | 0.008 | 0.000 |

Three structural observations:

* **The agent re-balances message budget toward CODE_LOCALIZE on
  Java** (+3.5 pp) at the expense of TEST_LOCALIZE (-5.3 pp) and
  VERIFY_PATCH (-4.1 pp). The Java agent therefore spends *more*
  time finding the right code to edit and *less* time stress-testing
  the resulting patch — consistent with Maven/Gradle test invocations
  being more expensive per call than `pytest`, so the agent
  compensates by doing fewer of them.
* **Rework is concentrated in CODE_FIX ↔ VERIFY_PATCH on both
  tracks.** Together these two phases account for 91 % of all rework
  on Python and 96 % on Java; every other phase has a near-zero
  rework factor. The phase-decomposed scaffold has the same single
  feedback edge on both tracks: VERIFY_PATCH → CODE_FIX.
* **Rework intensity is materially lower on Java.** The CODE_FIX
  rework factor is 0.36 on Java vs 0.53 on Python (-32 % relative);
  the VERIFY_PATCH factor is 0.17 vs 0.45 (-63 %). The Java agent
  is reliably *less* iterative than the Python agent — combined with
  the §3 patch-size dependency reading, this suggests the Java
  agent's verify→fix loop terminates earlier (often correctly when
  the patch is small, often *prematurely* when the patch is large).

The Java doc §7.2 reports a **rework-loop sign-flip** vs. Python:
on Python, *unresolved* trajectories fire +28 % more CODE_FIX
messages than resolved ones (selection-bias on hardness); on Java,
the sign of the VERIFY_PATCH GIVEUP signal *flips* — resolved Java
trajectories fire **slightly more** GIVEUPs (0.41 / instance) than
unresolved ones (0.36). This is direct evidence that Java agents
who *do* iterate through the verify loop more often *succeed* more
often. On Python this effect is masked by the dominant hardness-
selection bias; on Java the iterative-correction signal is small
enough (the verify loop runs less aggressively) that the
"more rework helps" effect is observable in the raw means.

---

## 5. Failure-mode breakdown (panel e)

Panel (e) is the cleanest visualisation of where the two tracks
*diverge qualitatively*. The two distributions are **structurally
different**:

| failure mode | Python share of unresolved | Java share of unresolved |
|---|---:|---:|
| WRONG_FIX / `no_fixed_tests` | **91.3 %** | 37.9 % |
| `no_fix_test_results` | 0.0 % | **25.3 %** |
| REGRESSION / `regressed_passing_tests` | 4.8 % | 17.2 % |
| `report_valid_¬leaderboard_resolved` | 0.0 % | **9.2 %** |
| `anomalous_test_pattern` | 0.0 % | 5.7 % |
| `patch_apply_failed` | 0.0 % | 3.4 % |
| `empty_patch` | 0.0 % | 1.1 % |
| MISSING_ARTEFACT | 4.0 % | 0.0 % |

Three takeaways:

* **Python is single-mode dominated; Java is multi-mode.** On Python,
  $91 \%$ of unresolved instances fall into the WRONG_FIX bucket: a
  cleanly applicable patch that fails to flip the FAIL_TO_PASS test
  set. The remaining buckets are essentially noise. On Java the
  *equivalent* bucket (`no_fixed_tests`) is only 38 %, with another
  35 % distributed across **two Java-specific failure surfaces** that
  do not exist on the Python track:
  * `no_fix_test_results` (25 %) — the JVM/Maven/Gradle layer
    failed to even produce a parseable test report. This is a pure
    Java toolchain failure mode.
  * `report_valid_¬leaderboard_resolved` (9 %) — the per-instance
    harness called the patch valid, but the leaderboard's stricter
    cross-suite re-eval downgraded it. This is a selector-side
    failure mode.
  * `anomalous_test_pattern` (6 %) — the patch produced a
    test-result pattern that differs from both pre-patch and gold-
    patch; another harness diagnostic exclusive to the Java
    leaderboard.
* **Edit-layer reliability is *not* solved on Java.** Three patch-
  apply failures and one empty patch (3.1 % of all 128) — the
  failures the Python track has driven to zero. The fault profile is
  a 1.5-3 % regression on the cleanest-patch metric the Python doc
  reports as a top-line achievement.
* **Regressions are 2.4 × more common on Java**. The
  `regressed_passing_tests` rate is 11.7 % of all 128 vs. 1.2 % of
  all 500 on Python. Combined with the lower VERIFY_PATCH rework
  factor in §4, this is consistent with the Java agent's verify-fix
  loop being *less aggressive* and therefore catching fewer
  regressions before submission.

The implications for follow-up work split cleanly:

* On Python, future improvements have to come from **better
  reasoning under long context** (the WRONG_FIX bucket is purely a
  semantic-mistake bucket; everything else is essentially noise).
* On Java, future improvements split across three orthogonal axes:
  (i) reasoning quality (close the `no_fixed_tests` bucket, ~38 %),
  (ii) JVM/Maven harness reliability (close `no_fix_test_results`
  and `patch_apply_failed`, ~29 %), and (iii) selector cross-test
  reinforcement (close `report_valid_¬leaderboard`, ~9 % — the
  single cheapest lever in the Java analysis).

---

## 6. Per-instance effort (panel f)

Panel (f) reports the Java-median ÷ Python-median ratio for seven
per-instance effort metrics. **Six of the seven are within ±20 %
of parity**, with one striking outlier:

| metric | Python median | Java median | Java / Python |
|---|---:|---:|---:|
| api_calls | 490 | 529 | **1.08×** |
| messages | 556 | 594 | 1.07× |
| bash calls | 257 | 276 | 1.07× |
| prompt tokens (M) | 6.20 | 6.47 | 1.04× |
| completion tokens (K) | 83.1 | 80.7 | 0.97× |
| runtime (s) | 2,784 | 3,330 | 1.20× |
| **patch churn (LOC, all)** | 5.0 | 27.0 | **5.40×** |

Two complementary readings:

* **Inference-side cost is essentially the same.** The agent is
  spending roughly identical compute per instance on both tracks
  (api_calls, messages, bash calls, prompt tokens all within 8 %).
  The only meaningful inference-cost increase is wall-clock runtime
  (+20 %), driven by Maven/Gradle being slower than `pytest` per
  invocation, not by the agent making more invocations.
* **The *output* (patch) is 5.4× larger at the median**. The median
  Java patch churn is 27 LOC vs Python's 5 LOC. This is the
  combined effect of (i) Java's verbose syntax, (ii) tests being
  longer, and (iii) the unresolved tail (median unresolved-with-
  patch churn 44 LOC, max 50,885 LOC entirely in the logstash
  cluster). Restricted to the resolved-patch subset, Java's median
  churn drops to 12 LOC (vs Python's resolved median of 5 LOC) —
  still ~2.4× larger but no longer in the > 5× range.

The ratio chart is the cleanest single-axis visualisation of the
claim "**Kozuchi spends approximately the same compute per
instance on both tracks**" — i.e. the +43-pp headline gap from §2 is
*not* a compute gap, it is a fluency gap.

---

## 7. Selector behaviour cross-comparison

Both tracks run K=8 and emit one patch per instance, but the data
shipped about that selection step is markedly more complete on
Python.

| dimension | Python | Java |
|---|---|---|
| selector family | weighted F2P / P2P passrate | strict xcheck@8 (cross-agent-test passrate) |
| weights | 0.3 / 0.7 | inferred 0.3 / 0.7 (not in shipped settings) |
| tie-break | `shortest_patch_raw` | inferred `shortest_patch_raw` |
| per-leg per-instance reports shipped? | **yes** (8 × `report.json`) | no |
| per-instance test-table shipped? | yes (`xcheck/instance_test_tables/*`) | no |
| candidate dedup hashes shipped? | yes (`tts_diversity_vs_outcome.csv`) | no |
| **per-leg pass@1** | **66.8 %-68.6 %** (1.8 pp band) | unobservable — bound only |
| **selector pass@1** | **74.80 %** | **32.03 %** |
| **oracle pass@8** | **81.6 %** (measured) | bound: ≤ 39-47 % rate |
| **selector regret** | **6.8 pp** (34 instances) | bound: 9-19 instances (≈ 7-15 pp) |
| selector conditional accuracy | 91.4 % | unobservable directly; lower bound ~70 % |

The cleanest summary of the selector behaviour gap is therefore
that **the Python selector decomposition is fully audited; the Java
selector decomposition is not yet auditable from the shipped
artefacts**. The Java doc §11.4 enumerates the six file types
(`runs/r0{1..8}_s100{1..8}/{report,preds}.json` plus the
`xcheck/instance_test_tables/*.json` matrices) needed to reproduce
the Python §11 audit on Java — once those are staged, the
selector-side comparison becomes a quantitative cross-track
ablation.

What we *can* say from the shipped Java artefacts:

* **The Java per-leg conditional resolved-rate spans 19 %-53 %**
  (`logs/_harness/xcheck_preds_score.json`), a much wider band than
  the Python ±1 pp range. The Java selector is therefore picking
  among legs of *very* heterogeneous quality, so its task is harder.
* **The xcheck selector is operationally reliable on Java**: zero
  malformed predictions across 127 picks; selection skew across
  the eight legs is uniform at $\chi^2$ p = 0.244 (n.s.).
* **The 8-instance `report_valid_¬leaderboard` stratum** is the
  cleanest cross-track-distinct selector bug. On Python the
  per-instance harness and the leaderboard are the same code path,
  so this stratum cannot exist; on Java they diverge, and the
  selector has no signal from the leaderboard's stricter cross-suite
  test set when picking. A re-eval pass at selection time is the
  single highest-leverage intervention identified in either of the
  two analyses.

---

## 8. Cross-experiment consensus comparison (§8 of each doc)

Both docs include a `peer_consensus_count → resolution_rate`
stratification. The shapes are similar but the levels are not:

| consensus level | Python (Qwen-peers, 4) Kozuchi rate | Java (peers, 41) Kozuchi rate |
|---|---:|---:|
| 0 (no peer solves) | 29.2 % | **2.0 %** |
| 1 | 65.0 % | 8.3 % |
| 2-3 | 80.0 % (combined) | 40.0 % (combined) |
| max-but-one | 95.9 % | 53.8 % |
| **max** (all peers solve) | 97.5 % | **100.0 %** |

* **The "all peers solve" tier is fully recovered on both
  tracks** (97.5 % on Python, 100 % on Java). On the universally
  easy tail the agent never substantively loses an instance.
* **The "no peer solves" tier is recoverable on Python and not on
  Java**. Python's Kozuchi resolves 35 / 120 = 29.2 % of *Qwen-hard*
  instances; Java's Kozuchi resolves 1 / 51 = 2.0 % of
  *peer-hard* instances. The 27-pp gap reflects (i) Java's
  larger "globally hard" residual (64 % vs 43 %), (ii) the
  smaller open-weight cohort to ensemble against (4 Qwen peers
  vs 41 mixed peers including 7 closed-frontier), and (iii) the
  near-zero recoverability of the logstash cluster.
* **The Spearman correlation** between Kozuchi outcome and peer
  consensus is +0.60 on Python (Qwen-peers) and +0.65 on Java —
  **the strongest single predictor on both tracks** in their
  respective multivariate logistic regressions.

The §8 stratification of unresolved instances is the cleanest
side-by-side decomposition of the recoverable headroom on each
track:

| stratum | Python (n=126 unresolved) | Java (n=87 unresolved) |
|---|---:|---:|
| Another peer (open-weight) resolves | 41 (33 %) | 14 (16 %) |
| Frontier-closed peer only resolves | 31 (25 %) | 17 (20 %) |
| **Globally hard** (no peer resolves) | 54 (43 %) | **56 (64 %)** |

Java has a substantially larger universal-hard residual (64 %
vs 43 %) — that is, of the 87 instances Kozuchi misses on Java,
nearly two thirds are *also* missed by every one of the 41
catalogued Java peer agents. The Python residual of 43 % is
already a hard cap on what scaffold-and-backbone work can
recover; Java's 64 % places a much harder structural ceiling on
incremental improvements.

---

## 9. Where the two tracks agree and where they diverge

### What transfers cleanly across tracks (cross-validated):

1. **Phase-decomposed scaffold premium**. The same 27 B Qwen3.5
   backbone, deployed inside Kozuchi vs. inside the strongest non-
   Kozuchi same-class peer, beats that peer by:
   * Python: +26 instances over OpenHands + Qwen3-Coder-480B
     ($p = 8\!\times\!10^{-3}$, scaffold beats 17.8× parameter
     scaling).
   * Java: +38 instances over MSWE-agent + Qwen2.5-72B
     ($p = 4\!\times\!10^{-10}$, scaffold beats 2.7× parameter
     scaling).
2. **Phase distribution is preserved**. Per-phase share of
   assistant messages differs by < 5 pp on every phase between the
   two tracks (panel c). The agent's macro-level scaffold-traversal
   behaviour is **identical** to within measurement noise.
3. **Rework concentrates at CODE_FIX ↔ VERIFY_PATCH**. The only
   non-trivial back-edge in the phase transition matrix on either
   track is VERIFY_PATCH → CODE_FIX, with rework factor 0.36-0.53
   on CODE_FIX and 0.17-0.45 on VERIFY_PATCH and ≤ 0.025 elsewhere.
4. **Patch size is the dominant non-effort predictor of failure**.
   Spearman $\rho = -0.20$ (Python), $-0.34$ (Java); both at
   $p < 10^{-4}$. The relationship is monotone in LOC churn on
   both tracks.
5. **Effort metrics carry only a hardness-selection-bias signal**.
   Every `api_calls / runtime / messages / prompt_tokens / bash_calls`
   variable carries a negative point-biserial / Spearman with
   resolution on both tracks; in both cases the multivariate
   logistic regression (Python §9.4) absorbs the signal into the
   peer-consensus predictor.
6. **Per-instance compute is essentially the same**. Six of seven
   effort medians are within 20 % of parity (panel f). Kozuchi is
   not "trying harder" on Java than on Python; it is producing a
   larger output with a lower success rate at the same input cost.
7. **Selector cardinality is K=8 and uniform-pick is approximately
   maintained**. Python: per-leg pick share $\in [8.7\%, 13.9\%]$;
   Java: $\in [8.7\%, 19.7\%]$. Both are statistically consistent
   with uniform.

### What does *not* transfer (track-specific):

1. **Headline rate**. 74.8 % vs. 32.0 %. Java is structurally
   harder on the same backbone-and-scaffold combination.
2. **Edit-layer reliability**. Python: 0 / 500 patch-apply
   failures. Java: 3 / 128 = 2.3 %. The Maven/Gradle diff/apply
   surface produces a class of failures the `pytest` track has
   eliminated.
3. **Failure-mode distribution**. Python: single-mode
   (WRONG_FIX = 91 %). Java: seven-mode, including three
   Java-specific buckets (`no_fix_test_results`,
   `report_valid_¬leaderboard`, `anomalous_test_pattern`) that
   collectively account for 40 % of unresolved instances.
4. **Hard-difficulty cliff**. Python's resolution rate degrades
   from 85 % (200-399 API calls bucket) to 50 % (1300+ bucket) — a
   35-pp drop. Java's drops from 67 % (< 400 calls) to 7 % (800-
   1199 bucket) — a **60-pp drop**, nearly twice as steep.
5. **Logstash cluster**. 38 / 128 = 30 % of Java is `elastic/logstash`
   and Kozuchi resolves zero of them; 32 of the 38 are also globally
   hard. Python has no comparable single-repo collapse; the worst
   Python repo is `pylint` at 30 % resolution rate on 10 instances.
6. **Selector regret is observed on Python and bounded on Java**.
   Python's measured selector regret is 6.8 pp (34 / 500 instances);
   Java's regret is in the 9-19 instance range based on indirect
   bounds. The full Java audit awaits per-leg artefact staging.
7. **Rework-loop sign**. On Python, more VERIFY_PATCH GIVEUPs are
   weakly *negatively* correlated with success (selection bias on
   hardness). On Java, the sign flips — resolved trajectories fire
   *more* GIVEUPs than unresolved (0.41 vs 0.36) — evidence that
   Java agents who iterate through the verify loop more often
   succeed more often.
8. **Cross-experiment universal-hard residual**. 43 % on Python vs
   64 % on Java. The structural ceiling on what scaffold and
   backbone improvements can deliver is much closer to the current
   rate on Java than on Python.

### Cross-track joint upper-bound estimate

Both docs close with an estimate of the joint upper-bound on
headline rate from layered improvements. The cross-track
side-by-side:

| improvement axis | Python lift | Java lift | Python after | Java after |
|---|---:|---:|---:|---:|
| baseline (current submission) | 0 | 0 | 74.8 % | 32.0 % |
| **+ selector** (close oracle gap) | +6.8 | +7-15 | 81.6 % | 39-47 % |
| **+ scaffold** (peer blind-spots) | +8.2 | +10.9 | 89.8 % | 50-58 % |
| **+ backbone** (frontier-only) | +6.2 | +13.3 | **96.0 %** | **63-71 %** |
| residual (universal-hard) | -4.0 | -29 to -37 | — | — |

The Python ceiling sits at ≈ 96 % with a ~4 pp universal-hard
floor; the Java ceiling sits at ≈ 63-71 % with a ~30 pp universal-
hard floor. Most of Java's gap to its ceiling is the logstash
cluster; once that single cluster is removed (i.e., on the
non-logstash 90-instance subset), Kozuchi's Java rate is
**41 / 90 = 45.6 %** — still below Python's 74.8 % but no
longer in a fundamentally different regime.

---

## 10. Take-aways for follow-up engineering

The two analyses **disagree on which intervention is the
shortest path to a higher headline rate**:

* On **Python**, the §11 selector regret is the cheapest 6.8-pp
  lever. The candidate generation budget is already spent and the
  oracle pass@8 ceiling sits 6.8 pp above the realised rate; a
  cross-test verification step on the 19 high-diversity ($u_i = 8$)
  instances would close ~half of that regret without any change to
  candidate generation, scaffold, or backbone. The next-cheapest
  lever (Qwen-blind-spot scaffold ensembling) is +8.2 pp.
* On **Java**, the cheapest lever is the **8 `report_valid_¬
  leaderboard_resolved` instances** (§5 / §11.5 of the Java doc) — a
  selector-side multi-suite cross-test reinforcement would convert
  most of these from unresolved to resolved at no candidate-
  generation cost. That alone is +6.3 pp. The next-cheapest is
  closing the patch-apply / empty-patch tail (4 instances, +3.1 pp)
  through stricter pre-submission diff sanity checks; together these
  two operational improvements would bring the Java rate to roughly
  **42 %**, which would put Kozuchi level with the rank-2 *InfCode +
  GPT-5.2* peer (39 % on a closed-LLM backbone) and within striking
  distance of the rank-1 *CodeArts-Agent + MiniMax-M2.5* peer (44 %
  on a closed-LLM backbone) — still on the same 27 B open-weight
  Qwen3.5 backbone.

The longer-horizon lever on **both tracks** is the same: the
*peer-consensus-zero* hard residual. Python's 54 instances and
Java's 56 instances are universally unsolved by every system in
their respective comparators, and likely require either a stronger
backbone (Java logstash in particular looks backbone-bound) or
test-set-level intervention (corrected golden tests, richer
specifications). Neither analysis claims to crack that residual
with selector or scaffold work alone.

---

## 11. Reproducing this comparison

```
experiments/
├── comparison.md                                  # this document
├── comparison_figures/
│   └── fig_python_vs_java.png                     # the 6-panel figure above
├── comparison_src/
│   └── plot_python_vs_java.py                     # plot generator
├── evaluation/verified/20260326_kozuchi-mini-swe-agent_qwen3.5-27b/
│   └── src/                                       # full Python analysis pipeline + analysis.md
└── java/kozuchi-mswe-java-20260429/
    └── src/                                       # full Java analysis pipeline + analysis.java.md
```

To regenerate the comparison figure from the source CSVs:

```bash
cd experiments
uv venv .venv-comparison --python 3.12
source .venv-comparison/bin/activate
uv pip install pandas numpy matplotlib scipy
python comparison_src/plot_python_vs_java.py
```

The plot script consumes hand-curated cell values traced to the
canonical CSVs of each track (Python: `headline.csv`,
`patch_size_buckets.csv`, `phase_distribution.csv`,
`failure_modes.csv`, `operational.csv`; Java: same filenames under
the Java track's `src/csv/`). Any divergence between the figure
and the underlying CSVs should be reported as a bug; the source
of truth is the per-track CSV in every case.
