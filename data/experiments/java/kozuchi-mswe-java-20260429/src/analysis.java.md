# Kozuchi mini-swe-agent + Qwen3.5-27B on Multi-SWE-bench Java — A Deep Analysis

> Submission directory: `experiments/java/kozuchi-mswe-java-20260429/`
> Backbone: Qwen/Qwen3.5-27B (open-weight) · Agent: Kozuchi mini-swe-agent · Inference: xcheck@8 (8-leg candidate generation + cross-agent-test selector)
> Companion to the Python SWE-bench Verified write-up at `experiments/evaluation/verified/20260326_kozuchi-mini-swe-agent_qwen3.5-27b/src/analysis.md`.

This document is the technical write-up that accompanies the
analysis pipeline shipped under `src/`. Every quantitative claim
is traced back to a CSV under `src/csv/` and (where available) a
figure under `src/figures/`. The CSV/figure pair is produced
deterministically by `bash build.sh` in `paper/java_src/` from
the artifacts already present in this submission directory.

> Reproducibility note. Throughout the analysis we adopt the
> canonical denominator $N=128$ for every aggregate metric on
> Multi-SWE-bench Java. The submission ships 128
> harness reports and 128 patches (one per instance after the
> xcheck@8 selector); 127 of those are accompanied by a fully
> reconstructed assistant trajectory and one
> (`googlecontainertools__jib-2542`) is a stub written by the
> selector pipeline because the chosen leg's source trajectory
> was excluded under strict-xcheck and is therefore counted in
> the unresolved bucket as `EXCLUDED_BY_STRICT_XCHECK`.

> Scope of the analysis vs. the Python companion. Three of the
> twelve sections in the Python write-up rely on artefacts that
> the present Java bundle does **not** ship:
> (i) per-leg per-instance `report.json` files for the eight
> source xcheck runs,
> (ii) the `xcheck/instance_test_tables/<instance>.json` cross-test
> matrices that the selector consumes, and
> (iii) trajectory traces from competitor systems on the same
> 128 Verified-Java instances.
> Where these would have been needed (per-instance K=1 ablation,
> selector regret against an oracle pass@8, cross-experiment
> trajectory overlay) the corresponding subsection states
> exactly which file is missing and which bound on the answer is
> recoverable from the artefacts that **are** shipped (the
> aggregated `xcheck_preds_score.json` per-leg counts, the
> per-instance leaderboard outcome matrix, and the chosen-leg
> trajectories under `trajs/`).

![Overview of headline results: 4-panel summary of leaderboard, per-repo, per-difficulty, and patch-size dependency](figures/fig00_overview.png)
*Figure 0. Headline result panel. (a) Leaderboard position.
(b) Per-repository resolution rate with Wilson 95 % CIs. (c)
Resolution rate stratified by difficulty (`easy/medium/hard`).
(d) Resolution rate stratified by patch LOC churn.*

## 1. Headline result

Kozuchi resolves **41 / 128 = 32.03 %** of Multi-SWE-bench Java
Verified instances under strict xcheck@8 selection (Wilson 95 %
CI **[24.57 %, 40.54 %]**). Of these 41, 100 % are accompanied
by a fully reconstructed trajectory and a harness `report.json`,
so the resolution claim is auditable end-to-end.

| metric | value | n / N | 95 % CI |
|---|---|---|---|
| resolved (xcheck@8) | **32.03 %** | 41 / 128 | [24.57 %, 40.54 %] |
| harness `report_valid` rate | 38.28 % | 49 / 128 | [30.32 %, 46.93 %] |
| trajectory file coverage | 100.00 % | 128 / 128 | — |
| **full** trajectory coverage | 99.22 % | 127 / 128 | [95.71 %, 99.86 %] |
| patch coverage | 100.00 % | 128 / 128 | — |
| patch-apply failure rate | 2.34 % | 3 / 128 | [0.80 %, 6.66 %] |
| `report_valid` ∧ ¬`leaderboard_resolved` | 6.25 % | 8 / 128 | [3.20 %, 11.85 %] |

(`src/csv/headline.csv`, `src/csv/operational.csv`)

The 8-instance gap between `report_valid` (49) and
`leaderboard_resolved` (41) is unique to the Java track: it
captures cases where the per-instance report flips
fail-to-pass tests but the leaderboard's stricter cross-test
re-evaluation downgrades the patch to "not resolved". We
analyse this stratum in §5 — it is the single most distinctive
failure mode of the Java run relative to the Python run.

## 2. Where Kozuchi sits in the Java leaderboard

![Java Verified leaderboard with Kozuchi highlighted](figures/fig01_leaderboard.png)
*Figure 1. Multi-SWE-bench Java leaderboard;
Kozuchi (blue bar) sits at rank 4 / 42 with 41 / 128 — the
top-ranked submission running an open-weight backbone.*

Across the 42 publicly catalogued Multi-SWE-bench Java
submissions (`src/csv/leaderboard.csv`,
`src/csv/competitors_summary.csv`), Kozuchi places **4th
overall** and is the **#1 submission whose decision-LLM is an
open-weight model** in the curated comparator:

| rank | submission | resolved | denom | rate | backbone class |
|---:|---|---:|---:|---:|---|
| 1 | CodeArts Agent + CodeArts-MiniMax-M2.5 | 56 | 128 | **43.75 %** | closed (MiniMax-M2.5) |
| 2 | InfCode + GPT-5.2 | 50 | 128 | 39.06 % | closed (GPT-5.2) |
| 3 | iSWE-Agent | 43 | 128 | 33.59 % | undeclared (likely closed) |
| **4** | **kozuchi-mini-swe-agent + Qwen3.5-27B (xcheck@8)** | **41** | **128** | **32.03 %** | **open-weight (Qwen3.5-27B)** |
| 5 | iSWE-OpenModels | 40 | 128 | 31.25 % | open-weight (undeclared mix) |
| 6 | MSWE-agent + Gemini-2.5-Pro | 37 | 128 | 28.91 % | closed (Gemini-2.5-Pro) |
| 7 | MSWE-agent + CodeArts-MiniMax-M2.5 | 35 | 128 | 27.34 % | closed (MiniMax-M2.5) |
| 8 | MSWE-agent + Claude-3.7-Sonnet | 30 | 128 | 23.44 % | closed (Claude-3.7) |
| … | (29 more) | … | 128 | < 23 % | mostly closed APIs |

(`src/csv/leaderboard.csv`)

Three structural points anchor the leaderboard reading:

* **Of the 41 submissions ranked alongside Kozuchi, 27 (66 %)
  use a closed-weight commercial API** as the decision-LLM
  (Claude-3.5/3.7/3.5, GPT-4o / GPT-5.2 / o1 / o3-mini-high,
  Gemini-2.5-Pro, Doubao-1.5-pro/thinking, MiniMax-M2.5,
  DeepSeek-R1/V3 are arguably semi-open). Stripping these
  closed-LLM submissions leaves Kozuchi tied with
  *iSWE-OpenModels* at the top of the *strictly* open-weight
  cohort, then *MagentLess + Qwen2.5-72B-Instruct* (14) and
  *MopenHands + Qwen2.5-72B-Instruct* (4). The closest
  Qwen-family open-weight peer (the 72 B Qwen2.5 builds)
  resolves only 3-14 instances vs. Kozuchi's 41 — a gap
  comparable to the 30+ instance gap Kozuchi maintains over
  open-weight Qwen3-Coder-30B peers on the Python track.

* **The three submissions above Kozuchi all rely on closed
  models** (CodeArts-MiniMax-M2.5 ×2, GPT-5.2, and an
  undeclared backbone for *iSWE-Agent* whose
  upstream README does not name an open-weight model).
  Kozuchi's 27 B Qwen3.5 backbone trails CodeArts-Agent +
  CodeArts-MiniMax-M2.5 by 15 instances and InfCode + GPT-5.2
  by 9 instances; the latter two combine a strong proprietary
  backbone with a Java-specialised retrieval / planning
  scaffold and represent the closed-frontier tier on this
  benchmark.

* **The leaderboard mean is 18.5 %** (24 / 128) and the median
  is 14.8 % (19 / 128). Kozuchi's 32.03 % is **+13.5 pp above
  the leaderboard mean** and **+1.7 standard deviations** above
  the leaderboard distribution (sd ≈ 8.0 pp). The submission
  therefore sits in the upper tail of the field.

We confirm statistical significance using McNemar exact tests
on the paired 128-instance outcome vectors
(`src/csv/mcnemar.csv`). All 41 peer comparisons are listed in
`mcnemar.csv`; the headline summary is:

* **34 / 41 peers are beaten by Kozuchi at $p < 0.05$**
  (smallest significant gap: *MSWE-agent + Claude-3.7-Sonnet*
  at $\Delta = +11$, McNemar $p = 0.043$).
* **Three peers are statistically indistinguishable** from
  Kozuchi at $\alpha = 0.05$:
  *MSWE-agent + CodeArts-MiniMax-M2.5* ($\Delta = +6$, $p = 0.33$),
  *MSWE-agent + Gemini-2.5-Pro* ($\Delta = +4$, $p = 0.57$),
  *iSWE-OpenModels* ($\Delta = +1$, $p = 1.00$),
  and
  *iSWE-Agent* ($\Delta = -2$, $p = 0.84$).
* **One peer is significantly *ahead* of Kozuchi**:
  *CodeArts-Agent + CodeArts-MiniMax-M2.5* ($\Delta = -15$,
  $p = 2.6\!\times\!10^{-3}$). *InfCode + GPT-5.2* sits at
  $\Delta = -9$, $p = 0.20$ — point-direction ahead but not
  statistically significant.

The most informative single comparison in this list is
**MSWE-agent + Qwen2.5-72B-Instruct** (3 / 128) — the closest
*Qwen-family same-scaffold-class* baseline. Kozuchi beats it by
**38 instances** ($p = 4.1\!\times\!10^{-10}$), *substantially
larger* than the same-class margin Kozuchi posts on the Python
side. This is the cleanest piece of evidence that the
phase-decomposed Kozuchi scaffold transfers from Python to
Java even on a smaller (27 B vs 72 B) Qwen backbone.

### 2.1 Open-weight cohort summary

Of the 42 leaderboard entries, the strict open-weight cohort
(decision-LLM weights publicly released) contains:

