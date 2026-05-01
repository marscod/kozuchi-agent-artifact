# RQ6 Cross-Track Reproduction Bundle

This directory is the standalone reviewer-facing source bundle for the
paper's RQ6 result: cross-language transfer from SWE-bench Verified
(Python) to Multi-SWE-bench Java Verified.

Run from this directory:

```bash
python3 build_rq6.py
```

The script reads only the local CSV files in `csv/` and regenerates:

- `out/csv/cross_track_summary.csv`
- `out/tables/cross_track_summary.tex`
- `out/figures/cross_track_kozuchi.png`

When called from `paper/final/build.sh`, the same script also refreshes
the paper-facing outputs:

- `paper/final/stats/cross_track_summary.tex`
- `paper/final/figures/cross_track_kozuchi.png`

## Source Mapping

The bundled CSVs are compact extracts from the canonical analysis
artifacts:

- Python values: `experiments/evaluation/verified/20260326_kozuchi-mini-swe-agent_qwen3.5-27b/src/csv/`
- Java values: `experiments/java/kozuchi-mswe-java-20260429/src/csv/`
- Cross-track interpretation: `experiments/comparison.md`

The script intentionally avoids hidden benchmark tests and external
leaderboard access. It is a deterministic formatting/plotting step over
already published aggregate CSV values.
