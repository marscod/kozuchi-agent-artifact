# kozuchi-mini-swe-agent + qwen3.5-27b xcheck@8

Multi-SWE-bench Java Verified submission package for kozuchi-mini-swe-agent using qwen3.5-27b and strict xcheck@8 selection.

## Result

- Resolved: 41 / 128 = 32.03125%
- Submitted: 128
- Completed: 128
- Incomplete: 0
- Errors: 0

## Provenance

- Staged predictions: `swe-sota-agent/out/mswe_java_qwen35_xcheck8_full128_complete_preds_20260428/preds.json`
- Official evaluation report: `swe-sota-agent/out/mswe_java_qwen35_xcheck8_full128_complete_preds_20260428/multi_swe_java_eval_output/final_report.json`
- Source xcheck run: `swe-sota-agent/out/tts_mswe_java_qwen35_azalea_runs12345678_xcheck_full128_local_timeout1800_p8_20260423-235921`
- Evaluation settings: `MAX_WORKERS=8`, `EVAL_TIMEOUT_SEC=3600`, `multi-swe-bench==1.1.2`

`google__gson-1787` was added as an empty-patch prediction because strict xcheck selected 127 of the 128 Java Verified instances; the empty patch preserves the leaderboard denominator.