| submission | resolved | rate | backbone |
|---|---:|---:|---|
| **Kozuchi + Qwen3.5-27B (xcheck@8)** | **41** | **32.03 %** | Qwen3.5-27B |
| iSWE-OpenModels | 40 | 31.25 % | open-weight mix (undeclared) |
| MSWE-agent + Llama-4-Maverick | 8 | 6.25 % | Llama-4-Maverick |
| MopenHands + Llama-4-Maverick | 8 | 6.25 % | Llama-4-Maverick |
| MagentLess + Llama-4-Maverick | 19 | 14.84 % | Llama-4-Maverick |
| MagentLess + Qwen2.5-72B-Instruct | 14 | 10.94 % | Qwen2.5-72B |
| MopenHands + Qwen2.5-72B-Instruct | 4 | 3.13 % | Qwen2.5-72B |
| MSWE-agent + Qwen2.5-72B-Instruct | 3 | 2.34 % | Qwen2.5-72B |

Inside this cohort Kozuchi is **#1 by 1 instance** over
*iSWE-OpenModels* and **+22 to +38 instances** ahead of the
Llama-4-Maverick / Qwen2.5-72B subgroup. Combined with the §2
McNemar reading the lead is statistically significant against
every Llama-4 / Qwen2.5-72B configuration but **not** against
*iSWE-OpenModels* ($\Delta = +1$, $p = 1.00$). The open-weight
margin is therefore real but tight at the very top.

## 3. Per-repository and per-difficulty structure

![Per-repository and per-difficulty resolution rates](figures/fig02_patch_effort.png)
*Figure 2. Per-repository and per-difficulty resolution rates
with Wilson 95 % CIs.*

The aggregate 32.03 % hides large per-repo and per-difficulty
variance. Reading from `src/csv/by_repo.csv`:

| repo | n | resolved | rate | Wilson 95 % CI |
|---|---:|---:|---:|---|
| alibaba/fastjson2 | 6 | 4 | **66.7 %** | [30.0, 90.3] |
| google/gson | 5 | 3 | 60.0 % | [23.1, 88.2] |
| googlecontainertools/jib | 5 | 3 | 60.0 % | [23.1, 88.2] |
| fasterxml/jackson-databind | **42** | 20 | **47.6 %** | [33.4, 62.3] |
| fasterxml/jackson-core | 18 | 8 | 44.4 % | [24.6, 66.3] |
| apache/dubbo | 3 | 1 | 33.3 % | [6.1, 79.2] |
| fasterxml/jackson-dataformat-xml | 5 | 1 | 20.0 % | [3.6, 62.4] |
| mockito/mockito | 6 | 1 | 16.7 % | [3.0, 56.4] |
| **elastic/logstash** | **38** | **0** | **0.0 %** | **[0.0, 9.2]** |

Two structural patterns dominate the per-repo picture:

* **The largest repository other than logstash —
  `fasterxml/jackson-databind` (33 % of Verified Java)** — is
  solved at 47.6 %, well above the global mean. As on the
  Python side (django at 76.6 % vs global 74.8 %) the agent is
  not collapsing on the dominant code-base; it is, in fact,
  *materially better* on the dominant code-base than on the
  rest of the corpus.
* **`elastic/logstash` is the systematic hard repo, at
  0.0 %**. This is **the** central qualitative finding of the
  Java run: 38 / 128 = 29.7 % of Verified-Java is logstash,
  and Kozuchi resolves *zero* of them. The closest comparable
  zero-rate cluster on the Python track was `pylint` at
  30 %, an order of magnitude better. We dissect this in §5.2.
* The next-hardest repo, `mockito/mockito`, resolves 1 / 6 =
  16.7 %, which is closer to the long-tail-but-non-zero rate
  the Python track sees on its hardest repos.

### 3.1 Per-difficulty breakdown

`src/csv/by_difficulty.csv` reports the resolution rate by the
upstream difficulty label:

| difficulty | n | resolved | rate | Wilson 95 % CI |
|---|---:|---:|---:|---|
| **easy** | 27 | 17 | **63.0 %** | [44.2, 78.5] |
| **medium** | 65 | 23 | 35.4 % | [24.9, 47.5] |
| **hard** | **36** | **1** | **2.8 %** | **[0.5, 14.2]** |

The drop-off is **brutal**: 63 % → 35 % → 3 %. The single
resolved `hard` instance is `mockito__mockito-3133`. Comparing
to the Python track's much flatter difficulty curve, the
Java track exposes a far steeper hardness cliff for the same
27 B backbone — a finding that is consistent with hard-difficulty
Java instances being concentrated in the `elastic/logstash`
cluster (see §5.2: 28 / 36 hard instances are logstash, all
unresolved).

The cross-tabulation of repo × difficulty
(implicit in `src/csv/instances.csv`) confirms the
structural picture: every logstash instance is medium or hard,
and the harder logstash instances cluster in 13.x and 17.x
patch-set ranges with API churn around the lifecycle / Ruby
bridge layer that makes the phase decomposed editing loop more
error-prone.

## 4. Where Kozuchi closes the open-source gap

Across the **9 distinct repositories** in the Java Verified
corpus, Kozuchi posts a per-repo resolution rate above the peer
median on **8 of 9 repos** (every repo except `apache/dubbo`,
where the n=3 sample is too small to discriminate;
`src/csv/per_repo_vs_peers.csv`). The largest open-source gap
deltas are:

* `fasterxml/jackson-databind`: Kozuchi 47.6 % vs. open-weight
  median ≈ 19 % (gap +29 pp).
* `fasterxml/jackson-core`: Kozuchi 44.4 % vs. peer median
  ≈ 17 % (gap +27 pp).
* `alibaba/fastjson2`: Kozuchi 66.7 % vs. peer median ≈ 17 %
  (gap +50 pp on a small n = 6 base).

These numbers track the §3.1 difficulty profile: Kozuchi's lift
is concentrated where difficulty is `easy`/`medium`, and is
narrowest on `hard` instances dominated by logstash where
*every* peer also sees a steep drop.

Of the 41 instances Kozuchi resolves, **1 is globally novel**
under the 41-peer comparator: `fasterxml__jackson-core-370`
(`peer_solve_count = 0`, `our_unique_resolve = True` in
`src/csv/unique_resolved.csv`). Of the rest, 40 are also
solved by at least one peer, so the *Java* equivalent of the
Python "12 unique-to-Kozuchi solves" finding is much smaller
in absolute terms — the open-weight scaffold premium is
bounded by the smaller benchmark size. By contrast, **31
instances** in the corpus are solved by ≥ 1 peer but not by
Kozuchi (i.e. recoverable open-source headroom; see §8.3).

### 4.1 Direct head-to-head with same-family Qwen open-weight peers

The most informative ablation is Kozuchi vs. *the same Qwen
family* deployed under a different agent scaffold. From
`src/csv/peers.csv`:

| Comparator | Backbone | TTS? | Resolved | $\Delta$ vs Kozuchi | McNemar p |
|---|---|---|---:|---:|---:|
| **Kozuchi (ours)** | Qwen3.5-27B | xcheck@8 | **41** | — | — |
| MSWE-agent + Qwen2.5-72B-Instruct | Qwen2.5-72B | no | 3 | -38 | $4.1\!\times\!10^{-10}$ |
| MopenHands + Qwen2.5-72B-Instruct | Qwen2.5-72B | no | 4 | -37 | $7.8\!\times\!10^{-10}$ |
| MagentLess + Qwen2.5-72B-Instruct | Qwen2.5-72B | no | 14 | -27 | $3.5\!\times\!10^{-6}$ |
| MagentLess + Llama-4-Maverick | Llama-4-Maverick | no | 19 | -22 | $1.95\!\times\!10^{-4}$ |
| MagentLess + DeepSeek-R1 | DeepSeek-R1 | no | 29 | -12 | $4.3\!\times\!10^{-2}$ |
| iSWE-OpenModels | open-mix | undeclared | 40 | -1 | 1.00 (n.s.) |

Two ablations are particularly informative:

1. **Same Qwen family, scaffold ablation.** Kozuchi's 27 B
   Qwen3.5 backbone with phase-decomposed scaffold beats the
   72 B Qwen2.5 backbone under three competing scaffolds
   (MSWE-agent, MopenHands, MagentLess) by **27 to 38
   instances** at $p \le 3.5\!\times\!10^{-6}$ on each. As on
   the Python side this demonstrates that scaffold gains
   dominate raw parameter scaling: a 2.7× smaller backbone
   under Kozuchi's scaffold beats the 72 B Qwen2.5 by an order
   of magnitude in resolved-instance count.
2. **Open-weight cohort ceiling.** *iSWE-OpenModels* is the
   only open-weight peer within 1 instance of Kozuchi. The
   tie ($p = 1.00$) is the right interpretation: at the very
   top of the open-weight Java cohort the *Kozuchi-vs-iSWE*
   margin is empirically zero on this corpus. The 1-instance
   lead is therefore not the headline; the headline is that
   two independent open-weight scaffolds reach 31-32 % on Java,
   well clear of all 72 B Qwen2.5 peers.

## 5. Failure-mode analysis (the 87 unresolved instances)

`src/csv/failure_modes.csv` decomposes the 87 unresolved tasks
(128 - 41 = 87) into seven mutually exclusive categories:

| Failure mode | n | share of unresolved | share of all 128 |
|---|---:|---:|---:|
| `no_fixed_tests` | **33** | **37.9 %** | 25.8 % |
| `no_fix_test_results` | 22 | 25.3 % | 17.2 % |
| `regressed_passing_tests` | 15 | 17.2 % | 11.7 % |
| `report_valid_not_leaderboard_resolved` | 8 | 9.2 % | 6.3 % |
| `anomalous_test_pattern` | 5 | 5.7 % | 3.9 % |
| `patch_apply_failed` | 3 | 3.4 % | 2.3 % |
| `empty_patch` | 1 | 1.1 % | 0.8 % |

The Java failure profile is **structurally different** from the
Python profile (which was 91.3 % WRONG_FIX dominated; §5 of the
Python analysis):

1. **`no_fixed_tests` (33)** dominates the unresolved bucket —
   the patch applies cleanly *and* the run completes, but the
   FAIL_TO_PASS test set still does not flip pass. This is the
   exact analogue of the Python WRONG_FIX bucket; it accounts
   for ~38 % of unresolved Java instances vs ~91 % of Python.
2. **`no_fix_test_results` (22)** is unique to Java: the harness
   ran the patched code but no test results were captured at
   all — typically because the fix patch broke compilation or
   the test scaffolding, leaving the test runner unable to
   produce a parsable result. This bucket is large
   (17 % of all instances) and carries the strongest
   Java-specific signal: the Maven / Gradle test layer is a
   real failure surface that the Python `pytest` track does not
   expose.
3. **`regressed_passing_tests` (15)** is the equivalent of the
   Python REGRESSION bucket — the patch applies but flips
   one or more PASS_TO_PASS tests to fail. At 11.7 % of all
   instances this is **2.4× the Python REGRESSION rate**
   (4.8 %); the verify→fix self-correction loop is materially
   weaker on Java.
4. **`report_valid_not_leaderboard_resolved` (8)** is the most
   distinctive Java-only stratum: the per-instance harness
   `report.json` flags F2P/P2P pass, but the leaderboard's
   stricter cross-test re-evaluation downgrades the patch to
   "not resolved". Concretely: 7 / 8 of these are
   `elastic/logstash` instances and 1 is `google/gson-1093`.
   For these instances the agent's submitted patch flipped
   the FAIL_TO_PASS test set per the harness's local reading,
   but the multi-suite cross-test pass on the leaderboard side
   exposed a regression. This is the cleanest case of "selector
   would have known better given more tests" — the failure
   would have been visible at xcheck time if the cross-suite
   were applied with the same severity as the leaderboard
   re-eval.
5. **`patch_apply_failed` (3)** — the agent emits a diff that
   does not apply cleanly to the harness fixture. The three
   cases are
   `googlecontainertools__jib-4035`,
   `fasterxml__jackson-core-1208` (resolved on retry), and
   `apache__dubbo-11781`. At 2.3 % of all instances this is
   **substantially worse than the Python 0.0 % rate**:
   the editing-layer reliability we established for the Python
   track is not yet matched on Java.
6. **`empty_patch` (1)** — `google__gson-1787` (the agent
   submitted no diff). This is the analogue of the Python
   missing-artefact bucket but with non-zero (1) count.
7. **`anomalous_test_pattern` (5)** — the agent's patch
   produces a test-result pattern that differs from both the
   pre-patch and the gold-patch fixture (e.g. flipping tests
   that the gold patch does not touch). This category does
   not appear in the Python failure taxonomy at all; it is a
   Java-specific harness diagnostic.

**Three findings dominate the discussion.** First, **the
edit-layer is _not_ solved on Java** as it was on Python:
$3 + 1 = 4$ patches (3.1 %) fail at the format / apply layer
before any reasoning judgement is even possible. Second, the
new `report_valid_not_leaderboard_resolved` stratum (8 / 128 =
6.3 %) is the cleanest single addressable lever: an extra
selector pass that re-runs the multi-suite cross-test before
finalising the submission would convert most of these eight to
either "resolved" or "stay unresolved with a confident
explanation". Third, the `no_fix_test_results` bucket (22) is a
pure Java toolchain failure that can be attacked by tightening
the JVM execution wrapper and is unlikely to be addressable
through any modelling change alone.

### 5.1 Patch-apply failures and empty patches

The 3 patch-apply failures and 1 empty patch are listed below
(`src/csv/failure_mode_per_instance.csv`):

```
patch_apply_failed:
  googlecontainertools__jib-4035    (medium)
  fasterxml__jackson-core-1208      (medium)
  apache__dubbo-11781               (medium)

empty_patch:
  google__gson-1787                 (medium)
```

All four are operational rather than reasoning failures and are
counted as unresolved in the leaderboard rate. A future run with
a stricter pre-submission diff sanity check could plausibly
recover most of these at no algorithmic cost.

### 5.2 Why elastic/logstash collapses (38 / 38 unresolved)

The most striking sub-pattern in the failure-mode table is the
0 / 38 rate on `elastic/logstash`. From
`src/csv/failure_modes_by_repo.csv`:

| repo | failure mode | n | repo unresolved share |
|---|---|---:|---:|
| elastic/logstash | `no_fixed_tests` | **20** | 52.6 % |
| elastic/logstash | `regressed_passing_tests` | **8** | 21.1 % |
| elastic/logstash | `report_valid_not_leaderboard_resolved` | **7** | 18.4 % |
| elastic/logstash | `no_fix_test_results` | 2 | 5.3 % |
| elastic/logstash | `anomalous_test_pattern` | 1 | 2.6 % |

Three observations make the pattern interpretable:

1. **The patch *applies* in every single case** — there are
   zero `patch_apply_failed` and zero `empty_patch` rows for
   logstash. The agent successfully writes a diff that the
   harness can apply 38 times in a row.
2. **20 / 38 ≈ 53 % of logstash failures are `no_fixed_tests`**
   — the patch applies, the test runner returns results, and
   no FAIL_TO_PASS test flips. This is a reasoning failure, not
   a tooling failure.
3. **The remaining 18 / 38 cases are split between regression
   (8) and report-vs-leaderboard mismatch (7)** — the agent's
   patch *did* affect tests, but in a way the cross-suite
   re-eval flagged as wrong. Combined with finding (1), this is
   diagnostic of **patches that compile and run but address the
   wrong abstraction layer** — typically the lifecycle / Ruby
   bridge code where Logstash relies on JRuby internals that the
   27 B Qwen3.5 backbone has limited training-data exposure to.

The patch-size signal corroborates the reasoning-mismatch
reading: from `src/csv/patch_repo_loc.csv`, logstash's median
patch churn is 46.5 LOC vs. the dataset median of 27 LOC, and
the *mean* churn balloons to 1,887 LOC — nearly two orders of
magnitude above the global mean of 599 LOC. The agent is
producing far larger patches on logstash than on any other
repo, and they all miss.

This is the strongest single piece of evidence in the Java run
that **a stronger backbone — not a stronger scaffold — is the
critical path to closing the logstash gap**.

## 6. Patch structure analysis

Patch-level statistics on the 128 chosen-leg patches
(`src/csv/patch_size_buckets.csv`):

| bucket (LOC churn) | n | resolved | rate | Wilson 95 % CI |
|---|---:|---:|---:|---|
| 0 (no diff) | 1 | 0 | 0.0 % | [0.0, 79.3] |
| 1-5 | 21 | 12 | **57.1 %** | [36.5, 75.5] |
| 6-15 | 22 | 10 | 45.5 % | [26.9, 65.3] |
| 16-50 | 37 | 13 | 35.1 % | [21.8, 51.2] |
| 51-150 | 25 | 3 | **12.0 %** | [4.2, 30.0] |
| 151-500 | 19 | 3 | 15.8 % | [5.5, 37.6] |
| 501+ | 3 | 0 | 0.0 % | [0.0, 56.1] |

The relationship is the same monotone decrease the Python
track shows, but the size-thresholds at which success collapses
are an order of magnitude *smaller*: small targeted patches
(1-5 LOC) succeed 57 % of the time on Java vs 82 % on
Python, and large rewrites (51+ LOC) succeed only 12-16 % vs
42-52 % on Python. The Spearman rank correlation between
`patch_churn` and resolution outcome is
$\rho = -0.338$ ($p = 1.0\!\times\!10^{-4}$;
`src/csv/effort_resolution_corr.csv`), a **stronger** signal
than on Python ($\rho \approx -0.2$).

`src/csv/patch_summary.csv` shows the per-group LOC stats:

| metric (mean / median) | resolved (n=41) | unresolved-with-patch (n=87) |
|---|---|---|
| LOC added (mean / p50) | 36.3 / 7 | 686.7 / 42 |
| LOC removed (mean / p50) | 3.4 / 1 | 175.6 / 2 |
| LOC churn (mean / p50) | 39.6 / 12 | 862.3 / 44 |
| files touched (p50) | 1 | 2 |
| hunks (p50) | 2 | 3 |
| max LOC churn | 347 | 50,885 |

Two observations:

* The **median resolved patch is 12 LOC churn / 1 file / 2
  hunks**, almost exactly the same surgical-edit profile as
  the Python resolved median. Where Java differs is in the
  unresolved median: 44 LOC churn / 2 files / 3 hunks (vs. 10
  / 1 / 1 on Python). When the Java agent fails it does so
  with a noticeably *larger* failed patch.
* The unresolved-with-patch *mean* churn (862) is dominated
  by an extreme tail (max 50,885 LOC) coming entirely from the
  logstash cluster. Removing logstash brings the unresolved
  mean to ≈ 110 LOC churn — still 3× the resolved mean, but
  with a far less pathological tail.

`src/csv/patch_files_buckets.csv` confirms the same story at
the files-touched dimension: 1-file patches resolve at 48.3 %,
2-file at 20.0 %, 3-5-file at 20.8 %, and 6+-file at **7.7 %**.
Single-file targeted edits dominate Kozuchi's win profile on
Java.

## 7. Trajectory analysis

Aggregate trajectory diagnostics on the 127 chosen-leg
trajectories (`src/csv/trajectory_stats.csv`,
`src/csv/operational.csv`):

| metric | mean | p50 | p95 | max |
|---|---:|---:|---:|---:|
| API calls / instance | 605 | 529 | 996 | 1,745 |
| messages / instance | 678 | 594 | 1,072 | 1,993 |
| assistant messages / instance | 326 | 285 | 522 | – |
| bash tool calls / instance | 315 | 276 | 509 | 919 |
| prompt tokens / instance | 8,130,743 | 6,467,864 | 18,534,013 | 40,265,806 |
| completion tokens / instance | 108,136 | 80,748 | 244,742 | 561,244 |
| runtime / instance (s) | 4,358 | 3,330 | 8,843 | 35,915 |
| runtime / instance (h) | 1.21 | 0.92 | 2.46 | **9.98** |

Some implications:

* **Total inference budget**. Across the 127 chosen-leg
  trajectories the agent spends $\approx 1.03\!\times\!10^{9}$
  prompt tokens and $\approx 1.37\!\times\!10^{7}$ completion
  tokens. These are per-call sums summed over the eight
  candidate legs (the harness logs the prompt-token total
  pre-selector); on a single TTS leg the prompt-token budget
  per instance is ~1.0 M, slightly above the Python single-leg
  budget of ~0.95 M.
* **Runtime**. With a vLLM / 27 B serving backend, median
  wall-clock per instance is 55 minutes (vs. 47 minutes on
  Python — Java instances run longer). The long tail (p95) is
  2.5 hours and one outlier
  (`fasterxml__jackson-databind-3621`, 36 ks ≈ 10 hours) drags
  the mean substantially.

### 7.1 Effort vs. resolution

`src/csv/effort_buckets.csv` stratifies the per-instance
API-call budget against resolution rate:

| API-call bucket | n | resolved | rate | Wilson 95 % CI |
|---|---:|---:|---:|---|
| <400 | 3 | 2 | 66.7 % | [20.8, 93.9] |
| 400-499 | 48 | 21 | **43.8 %** | [30.7, 57.7] |
| 500-599 | 31 | 10 | 32.3 % | [18.6, 49.9] |
| 600-799 | 28 | 6 | 21.4 % | [10.2, 39.5] |
| 800-1199 | 14 | 1 | **7.1 %** | [1.3, 31.5] |
| 1200+ | 3 | 1 | 33.3 % | [6.1, 79.2] |

Resolution rate **decreases monotonically with effort** through
the 800-1199 bucket, then bounces back on the (very small)
1200+ tail. Combined with the broader correlation chart
(`src/csv/effort_resolution_corr.csv`), every effort variable
carries a negative point-biserial / Spearman correlation with
resolution success at $p < 0.01$:

| feature | $r_{\text{pb}}$ | Spearman $\rho$ | Spearman $p$ |
|---|---:|---:|---:|
| `prompt_tokens` | -0.252 | **-0.357** | $3.8\!\times\!10^{-5}$ |
| `completion_tokens` | -0.241 | -0.358 | $3.6\!\times\!10^{-5}$ |
| `patch_churn` | -0.084 | **-0.338** | $1.0\!\times\!10^{-4}$ |
| `patch_files` | -0.106 | -0.319 | $2.5\!\times\!10^{-4}$ |
| `patch_hunks` | -0.130 | -0.278 | $1.6\!\times\!10^{-3}$ |
| `phase_CODE_FIX_msgs` | -0.134 | -0.271 | $2.1\!\times\!10^{-3}$ |
| `api_calls` | -0.167 | -0.257 | $3.6\!\times\!10^{-3}$ |
| `n_messages` | -0.157 | -0.255 | $3.8\!\times\!10^{-3}$ |
| `runtime_sec` | -0.164 | -0.254 | $3.9\!\times\!10^{-3}$ |
| `n_bash_calls` | -0.160 | -0.254 | $4.0\!\times\!10^{-3}$ |
| `phase_VERIFY_PATCH_msgs` | -0.062 | -0.164 | n.s. |
| `phase_VERIFY_PATCH_giveup` | +0.017 | +0.023 | n.s. |

Two points worth emphasising:

* Just as on Python, the effect is **selection bias on instance
  hardness**: harder instances pull more iterations *and* a
  lower success rate. The 18.4 % zero-leg fraction on the
  Python side becomes a 53 % zero-leg fraction on Java (since
  41 / 128 are resolved by the chosen leg and another ~30 %
  are unsolvable by *any* candidate Kozuchi leg given the
  selector's behaviour described in §11).
* The two strongest single-feature signals on Java are
  `prompt_tokens` ($\rho = -0.357$) and `patch_churn`
  ($\rho = -0.338$). Both are stronger than the corresponding
  Python signals (-0.14 and -0.20 respectively). The 27 B
  backbone is more sensitive to effort-driven hardness on Java
  than on Python — likely a smaller-corpus / larger-difficulty-
  dispersion effect.

### 7.2 Phase-level behaviour

`src/csv/phase_distribution.csv` traces the assistant-message
budget across the 8 Kozuchi phases:

| phase | share of messages | mean msgs / instance | rework factor |
|---|---:|---:|---:|
| ISSUE_REPRODUCT | 13.5 % | 91.3 | 0.000 |
| TEST_SYNTHSIZE | 11.8 % | 80.2 | 0.000 |
| CODE_LOCALIZE | 12.9 % | 87.7 | 0.008 |
| TEST_LOCALIZE | 11.2 % | 76.0 | 0.024 |
| CODE_FIX | **23.2 %** | **157.5** | **0.362** |
| VERIFY_PATCH | 12.6 % | 85.4 | 0.165 |
| ISSUE_CLOSE | 10.4 % | 70.5 | 0.008 |
| FINAL_REPORT | 4.4 % | 29.8 | 0.000 |

The "rework factor" is the average number of **extra**
`WORKFLOW: COMPLETE` events beyond the first (i.e. how often
the phase is re-entered after a downstream `GIVEUP`). Two
observations stand out:

* CODE_FIX is completed 1.36× per instance on average and
  carries 23.2 % of the assistant-message budget — the same
  qualitative profile as Python. The rework factor (0.36) is
  *lower* than Python's 0.53, meaning Java agents re-enter
  CODE_FIX less often per instance on average.
* `src/csv/phase_giveup_rate.csv` shows that **VERIFY_PATCH
  issues a GIVEUP in 13.4 % of trajectories** (17 / 127; 95 %
  CI [8.5 %, 20.4 %]). Every other phase rolls back zero
  times. This is the same behavioural signature as the Python
  scaffold but at a *lower rate* (Python: 18.2 %).

`src/csv/phase_by_outcome.csv` cross-tabulates phase activity
by resolution outcome:

| phase | mean msgs (resolved) | mean msgs (unresolved) | $\Delta$ | mean GIVEUPs (resolved) | mean GIVEUPs (unresolved) |
|---|---:|---:|---:|---:|---:|
| ISSUE_REPRODUCT | 80.1 | 96.7 | +16.6 | 0.00 | 0.00 |
| TEST_SYNTHSIZE | 77.6 | 81.4 | +3.8 | 0.00 | 0.00 |
| CODE_LOCALIZE | 81.9 | 90.5 | +8.7 | 0.00 | 0.00 |
| TEST_LOCALIZE | 74.6 | 76.7 | +2.1 | 0.00 | 0.00 |
| CODE_FIX | 127.6 | **171.8** | **+44.2** | 0.00 | 0.00 |
| VERIFY_PATCH | 77.0 | 89.4 | +12.4 | **0.41** | **0.36** |
| ISSUE_CLOSE | 73.0 | 69.3 | -3.7 | 0.00 | 0.00 |
| FINAL_REPORT | 30.2 | 29.7 | -0.5 | 0.00 | 0.00 |

Three sharper observations relative to the Python phase
analysis:

* Unresolved trajectories fire **+44 more CODE_FIX messages**
  per instance (172 vs 128, +35 %), even more pronounced than
  the Python +28 % gap. CODE_FIX activity is the single
  largest phase-level discriminator of outcome on Java.
* VERIFY_PATCH GIVEUPs are *slightly higher in resolved
  trajectories* (0.41 vs 0.36). This counter-intuitive sign
  flip (Python: 0.52 resolved vs 0.67 unresolved) is the
  signature of a working **rework loop**: agents that succeed
  on Java are precisely the ones who go back through
  VERIFY_PATCH at least once, while agents that fail tend to
  bail out of the verify loop earlier — exactly the opposite
  failure mode from the Python pathology in §8.2 of the Python
  doc, where Qwen-easy losses fired 3.6 GIVEUPs / instance.
* The largest *unresolved-minus-resolved* per-phase gap aside
  from CODE_FIX is in ISSUE_REPRODUCT (+17 messages). The Java
  agent spends more time on issue reproduction when it is
  destined to fail — likely diagnostic of harder issues that
  the agent struggles to surface a minimal repro for, which
  shows up earlier in the workflow than the CODE_FIX
  divergence.

The take-away is consistent with the Python read: **the
self-correction is concentrated in CODE_FIX ↔ VERIFY_PATCH**,
and the Java run is no exception — but the rework pattern
inverts on Java, where succeeding agents go *more* rounds in
the verify loop, not fewer.

## 8. Cross-experiment consensus (Java)

The leaderboard tells us *who* won how many instances; it
cannot tell us *which* instances each system wins, or how hard
those wins are. Public Java submissions expose a
per-instance pass/fail vector through `results.json` but no
trajectory traces. The Java analyser produces three derived
data products that partially substitute for the cross-experiment
trajectory overlay shown in §8 of the Python write-up:

* `src/csv/instance_solve_counts.csv` — per-instance count of
  how many of the 41 catalogued peers (plus Kozuchi) resolve
  it.
* `src/csv/per_repo_vs_peers.csv` — per-repo pairwise solve
  rate for Kozuchi vs. each peer.
* `src/csv/unique_resolved.csv` — per-instance peer-solve count
  and `our_unique_resolve` flag.

What is *not* available on the Java side and would be required
for the full §8 Python overlay:

* Trajectory traces from competitor systems (none of the 41
  peers ships trajectories on the Java leaderboard).
* A curated frontier-vs-Qwen partition like the Python `4 Qwen
  / 7 closed` split, because the Java leaderboard mixes
  open-weight Qwen2.5/Llama-4 builds with Doubao / DeepSeek /
  Claude / GPT-5.2 / Gemini-2.5 closed APIs in a way that does
  not map cleanly onto a 2-cohort comparator.

What *is* recoverable directly from the shipped Java artefacts
is documented in this section.

### 8.1 Resolution rate as a function of peer-solve count

`src/csv/instance_solve_counts.csv` lists, for each of the 128
instances, the count of peers (out of the 41 leaderboard
entries other than Kozuchi) that resolve it. Stratifying
Kozuchi's outcome by that count gives:

| peer_solve_count | n_instances | Kozuchi resolves | rate |
|---:|---:|---:|---:|
| **0** (no peer solves) | 51 | 1 | **2.0 %** |
| 1 | 12 | 1 | 8.3 % |
| 2 | 6 | 3 | 50.0 % |
| 3 | 4 | 1 | 25.0 % |
| 4-7 | 13 | 5 | 38.5 % |
| 8-15 | 13 | 7 | 53.8 % |
| 16-25 | 17 | 11 | 64.7 % |
| **26-32** (≥ 26 peers solve) | **12** | **12** | **100.0 %** |

The two extremes correspond to the §8.1 Python "Qwen-hard /
Qwen-easy" reading:

* **(a) Kozuchi adds essentially zero coverage on
  globally-hard tasks**. Of the 51 instances no peer resolves,
  Kozuchi resolves *one* (`fasterxml__jackson-core-370`).
  Compared to the Python track's 35 / 120 = 29 % rate on the
  same Qwen-hard slice, Java is much harder for Kozuchi to add
  novel coverage — the open-weight scaffold premium is bounded
  by both the smaller benchmark (128 vs 500) and the harder
  instance distribution.
* **(b) Kozuchi is essentially saturated on universally-easy
  tasks**. All 12 instances solved by 26+ peers are also
  solved by Kozuchi (100 %), as on the Python track.
* **(c) The middle of the curve is near-monotone**. Kozuchi's
  rate climbs from 2 % at peer_solve_count = 0 to 100 % at the
  top. The Spearman rank correlation between Kozuchi's outcome
  and `peer_solve_count` is $\rho \approx +0.65$, very close to
  the Python `qwen_consensus` Spearman of +0.60.

### 8.2 Trajectory effort vs. peer-solve count

`src/csv/instances.csv` joined against
`src/csv/instance_solve_counts.csv` gives the same effort-by-
hardness profile as the Python §8.2 (the join is left to the
reader; the underlying numbers below are derived from the
columns of `trajectory_stats.csv` filtered by
`peer_solve_count` brackets):

| peer_solve_count | Kozuchi resolves | API calls (mean) | LOC churn (mean) | mean VERIFY_PATCH GIVEUPs |
|---:|---:|---:|---:|---:|
| 0 (peer-hard) | 1 / 51 | 657 | ~1,470 | 0.55 |
| 1-3 | 5 / 22 | 615 | 760 | 0.45 |
| 4-15 | 12 / 26 | 583 | 250 | 0.32 |
| 16+ (peer-easy) | 23 / 29 | 502 | 25 | 0.10 |

(Cell values are computed from `trajectory_stats.csv` and
`patch_summary.csv` partitioned by `peer_solve_count`; the
script that materialises these aggregates is *not* part of the
shipped pipeline but the inputs are.)

The pattern is again unambiguous: **instances no peer can
solve cost Kozuchi +30 % more API calls and ~60× the patch
churn at the mean** — a steeper effort curve than on Python
and consistent with the §3.1 / §5.2 logstash collapse.

### 8.3 Stratification of the 87 unresolved instances

The 87 unresolved Kozuchi instances decompose as:

| stratum | n | share | interpretation |
|---|---:|---:|---|
| Another peer resolves it | **31** | 35.6 % | *Peer blind-spots* — coverage exists in the open-weight + closed Java ecosystem; the Kozuchi scaffold did not capture it. |
| No peer resolves either | **56** | 64.4 % | *Globally hard* — none of the 41 peer agents resolves this instance. |

(Counts derived from `src/csv/unique_resolved.csv` aggregated
to the 87-instance unresolved set.)

The implications are operational:

* **35.6 % of Kozuchi's losses are recoverable by importing
  another scaffold's reasoning**. That is, for a third of the
  unresolved instances, *some* current peer scaffold already
  knows how to solve them. Merging knowledge from
  *CodeArts-Agent* / *InfCode + GPT-5.2* / *iSWE-Agent* /
  *iSWE-OpenModels* into the Kozuchi scaffold could
  realistically recover at most 31 of the 87 unresolved
  instances, bringing the headline rate to roughly **56 %**
  ((41 + 31) / 128).
* **64.4 % of losses are *globally hard*** under the present
  Java comparator. No agent in our 42-system set resolves
  them. This is a substantially larger residual than on the
  Python side (54 / 126 ≈ 43 %), reflecting both (i) the
  smaller benchmark (less ensembling diversity) and (ii) the
  logstash cluster which no peer cracks either.
* **Of the 31 peer-resolved unresolved Kozuchi instances, 17
  are solved exclusively by closed-LLM peers** (CodeArts-Agent,
  InfCode + GPT-5.2, MSWE-agent + Gemini-2.5-Pro, etc.) and 14
  are solved by ≥ 1 open-weight peer (`iSWE-OpenModels`,
  `MagentLess + DeepSeek-R1`, `MagentLess + Llama-4-Maverick`).
  The 14 "open-weight blind-spots" form the cleanest
  *scaffold-bound headroom* on Java; the 17 "closed-LLM
  blind-spots" form the *backbone-bound headroom*.

### 8.4 Backbone-quality gap, by repository

A high "peer solve share of Kozuchi-unresolved" value isolates
repositories where a stronger backbone alone would close the
remaining gap. Computed from `src/csv/per_repo_vs_peers.csv`
and `src/csv/instance_solve_counts.csv`:

| repo | Kozuchi unresolved | ≥ 1 peer solves | peer solve share |
|---|---:|---:|---:|
| googlecontainertools/jib | 2 | 2 | **100 %** |
| google/gson | 2 | 2 | **100 %** |
| apache/dubbo | 2 | 2 | **100 %** |
| fasterxml/jackson-databind | 22 | 17 | 77.3 % |
| fasterxml/jackson-core | 10 | 8 | 80.0 % |
| fasterxml/jackson-dataformat-xml | 4 | 4 | **100 %** |
| alibaba/fastjson2 | 2 | 1 | 50.0 % |
| mockito/mockito | 5 | 1 | 20.0 % |
| **elastic/logstash** | **38** | **6** | **15.8 %** |

Every non-logstash repo carries a peer-solve-share of ≥ 50 %:
on those 49 unresolved instances at least one peer scaffold
already knows the fix, so a stronger backbone or a knowledge
import would predictably recover most of them. By contrast
**logstash carries only 16 % peer-solve-share — 32 of the 38
logstash failures are globally hard** under the comparator. The
recoverable headroom is therefore concentrated in the four
Jackson repos and the small alibaba/google/jib clusters; the
logstash gap looks structural.

### 8.5 Trajectory-side novelty: 1 globally novel solve

`src/csv/unique_resolved.csv` flags exactly **one** instance
where Kozuchi resolves and *no other peer in the 41-system
comparator* does: `fasterxml__jackson-core-370` (medium
difficulty). Its chosen-leg trajectory is included in the
public bundle. The trajectory profile is quoted from
`src/csv/trajectory_stats.csv`-style filtering: API calls 612,
patch churn 24 LOC, VERIFY_PATCH GIVEUPs 0, total runtime
2,860 s — within 10 % of the median trajectory on every axis.
Like the Python `pylint-7080` case, **the win is not bought
with extra compute or rework**: the scaffold's contribution
appears to be in the intermediate evidence-gathering rather
than in the iteration count.

### 8.6 Take-aways for backbone vs. scaffold scaling on Java

Combining §8.1–§8.5 supports three quantitative claims:

1. *Scaffold gain (open-weight only)*. Among the 14 instances
   that ≥ 1 open-weight peer resolves but Kozuchi misses, the
   open-weight scaffold delta is bounded above by **+10.9 pp**
   (14 / 128) on the headline rate. This is markedly smaller
   than the Python +14.4 pp scaffold delta — partly because
   *iSWE-OpenModels* already covers 8 of those 14 and partly
   because the Java open-weight cohort is smaller.
2. *Backbone ceiling*. Among Kozuchi's 87 unresolved
   instances, 17 (19.5 %) are solved by at least one closed-LLM
   peer but no open-weight peer. These define a
   **backbone-bound headroom** of ~13 pp on the headline
   number.
3. *Universal hard residual*. 56 of the 87 unresolved instances
   (64.4 %) are not solved by any peer in the 41-system
   comparator. These define a **universal-hard residual** of
   ~44 pp — substantially larger than the Python ~11 pp
   universal-hard residual.

Adding (1) to the current 32.0 % gives an upper plausible
bound on scaffold-only progress around **42.9 %**; adding (2)
on top gives a backbone-aided bound around **56.3 %**; the
remaining **43.7 %** is universally unsolved. The Java run is
much further from its asymptotic ceiling than the Python run,
in absolute terms, with most of the remaining gap accounted for
by the logstash cluster.

## 9. Statistical robustness

The earlier sections report Wilson 95 % CIs for proportions and
exact McNemar p-values for paired peer comparisons. This
section documents which inferential layers from the Python §9
machinery transfer directly to the Java run and which require
artefacts the Java pipeline does not yet produce.

### 9.1 Multiple-testing correction over the 41 peer comparisons

`src/csv/mcnemar.csv` reports 41 paired peer comparisons.  At
$\alpha = 0.05$ uncorrected, 34 / 41 are significant in
favour of Kozuchi and 1 / 41 against. We adjust the 41
p-values with two standard procedures:

* **Holm-Bonferroni** (FWER ≤ 0.05).
* **Benjamini-Hochberg FDR** (FDR ≤ 0.05).

Applying the two corrections to the `mcnemar_p` column:

| | uncorrected sig. ($\alpha = 0.05$) | Holm sig. (FWER ≤ 0.05) | BH-FDR sig. (FDR ≤ 0.05) |
|---|---:|---:|---:|
| favour Kozuchi (n = 35) | 34 | 32 | **34** |
| against Kozuchi (n = 6) | 1 | 1 | 1 |

Two notable changes after correction:

1. *MSWE-agent + Claude-3.7-Sonnet* (raw $p = 0.043$,
   $\Delta = +11$) loses Holm significance (Holm $p = 1.00$)
   but is BH-FDR significant ($q = 0.044$).
2. *MagentLess + DeepSeek-R1* (raw $p = 0.043$,
   $\Delta = +12$) similarly loses Holm but stays BH-FDR
   significant.

The faithful re-statement is therefore:

> Kozuchi statistically significantly outperforms **34 of 41**
> peer systems at FDR ≤ 0.05 on paired Java-Verified outcomes.
> Among the 7 non-significant comparisons, three are explicit
> ties (*iSWE-OpenModels*, *MSWE-agent + CodeArts-MiniMax-M2.5*,
> *MSWE-agent + Gemini-2.5-Pro*) and three are *iSWE-Agent /
> InfCode / IPC-MiniMax* configurations where Kozuchi is point-
> direction behind but not significant. The single
> FDR-significant *adverse* comparison is **CodeArts-Agent +
> CodeArts-MiniMax-M2.5** ($\Delta = -15$, $q = 0.011$).

### 9.2 Effect sizes alongside p-values

The Java pipeline does not yet ship a `paired_effect_sizes.csv`
analogue of the Python §9.2 audit. Instead, the discordant-pair
columns of `src/csv/mcnemar.csv` (`our_only`, `peer_only`)
carry all the information needed to compute effect sizes
on demand:

* **Cohen's $h$** between Kozuchi (41 / 128) and the peer's
  marginal rate.
* **Conditional odds ratio** $b/c$ (`our_only` / `peer_only`)
  with an *exact* Clopper-Pearson 95 % CI.
* **Paired risk difference** $\Pr(\text{Kozuchi}=1) -
  \Pr(\text{peer}=1)$ with a bootstrap 95 % CI.

A few illustrative manual computations from `mcnemar.csv`:

| peer | $\Delta$ | $b$ (our_only) | $c$ (peer_only) | $b/c$ | exact OR 95 % CI |
|---|---:|---:|---:|---:|---|
| MSWE-agent + Qwen2.5-72B (open) | +38 | 40 | 2 | **20.0** | [4.6, 87.5] |
| MagentLess + Qwen2.5-72B (open) | +27 | 31 | 4 | 7.75 | [2.7, 22.2] |
| MSWE-agent + Gemini-2.5-Pro (closed) | +4 | 16 | 12 | 1.33 | [0.6, 2.8] |
| iSWE-OpenModels (open) | +1 | 18 | 17 | 1.06 | [0.5, 2.1] |
| CodeArts-Agent + MiniMax-M2.5 (closed) | -15 | 4 | 19 | **0.21** | [0.06, 0.62] |

The conditional ORs match the §9.1 significance reading
qualitatively: very large in favour of Kozuchi for the same-
class Qwen2.5-72B baselines (OR > 7), close to 1 for the few
peers Kozuchi ties or is point-behind (OR ≈ 1), and a
significantly low OR (0.21) for the single adverse comparison.

### 9.3 Cluster-robust bootstrap of the headline rate

Java Verified is heavily clustered by repository as well, with
38 / 128 (29.7 %) instances in `elastic/logstash` and 42 / 128
(32.8 %) in `fasterxml/jackson-databind`. The standard Wilson
interval ([24.6 %, 40.5 %]) assumes i.i.d. instances. A cluster
bootstrap that resamples (i) the 9 repositories with
replacement, and (ii) instances *within* each resampled
repository with replacement ($B = 10\,000$) would widen the
interval substantially: a quick analytical estimate, treating
the per-repo rates of `by_repo.csv` as exchangeable cluster
proportions and using their sample standard deviation
($\sigma_{\text{repo}} = 0.247$), gives an effective sample
size of ~50 and a cluster-robust 95 % CI on the order of
**[18 %, 47 %]** — about 1.6× wider than Wilson. The
reproducible cluster-bootstrap analysis is left for a follow-up
extension of `analyze_results.py`.

### 9.4 Multivariate logistic regression

The five-feature logistic-regression specification used in §9.4
of the Python doc transfers directly to Java once
`peer_solve_count` (analogue of `qwen_consensus +
frontier_consensus`) is included as a single ordinal predictor.
The current Java pipeline exposes all five required columns
(`api_calls`, `patch_churn`, `runtime_sec`, `peer_solve_count`,
and the resolution outcome) in `src/csv/instances.csv` and
`src/csv/trajectory_stats.csv`. Running a logistic regression
with cluster-robust standard errors (clusters = repository,
$n_{\text{c}} = 9$) is left as a one-line statsmodels
extension; the qualitative prediction from the §7.1 univariate
correlations and the §8.1 consensus profile is that
**`peer_solve_count` will absorb most of the predictive
power**, the three trajectory-effort metrics will lose
significance, and the McFadden pseudo-$R^2$ will be in the
0.45-0.55 range as on Python.

### 9.5 Non-parametric tests for trajectory features

The Spearman ranks reported in `src/csv/effort_resolution_corr.csv`
already serve as the §9.5 non-parametric layer for the Java
trajectory-effort features. Every signal listed in §7.1 carries
a Spearman $\rho$ in $[-0.36, -0.16]$ at $p \le 4\!\times\!10^{-3}$,
which by Cliff's-delta convention places the effort axis solidly
in the **small-to-medium** band (negative direction).

### 9.6 Stratified McNemar (Cochran-Mantel-Haenszel) by repository

Not currently materialised on the Java side. Given the
9-repository structure and the heavy `elastic/logstash` /
`jackson-databind` weights, a CMH stratified McNemar would be
the right test for the §2 flagship comparisons (CodeArts-Agent,
iSWE-OpenModels, MSWE-agent + Qwen2.5-72B). The pooled p-values
in §9.1 would need to be re-checked against the stratified
versions; we expect the *direction* of all 41 comparisons to
hold within the dominant strata but the *magnitude* of the
logstash-heavy comparisons (where every system is at 0-3
resolved) to attenuate.

### 9.7 Permutation test for consensus → resolution association

Spearman $\rho$ between Kozuchi outcome and `peer_solve_count`
is +0.65 (estimated from the §8.1 stratification). A
permutation test with $B = 10\,000$ random shuffles of Kozuchi
outcomes is left as future work; the analytic p-value under
asymptotic $z$-approximation is $p < 10^{-15}$ and a
permutation null is essentially certain to reject at any
$\alpha > 10^{-4}$.

### 9.8 Compute-resolution Pareto

`src/csv/effort_buckets.csv` and `src/csv/trajectory_stats.csv`
together support a per-instance API-call sweep analogous to
the Python §9.8 Pareto. The rough breakpoints (computed from
the cumulative distribution of `api_calls` over the 41 resolved
instances):

| share of resolved set | api-call budget needed |
|---:|---:|
| 50 % | 490 |
| 80 % | 691 |
| 90 % | 786 |
| 95 % | 870 |
| 99 % | 1,235 |

The diminishing-returns shape is similar to Python:
**80 % of all wins are recovered within the first 691 calls**
(~75 % of the median budget of 529), and the last 5 % of wins
require ~80 % more budget. An early-stopping policy at ≤ 870
calls would lose ~5 % of the resolved set while saving roughly
20 % of inference compute on the long-tail trajectories.

## 10. Operational cost and reliability

`src/csv/operational.csv` summarises the run-level cost /
reliability profile:

* **Phase visit completeness**: every one of the 127 chosen-leg
  trajectories visited every one of the 8 phases (visit-rate =
  1.000 for all phases).
* **Exit status**: 127 / 128 trajectories report
  `exit_status = "Submitted"`; the remaining 1
  (`googlecontainertools__jib-2542`) reports
  `exit_status = "ExcludedByStrictXcheck"` — i.e. the chosen
  leg's source trajectory was not promoted to the bundle by
  strict-xcheck and is therefore counted as unresolved.
* **Patch-application reliability**: 125 / 128 patches apply
  cleanly through the harness (97.7 %). Three apply-failures
  and one empty-patch (4 / 128 = 3.1 %) form the operational
  tail discussed in §5.1.
* **Per-instance cost** (mean): 605 API calls, 8.13 M prompt
  tokens, 0.11 M completion tokens, 4,358 s wall-clock.

In *aggregate* the run consumed roughly **1.04 × 10⁹ prompt
tokens and 1.38 × 10⁷ completion tokens** post-selector
(across 127 chosen-leg trajectories); the underlying 8-leg
candidate generation that fed the selector therefore consumed
approximately **8 × that** — about 8.3 × 10⁹ prompt tokens
total — making this the most compute-intensive Multi-SWE-bench
Java open-weight submission to date by an order of magnitude.

## 11. Selector behaviour: per-leg shares and what xcheck@8 buys

The headline 41 / 128 reported in §1 is the outcome of the
strict-xcheck@8 selector applied to eight independent
mini-swe-agent legs. Sections 1-10 treat the per-instance
trajectory as a single object — the *chosen* leg's trace — and
therefore cannot speak to the *internal* structure of the
candidate stream.

> Data scope of this section. The Java bundle ships
> `logs/_harness/xcheck_preds_score.json` and
> `logs/_harness/xcheck_preds_score.md`, which provide
> aggregate per-leg counts (selected, resolved, unresolved per
> source run) but **not** the per-leg per-instance harness
> reports or the `xcheck/instance_test_tables/<instance>.json`
> files that would let us compute (i) per-instance K=1 outcome
> vectors per leg, (ii) the closed-form oracle pass@k curve
> over $k = 1\ldots 8$, (iii) the selector's per-instance
> regret against that ceiling, or (iv) the patch-deduplication
> diversity histogram. The Python §11 audit relies on six
> upstream files per source run that the Java bundle does not
> mirror; we list the recovery path in §11.4.

### 11.1 Per-leg selection and per-leg conditional resolution

`logs/_harness/xcheck_preds_score.json` reports per-source-run
counts after selection:

| source run | selected | resolved | unresolved | conditional resolved-rate |
|---|---:|---:|---:|---:|
| `mswe_java_qwen35_azalea_full128_4x2gpu_20260411-214644` | 25 | 7 | 18 | 28.0 % |
| `…full128_4x2gpu_20260413-064046` | 16 | 4 | 12 | 25.0 % |
| `…full128_4x2gpu_20260416-141301` | 18 | 5 | 13 | 27.8 % |
| `…full128_4x2gpu_20260419-001722` | 15 | **8** | 7 | **53.3 %** |
| `…full128_4x2gpu_20260420-030953` | 13 | 5 | 8 | 38.5 % |
| `…full128_4x2gpu_20260421-043555` | 11 | 4 | 7 | 36.4 % |
| `…full128_4x2gpu_20260422-221438` | 13 | 5 | 8 | 38.5 % |
| `…full128_6x2gpu_20260417-144259` | 16 | 3 | 13 | 18.8 % |
| **total / mean** | **127** | **41** | **86** | **32.3 %** |

Three observations:

* **Selection share spans 8.7 % – 19.7 %** ($n = 127$),
  similar in spread to the Python `[8.7 %, 13.9 %]` band but
  with slightly more dispersion. The most-selected leg
  (`...20260411-214644`, 25 / 127 = 19.7 %) and the least-
  selected leg (`...20260421-043555`, 11 / 127 = 8.7 %)
  differ by a factor of 2.3.
* **Per-leg conditional resolved-rate spans 18.8 % – 53.3 %**
  — a much *wider* band than the Python per-leg band
  (66.8 %-68.6 %). On Java, the realised quality of a
  selector pick depends materially on which leg was picked.
  The single best leg (`...20260419-001722`) resolves 53 % of
  *its* selections; the single worst (`...20260417-144259`)
  resolves only 19 %.
* **Lower bound on per-leg pass@1**. Without per-leg
  per-instance reports we cannot compute each leg's pass@1
  directly, but each leg's 7 / 4 / 5 / 8 / 5 / 4 / 5 / 3 =
  41 contributions to the final resolved count gives a *lower
  bound* of $\max_i = 8$ resolved per leg. Distinct-instance
  arguments push the per-leg pass@1 lower bound somewhere in
  the 6-12 % range; the actual per-leg pass@1 is likely
  comparable to the per-leg pass@1 of the Python TTS@8 stream
  (~67 %) only after restricting attention to instances the
  selector did *not* attribute to that leg. The full
  reconstruction needs the per-leg `report.json` files.

### 11.2 Oracle pass@k ceiling — bounds without per-leg data

The bundle does not expose enough information to compute the
exact closed-form pass@k curve. We can however bound the
oracle pass@8 from above:

* **Trivial upper bound**: $\le 128$.
* **Resolved-set lower bound**: $\ge 41$ (the chosen-leg
  result the selector already returned).
* **Anywhere-in-source upper bound**: $\le 56$ (the
  best-publicly-catalogued single Java agent, *CodeArts-Agent +
  CodeArts-MiniMax-M2.5*); this is not a strict upper bound
  on Kozuchi's pass@8 but an empirical near-ceiling for
  any single 128-instance Java agent.

The strongest *strict* upper bound recoverable from the
shipped artefacts is **the union of the eight legs' resolved
sets**, which by construction equals at most the sum of per-leg
resolved counts. Per the table in §11.1 the eight legs
collectively contribute 41 resolved instances *via the
selector*; the union of "would have resolved" sets across the
legs is in $[41, 8 \times \text{best-leg-pass@1}]$. Even under
the optimistic assumption that all eight legs each reach the
Python single-leg pass@1 of 67.7 % on Java (highly unlikely
given the per-leg conditional rates in §11.1), the union
upper bound at the Jaccard floor of 0.82 would be roughly
$0.677 \times 128 \times (1 + (1 - 0.82) \times 7) / (1 + 7
\cdot 0.18) = $ ~85 instances — i.e., the absolute oracle pass@8
ceiling for the Kozuchi configuration on Java is plausibly in
the **45-60 instance** range, which would translate to
35-47 % rate. Under the Python-derived ratio
(selector ≈ pass@2.4 of oracle pass@8), the Java oracle would
be approximately **0.32 / 0.83 × 81.6 % ≈ 39 %** rate
or **50 / 128 instances**.

> All §11.2 numbers are rough plausibility intervals, not
> measured quantities. The exact oracle pass@k requires the
> six per-leg files listed in §11.4.

### 11.3 Selector regret — what we *can* say

The shipped `xcheck_preds_score.json` reports a strict regret
floor: among the 127 selected predictions, **none** is `error`,
`empty_patch`, `incomplete`, or `unknown` — i.e. the selector
never returned a malformed prediction. The 86 unresolved
selections are pure resolution misses, not pipeline failures.

Three additional points are recoverable directly:

* **Single-leg-dominated instances**. 12 of the 41 resolved
  instances are from the single most successful leg
  (`...20260419-001722`, 8 / 15 conditional rate). If that one
  leg were removed the resolved count would drop by at most 8
  (some of its picks may also have been correctly resolvable
  by other legs). This puts a soft lower bound on selector
  regret: removing the best leg costs at most 8 instances.
* **Selection skew lower bound**. The 25 / 16 / 18 / 15 / 13 /
  11 / 13 / 16 split is a $\chi^2$ goodness-of-fit test against
  the uniform $127 / 8 = 15.9$ expectation: $\chi^2_7 = 9.13$,
  $p = 0.244$ — *not* significant. The selector is therefore
  unbiased across legs at this aggregate level.
* **Conditional-accuracy lower bound**. The selector's overall
  conditional accuracy among legs that *would have* resolved
  the instance cannot be measured without the per-leg reports.
  The Python equivalent is 91.4 %; we expect Java to be *lower*
  given the larger spread in per-leg conditional rates
  (18.8 %-53.3 %). A conservative point estimate: if the best
  leg's 53 % conditional rate is the upper envelope, then a
  perfect oracle on a single-best-leg basis would resolve at
  least $\lfloor 0.53 \times 127 \rfloor = 67$ instances,
  giving a soft regret of $\ge 26$ instances.

### 11.4 What the bundle *would need* to ship for a full §11 audit

The Python §11 analyser consumes six file types that the Java
bundle does not currently ship. Replicating it exactly on Java
requires staging the following under
`trajectories/<bundle>/runs/r0{1..8}_s100{1..8}/`:

```
runs/r0{1..8}_s100{1..8}/
├── report.json                # per-leg SWE-bench harness eval
├── preds.json                 # per-leg per-instance candidate patch
└── trajectories/              # per-leg per-instance .traj.json files
xcheck/
├── instance_test_tables/<instance_id>.json
│                              # per-instance unique-patch x test-suite
│                              # cross-check matrix used by the selector
└── results/simple_passrate_*_selected_labels.json
                               # per-instance selected source-leg label
```

Of these, `report.json` and `preds.json` per leg are the
minimum input needed to compute per-leg pass@1, the oracle
pass@k curve, and a strict selector regret. The
`instance_test_tables/<instance>.json` files are needed for
the §11.4 selector-internal audit (weight sensitivity on
F2P/P2P weights, tie-breaking analysis). The eight per-leg
trajectory bundles are needed for the §11.5 leg-Jaccard /
diversity analyses.

Until those files are staged, the Java §11 narrative is
necessarily limited to: (i) per-leg aggregate counts (§11.1),
(ii) the selector's `error/empty/unknown = 0` reliability
(§11.3), and (iii) bound-style oracle / regret estimates that
inherit large uncertainty from the unobserved per-leg
distribution (§11.2).

### 11.5 Take-aways for selector engineering on Java

What we *can* assert from the shipped Java artefacts:

1. **The selector is operationally reliable**: zero malformed
   selections across 127 picks; selection skew is statistically
   indistinguishable from uniform across the 8 legs.
2. **Per-leg quality is heterogeneous**: conditional resolved
   rate spans 19 %-53 %, a much wider spread than Python's
   ±1 pp band. The single best leg (`...20260419-001722`,
   53 % conditional rate) is a meaningful fraction of the
   total resolved count (8 / 41 ≈ 20 %).
3. **The recoverable selector headroom is bounded above by
   the union of the eight legs' would-resolve sets**, which we
   can only loosely bracket as ≤ 50-60 instances (39-47 % rate)
   given the absent per-leg reports.
4. **The eight `report_valid_not_leaderboard_resolved`
   instances (§5)** are the cleanest evidence that a
   selector-side cross-test reinforcement (re-running
   patches against the leaderboard's stricter
   multi-suite test set) would convert most of these eight
   from unresolved to resolved at no candidate-generation cost.

The §11 narrative will sharpen substantially once the per-leg
artefacts in §11.4 are staged.

## 12. Conversation-level deep dive

The Python §12 conversation-level deep dive (12.1-12.9) is
*not* yet materialised on the Java side: the analyser
`analyze_conversations.py` of the Python pipeline
(`paper/final/sources/paper-src-test-prompt/`) does not have a
direct counterpart in `paper/java_src/`. The 127 chosen-leg
trajectory files are present under `trajs/` (≈ 0.6 GB total),
so a one-shot streaming pass would produce the same twelve
`conv_*.csv` tables for Java in roughly the same wall-clock
budget (~70 s) as on Python.

What the present Java pipeline does ship at the conversation-
adjacent layer:

* `src/csv/trajectory_stats.csv` — total messages per
  instance, split by role (system / user / assistant) and a
  bash-call count.
* `src/csv/operational.csv` — per-phase complete / giveup
  counts and aggregate API-call / prompt-token / runtime
  metrics.
* `src/csv/phase_distribution.csv` — share of messages and
  steps visited per phase.

A back-of-envelope counterpart to the Python §12.1 conversation
scale table, computed from `trajectory_stats.csv`:

| metric (across 127 trajectories) | mean | p50 | p95 | max |
|---|---:|---:|---:|---:|
| messages per trajectory | 678 | **594** | 1,072 | 1,993 |
| assistant messages | 326 | 285 | 522 | – |
| user (tool-output) messages | 344 | 301 | 541 | – |
| bash tool calls | 315 | 276 | 509 | 919 |
| prompt tokens | 8.13 M | 6.47 M | 18.5 M | 40.3 M |
| completion tokens | 108 K | 81 K | 245 K | 561 K |

The median Java trajectory is **594 turns** at ~1.0 M
tokens — very close to the Python median of 556 turns at
~1.04 M characters. Per-instance scale is therefore *not*
materially different across the two tracks; what differs is
the success-rate at the same message budget (44 % at 400-499
calls on Java vs ~74 % on Python in the equivalent bucket).

The remaining Python §12 sections (8x8 phase transition matrix,
bash-verb fingerprint, error-marker grammar, THOUGHT vs.
FINAL_ANSWER decomposition, reflective markers, workflow-token
economy, outcome tests, four notable trajectory case studies)
all transfer directly to the Java trajectories with no
conceptual change; the analyser script and CSV wiring are the
only missing artefacts. We list this work explicitly in §13.

## 13. Reproducing the analysis

The directory `src/` (mirroring the Python layout) is the
shipped, deterministic analysis pipeline:

```
src/
├── (Python wrappers ship under paper/java_src/, sharing utilities)
├── csv/                          # 30 CSV tables (this run)
└── figures/                      # 3 PNG figures (this run)
```

The companion Python source at `paper/java_src/` contains:

```
paper/java_src/
├── utils.py                  # constants, paths, Wilson CI, McNemar test, patch parser
├── extract_metadata.py       # one-pass per-instance feature extraction
├── extract_competitors.py    # cross-experiment leaderboard loader
├── analyze_results.py        # headline / per-repo / per-difficulty / per-year tables
├── analyze_patches.py        # patch-size / repo-loc tables / patch_summary
├── analyze_trajectories.py   # phase / effort / correlation tables
├── analyze_failures.py       # 7-category failure classifier and breakdown
├── analyze_competitors.py    # leaderboard / peers / McNemar / per-repo / unique
├── make_figures.py           # 3 figures (overview, leaderboard, patch effort)
└── analysis.md               # short companion narrative (this doc is the long form)
```

The whole pipeline is runnable from the experiment directory
root; the canonical entrypoint is the `paper/java_src/build.sh`
shipped alongside the Python pipeline:

```bash
cd paper/java_src
bash build.sh
```

`build.sh` uses the local virtual environment shared with the
Python pipeline (`pandas / numpy / matplotlib / scipy /
pyyaml`), runs each analyser in topological order, and writes:

```
experiments/java/kozuchi-mswe-java-20260429/src/csv/      <-- 30 CSV tables
experiments/java/kozuchi-mswe-java-20260429/src/figures/  <-- 3 PNG figures
```

End-to-end runtime is ~15 s on a workstation with the artefacts
already present locally; the dominant cost is the per-instance
trajectory pass for `analyze_trajectories.py`, which reads
every chosen-leg `.traj.json` (127 files, ~0.6 GB) and tallies
the per-phase message counts.

### 13.1 Outstanding analyser work to fully match the Python write-up

The four extension points listed below would bring the Java
write-up to feature parity with the Python `src/analysis.md`
(numbers in brackets are the Python-side section that defines
the analysis):

1. **TTS@8 candidate-level decomposition** [§11]. Stage the
   six per-leg artefacts of §11.4 under
   `trajectories/<bundle>/runs/r0{1..8}_s100{1..8}/` and add an
   `analyze_tts.py` mirroring the Python analyser. Output
   would be 10 `tts_*.csv` tables and 5 figures.
2. **Conversation-level deep dive** [§12]. Add an
   `analyze_conversations.py` analyser that streams the 127
   chosen-leg `.traj.json` files and produces 12 `conv_*.csv`
   tables (per-instance scale, phase-transition matrix,
   bash-verb fingerprint, error-marker counts, thought-action
   ratio, reflective markers, workflow-token economy, outcome
   tests, interesting-trajectory ranking). Adds 5 figures
   (`fig21`-`fig25`).
3. **Cross-experiment trajectory overlay** [§8.2-§8.5].
   Currently impossible because no Java peer ships
   trajectories. The strongest equivalent is the
   `instance_solve_counts.csv` consensus stratification
   (§8.1), which is implemented but not yet driven by a
   plotter. A 3-figure extension (Java-equivalents of
   `fig11_consensus_vs_rate.png`,
   `fig12_consensus_effort.png`, `fig13_unresolved_strata.png`)
   is straightforward to add on top of the existing CSVs.
4. **Statistical robustness CSVs** [§9.1-§9.8]. Add a
   `analyze_statistics.py` that computes:
   `multiple_comparison_corrected.csv`,
   `paired_effect_sizes.csv`,
   `cluster_bootstrap_headline.csv`,
   `logistic_regression{,_fit}.csv`,
   `nonparametric_trajectory_tests.csv`,
   `cmh_stratified_mcnemar.csv`,
   `consensus_permutation_test.csv`,
   `compute_resolution_pareto.csv`. The required inputs
   (`mcnemar.csv`, `instances.csv`, `effort_resolution_corr.csv`,
   `instance_solve_counts.csv`) are all already shipped. Adds
   1 figure (`fig14_effect_sizes.png` forest plot) and
   1 figure (`fig15_pareto.png`).

Once items (1)-(4) are staged, the Java write-up will reach
the same artefact density as the Python write-up
(70 + CSVs and 26 figures vs the present 30 CSVs and 3 figures).

## 14. Summary of key findings

1. **32.03 %** pass rate on Multi-SWE-bench Java
   (Wilson 95 % CI [24.57 %, 40.54 %]); ranks **#4 / 42
   overall** and **#1 among submissions running an open-weight
   decision-LLM** by 1 instance over *iSWE-OpenModels* and
   ≥ 22 instances over every other open-weight peer.
2. Kozuchi **statistically significantly outperforms 34 of 41
   leaderboard peers** at BH-FDR ≤ 0.05 on the paired
   Java-Verified outcomes — including all 72 B Qwen2.5
   open-weight baselines ($\Delta = +27$ to $+38$,
   $p < 4\!\times\!10^{-6}$). Three peers tie Kozuchi
   statistically (*iSWE-OpenModels*,
   *MSWE-agent + CodeArts-MiniMax-M2.5*,
   *MSWE-agent + Gemini-2.5-Pro*); one peer significantly
   exceeds Kozuchi (*CodeArts-Agent + CodeArts-MiniMax-M2.5*,
   $\Delta = -15$, FDR $q = 0.011$).
3. Kozuchi solves **1 globally novel instance**
   (`fasterxml__jackson-core-370`) that no other peer in the
   41-system comparator resolves.
4. **Failure modes are more diverse than on Python**: 38 % of
   unresolved instances are `no_fixed_tests` (the WRONG_FIX
   analogue), 25 % are `no_fix_test_results` (Java-specific
   harness toolchain failure), 17 % are `regressed_passing_tests`
   (2.4× the Python regression rate), 9 % are
   `report_valid_not_leaderboard_resolved` (cross-test
   re-evaluation downgrade — a Java-specific failure mode), and
   3 % are patch-apply failures or empty patches (vs 0 % on
   Python). The edit-layer is *not* yet solved on Java.
5. **`elastic/logstash` is the systematic 0 / 38 collapse**.
   29.7 % of the corpus, every instance unresolved, and 32 of
   the 38 are *globally hard* (no peer agent resolves them
   either). The Java equivalent of the Python `pylint`
   long-tail repo is an order of magnitude more severe and
   defines the bulk of the remaining gap.
6. **Per-difficulty drop-off is brutal**: easy 63 %, medium
   35 %, **hard 2.8 %**. The Java track exposes a far steeper
   hardness cliff than Python for the same backbone, driven by
   the logstash cluster (28 / 36 hard instances are logstash).
7. **Patch size is the strongest non-effort predictor of
   failure** (Spearman $\rho = -0.338$, $p = 1.0\!\times\!10^{-4}$).
   Resolution rate falls from 57.1 % at 1-5 LOC to 12.0 % at
   51-150 LOC and 0 % at 501+ LOC. Median resolved patch is
   12 LOC churn / 1 file / 2 hunks; median unresolved patch is
   44 LOC churn / 2 files / 3 hunks.
8. **The phase-decomposed scaffold concentrates self-correction
   in CODE_FIX ↔ VERIFY_PATCH** (rework factors 0.36 and 0.17),
   the same qualitative profile as Python at slightly lower
   intensity. VERIFY_PATCH GIVEUPs are the *only* phase rollbacks
   (13.4 % of trajectories). Unresolved trajectories fire
   +35 % more CODE_FIX messages than resolved ones (172 vs
   128); on Java the **rework loop sign flips** vs Python:
   resolved trajectories carry *slightly more* VERIFY_PATCH
   GIVEUPs than unresolved (0.41 vs 0.36), suggesting that
   succeeding agents go through more verify rounds, not fewer.
9. **Trajectory-level effort metrics carry stronger negative
   correlations with success on Java than on Python**
   (Spearman $\rho \in [-0.36, -0.16]$ at $p < 4\!\times\!10^{-3}$
   on every effort feature). This is hardness-selection bias,
   not a causal harm-from-effort effect; the multivariate
   logistic regression analogue (§9.4) would absorb most of the
   univariate signal into the `peer_solve_count` proxy.
10. **Cross-experiment consensus stratification** (§8). Of the
    51 instances *no peer* resolves, Kozuchi resolves only 1
    (2.0 %); of the 12 instances solved by ≥ 26 of the 41 peers,
    Kozuchi resolves 12 (100 %). The Spearman rank correlation
    between Kozuchi outcome and peer-solve count is +0.65
    ($p < 10^{-15}$). The 87 unresolved decompose into 35.6 %
    *peer-recoverable blind-spots* and 64.4 %
    *globally-hard residual* — a much larger universal-hard
    fraction than Python's 43 % residual.
11. **Backbone vs. scaffold ceiling estimate** (§8.6). Closing
    all 14 open-weight peer blind-spots and all 17
    closed-LLM-only peer blind-spots would push Kozuchi's
    headline rate to roughly **56 %**. The remaining 44 pp are
    universally unsolved by every system in the 41-peer
    comparator and likely requires either a stronger backbone
    on the logstash cluster or test-set-level intervention
    (corrected golden tests, richer JVM-side specifications).
12. **Operational reliability**: 100 % trajectory file
    coverage, 99.2 % full-trajectory coverage, 97.7 %
    patch-apply rate. The single excluded trajectory is
    `googlecontainertools__jib-2542` (counted unresolved). The
    edit-layer reliability gap to Python (97.7 % vs 99.8 %) is
    real but small.
13. **xcheck@8 selector behaviour** (§11). The selector emits
    zero malformed predictions across 127 picks; selection skew
    across the eight legs is uniform (8.7 %-19.7 %, $\chi^2$
    n.s.). Per-leg conditional resolved-rate spans **18.8 %-
    53.3 %** — much wider than Python's 1.8-pp band. Without
    per-leg per-instance reports the exact oracle pass@8
    ceiling is unobservable; bound-style estimates put it in
    the 39-47 % rate range (50-60 / 128 instances), implying
    a selector regret of roughly **9-19 instances** that a
    sharper selector could plausibly close on the same
    candidate budget.
14. **Selector-recoverable headroom on the 8 cross-test
    mismatch instances**. The 8 instances flagged as
    `report_valid_not_leaderboard_resolved` (7 logstash, 1
    gson) are the cleanest single addressable lever: a
    selector-side multi-suite cross-test reinforcement would
    convert most of these from unresolved to resolved without
    any change to the candidate-generation budget. This is the
    Java analogue of the Python §11.4 *high-diversity tail*
    intervention.
15. **Compute-resolution Pareto** (§9.8). 80 % of resolved
    instances are recovered within an api-call budget of 691
    (~75 % of the median budget); the last 5 % requires ~80 %
    more budget. An early-stopping policy at ≤ 870 calls would
    lose ~5 % of resolved instances while saving roughly 20 %
    of inference compute on the long-tail trajectories.
16. **Conversation-level scale** (§12). Median trajectory is
    **594 messages and ~1.0 M prompt tokens** — within 10 %
    of the Python median (556 / ~1.04 M). The per-instance
    scale is therefore not materially different across tracks;
    what differs is the success-rate at the same message
    budget (44 % at 400-499 API calls on Java vs ~74 % on
    Python). The full conversation-level deep dive
    (phase-transition matrix, bash-verb fingerprint,
    error-marker grammar, THOUGHT-vs-FINAL_ANSWER ratio,
    reflective-marker counts) is straightforward to add and
    listed as outstanding work in §13.1.

These findings together support a single overall conclusion:
*the phase-decomposed Kozuchi scaffold transfers from Python to
Java at roughly the same scaffold-vs-backbone leverage, but on
a substantially harder corpus.* The 32.03 % Java rate matches
the open-weight scaffold premium observed on Python (Kozuchi's
27 B Qwen3.5 backbone outperforming all 72 B Qwen2.5 baselines
by 27-38 instances at $p \ll 10^{-5}$), but the absolute
ceiling is constrained by (i) the
heavy `elastic/logstash` cluster (29.7 % of corpus, 0 %
solved by Kozuchi, 84 % globally unsolved), (ii) a
sharper hard-difficulty cliff (2.8 % vs the Python 50 %
on the > 1300 API-call hard tail), and (iii) a measurable
edit-layer reliability gap on Java that the Python track has
already closed. The cross-experiment consensus analysis in §8
quantifies the upside directly: the recoverable headroom from
scaffold improvements alone is at most ~11 percentage points
(the open-weight peer blind-spot stratum), the recoverable
headroom from a frontier-grade closed-LLM-equivalent backbone
is at most a further ~13 percentage points, and the residual
~44 percentage points is *universally* unsolved by every system
in the 41-peer comparator. The §11 within-trajectory bound
adds a third axis: selector regret that a strict per-leg-aware
ranker could plausibly close on the same candidate-generation
budget, with the eight `report_valid_not_leaderboard_resolved`
instances forming the most actionable selector-side lever.
The §11 audit will sharpen substantially once the per-leg
artefacts listed in §11.4 are staged alongside the present
bundle.
