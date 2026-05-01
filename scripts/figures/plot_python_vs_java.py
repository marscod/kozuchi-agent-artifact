"""Generate a 6-panel side-by-side comparison of Kozuchi Python and Java runs.

Panels:
    (a) Headline rate with Wilson 95 % CI bars.
    (b) Resolution rate by patch-size LOC bucket -- both tracks.
    (c) Per-phase share of assistant messages -- both tracks.
    (d) Per-phase rework factor (extra COMPLETE events) -- both tracks.
    (e) Failure-mode breakdown stacked bar (sorted by share, with both tracks
        normalised to share-of-unresolved).
    (f) Trajectory effort (api_calls / messages / runtime / patch_churn p50)
        bar comparison normalised to Python = 1.0.

All numbers are hand-curated from the canonical CSVs of each track:
    Python:   experiments/evaluation/verified/.../src/csv/*.csv
    Java:     experiments/java/kozuchi-mswe-java-20260429/src/csv/*.csv

Outputs the figure to experiments/comparison_figures/fig_python_vs_java.png.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

import os

ARTIFACT_ROOT = Path(
    os.environ.get(
        "KOZUCHI_ARTIFACT_ROOT",
        Path(__file__).resolve().parents[2],
    )
).resolve()
OUT_DIR = ARTIFACT_ROOT / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "fig_python_vs_java.png"

PYTHON_COLOR = "#1f77b4"
JAVA_COLOR = "#d62728"

# ---------------------------------------------------------------------------
# Panel (a) -- headline rate w/ Wilson 95% CI
# ---------------------------------------------------------------------------
HEADLINE = {
    "Python\n(SWE-bench Verified)": dict(
        n=500, resolved=374, rate=0.7480,
        ci=(0.7082, 0.7841), color=PYTHON_COLOR,
    ),
    "Java\n(Multi-SWE-bench Verified)": dict(
        n=128, resolved=41, rate=0.3203,
        ci=(0.2457, 0.4054), color=JAVA_COLOR,
    ),
}

# ---------------------------------------------------------------------------
# Panel (b) -- resolution rate by LOC churn bucket (matched bin labels)
# ---------------------------------------------------------------------------
# Python:   from patch_size_buckets.csv (bins 0/1-4/5-10/11-25/26-50/51-100/101+)
# Java:     from patch_size_buckets.csv (bins 0/1-5/6-15/16-50/51-150/151-500/501+)
# We harmonise to a label set keyed on "small / mid / large" buckets so the
# panel is interpretable side-by-side; cell values are taken at face value
# from the underlying CSVs.
LOC_BUCKETS = [
    ("1-5",     dict(py_n=208, py_res=170, java_n=21, java_res=12)),
    ("6-25",    dict(py_n=195, py_res=149, java_n=22, java_res=10)),
    ("26-50",   dict(py_n=57,  py_res=38,  java_n=37, java_res=13)),
    ("51-150",  dict(py_n=23+12, py_res=12+5, java_n=25, java_res=3)),
    ("151+",    dict(py_n=12,  py_res=5,   java_n=22, java_res=3)),
]

# ---------------------------------------------------------------------------
# Panel (c) -- per-phase share of assistant messages
# ---------------------------------------------------------------------------
# Python:   §7.2 / phase_distribution.csv
# Java:     phase_distribution.csv  (data computed in shipped CSV)
PHASES = [
    "ISSUE_REPRODUCT",
    "TEST_SYNTHSIZE",
    "CODE_LOCALIZE",
    "TEST_LOCALIZE",
    "CODE_FIX",
    "VERIFY_PATCH",
    "ISSUE_CLOSE",
    "FINAL_REPORT",
]
PY_PHASE_SHARE = [0.125, 0.115, 0.094, 0.165, 0.219, 0.167, 0.076, 0.039]
JA_PHASE_SHARE = [0.135, 0.118, 0.129, 0.112, 0.232, 0.126, 0.104, 0.044]

# Python rework factor (extra COMPLETE per phase) from §7.2
# Java rework factor computed from operational.csv:
#   total_complete - 127 (single completion baseline) per phase, /127.
#   ISSUE_REPRODUCT 127 -> 0; TEST_SYNTHSIZE 127 -> 0;
#   CODE_LOCALIZE 128 -> 1/127; TEST_LOCALIZE 130 -> 3/127;
#   CODE_FIX 173 -> 46/127; VERIFY_PATCH 148 -> 21/127;
#   ISSUE_CLOSE 128 -> 1/127; FINAL_REPORT 128 -> 1/127.
PY_REWORK = [0.004, 0.004, 0.016, 0.014, 0.525, 0.446, 0.010, 0.008]
JA_REWORK = [0.000, 0.000, 0.008, 0.024, 0.362, 0.165, 0.008, 0.008]

# ---------------------------------------------------------------------------
# Panel (e) -- failure mode breakdown (share of unresolved)
# ---------------------------------------------------------------------------
# Python: §5 / failure_modes.csv
#   WRONG_FIX 91.3, REGRESSION 4.8, MISSING_ARTEFACT 4.0, APPLY/EMPTY 0.0
# Java: §5 / failure_modes.csv
#   no_fixed_tests 37.9, no_fix_test_results 25.3, regressed 17.2,
#   report_valid_not_leaderboard_resolved 9.2, anomalous 5.7,
#   patch_apply_failed 3.4, empty_patch 1.1
FAILURE_MODES = [
    ("WRONG_FIX  /  no_fixed_tests",       dict(py=0.913, java=0.379)),
    ("no_fix_test_results  (Java)",        dict(py=0.000, java=0.253)),
    ("REGRESSION  /  regressed_pass",      dict(py=0.048, java=0.172)),
    ("report_valid_¬leaderboard  (Java)",  dict(py=0.000, java=0.092)),
    ("anomalous_test_pattern  (Java)",     dict(py=0.000, java=0.057)),
    ("patch_apply_failed",                 dict(py=0.000, java=0.034)),
    ("empty_patch",                        dict(py=0.000, java=0.011)),
    ("missing_artefact  (Python)",         dict(py=0.040, java=0.000)),
]

# ---------------------------------------------------------------------------
# Panel (f) -- per-instance effort comparison (Python = 1.0 baseline)
# ---------------------------------------------------------------------------
# Numbers from Python operational.csv / Java operational.csv  (medians)
EFFORT = [
    ("api_calls (p50)",        490,    529.0),
    ("messages (p50)",          556,    594.0),
    ("bash calls (p50)",       257,    276.0),
    ("prompt tokens (M, p50)", 6.20,   6.47),
    ("completion tokens (K)",  83.1,   80.7),
    ("runtime (s, p50)",     2784,   3330.4),
    ("patch churn (p50, all)",  5.0,   27.0),
]


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    phat = k / n
    denom = 1 + z ** 2 / n
    centre = (phat + z ** 2 / (2 * n)) / denom
    half = z * np.sqrt(phat * (1 - phat) / n + z ** 2 / (4 * n ** 2)) / denom
    return centre - half, centre + half


def plot_panel_a(ax: plt.Axes) -> None:
    labels = list(HEADLINE.keys())
    rates = [HEADLINE[k]["rate"] for k in labels]
    cis = [HEADLINE[k]["ci"] for k in labels]
    colors = [HEADLINE[k]["color"] for k in labels]
    ns = [HEADLINE[k]["n"] for k in labels]
    rs = [HEADLINE[k]["resolved"] for k in labels]
    x = np.arange(len(labels))
    err_low = [r - lo for r, (lo, _hi) in zip(rates, cis)]
    err_high = [hi - r for r, (_lo, hi) in zip(rates, cis)]
    ax.bar(x, rates, color=colors, alpha=0.85, width=0.55,
           yerr=[err_low, err_high], capsize=8, ecolor="black")
    for i, (r, n, k) in enumerate(zip(rates, ns, rs)):
        ax.text(i, r + 0.04, f"{r*100:.2f}%\n({k}/{n})",
                ha="center", va="bottom", fontsize=10)
    ax.set_xticks(x, labels, fontsize=10)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Resolution rate")
    ax.set_title("(a) Headline rate (Wilson 95% CI)", loc="left",
                 fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)


def plot_panel_b(ax: plt.Axes) -> None:
    labels = [b[0] for b in LOC_BUCKETS]
    py_rates = [b[1]["py_res"] / b[1]["py_n"] for b in LOC_BUCKETS]
    ja_rates = [b[1]["java_res"] / b[1]["java_n"] for b in LOC_BUCKETS]
    py_ns = [b[1]["py_n"] for b in LOC_BUCKETS]
    ja_ns = [b[1]["java_n"] for b in LOC_BUCKETS]
    x = np.arange(len(labels))
    w = 0.4
    ax.bar(x - w / 2, py_rates, w, color=PYTHON_COLOR, alpha=0.85,
           label=f"Python ({sum(py_ns)} instances)")
    ax.bar(x + w / 2, ja_rates, w, color=JAVA_COLOR, alpha=0.85,
           label=f"Java ({sum(ja_ns)} instances)")
    for i, (pr, jr) in enumerate(zip(py_rates, ja_rates)):
        ax.text(i - w / 2, pr + 0.01, f"{pr*100:.0f}%", ha="center",
                va="bottom", fontsize=8, color=PYTHON_COLOR)
        ax.text(i + w / 2, jr + 0.01, f"{jr*100:.0f}%", ha="center",
                va="bottom", fontsize=8, color=JAVA_COLOR)
    ax.set_xticks(x, labels, fontsize=9)
    ax.set_xlabel("Patch LOC churn bucket")
    ax.set_ylabel("Resolution rate")
    ax.set_ylim(0, 1.0)
    ax.set_title("(b) Resolution rate vs. patch size",
                 loc="left", fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", fontsize=9)


def plot_panel_c(ax: plt.Axes) -> None:
    x = np.arange(len(PHASES))
    w = 0.4
    ax.bar(x - w / 2, [v * 100 for v in PY_PHASE_SHARE], w,
           color=PYTHON_COLOR, alpha=0.85, label="Python")
    ax.bar(x + w / 2, [v * 100 for v in JA_PHASE_SHARE], w,
           color=JAVA_COLOR, alpha=0.85, label="Java")
    ax.set_xticks(x, [p.replace("_", "_\n") for p in PHASES],
                  fontsize=8)
    ax.set_ylabel("% of assistant messages")
    ax.set_title("(c) Per-phase message share",
                 loc="left", fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", fontsize=9)


def plot_panel_d(ax: plt.Axes) -> None:
    x = np.arange(len(PHASES))
    w = 0.4
    ax.bar(x - w / 2, PY_REWORK, w, color=PYTHON_COLOR,
           alpha=0.85, label="Python")
    ax.bar(x + w / 2, JA_REWORK, w, color=JAVA_COLOR,
           alpha=0.85, label="Java")
    ax.set_xticks(x, [p.replace("_", "_\n") for p in PHASES],
                  fontsize=8)
    ax.set_ylabel("Extra COMPLETEs / instance")
    ax.set_title("(d) Per-phase rework factor",
                 loc="left", fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", fontsize=9)


def plot_panel_e(ax: plt.Axes) -> None:
    labels = [m[0] for m in FAILURE_MODES]
    py = np.array([m[1]["py"] for m in FAILURE_MODES]) * 100
    ja = np.array([m[1]["java"] for m in FAILURE_MODES]) * 100
    y = np.arange(len(labels))
    h = 0.4
    ax.barh(y - h / 2, py, h, color=PYTHON_COLOR, alpha=0.85,
            label="Python (n=126 unresolved)")
    ax.barh(y + h / 2, ja, h, color=JAVA_COLOR, alpha=0.85,
            label="Java (n=87 unresolved)")
    for i, (p, j) in enumerate(zip(py, ja)):
        if p > 0.5:
            ax.text(p + 1.0, i - h / 2, f"{p:.1f}%",
                    va="center", fontsize=8, color=PYTHON_COLOR)
        if j > 0.5:
            ax.text(j + 1.0, i + h / 2, f"{j:.1f}%",
                    va="center", fontsize=8, color=JAVA_COLOR)
    ax.set_yticks(y, labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Share of unresolved (%)")
    ax.set_xlim(0, max(max(py), max(ja)) * 1.18)
    ax.set_title("(e) Failure-mode breakdown",
                 loc="left", fontsize=11, fontweight="bold")
    ax.grid(True, axis="x", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)
    ax.legend(loc="lower right", fontsize=9)


def plot_panel_f(ax: plt.Axes) -> None:
    labels = [e[0] for e in EFFORT]
    py = np.array([e[1] for e in EFFORT], dtype=float)
    ja = np.array([e[2] for e in EFFORT], dtype=float)
    ratio = ja / py
    y = np.arange(len(labels))
    colors = [JAVA_COLOR if r >= 1.0 else "#2ca02c" for r in ratio]
    ax.barh(y, ratio, color=colors, alpha=0.85)
    for i, r in enumerate(ratio):
        ax.text(r + 0.05, i, f"{r:.2f}× ({ja[i]:.0f} vs {py[i]:.0f})",
                va="center", fontsize=8)
    ax.axvline(1.0, color="black", linestyle="--", linewidth=1.2,
               alpha=0.7)
    ax.set_yticks(y, labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Java / Python ratio (median per instance)")
    ax.set_xlim(0, max(ratio) * 1.45)
    ax.set_title("(f) Per-instance effort (Java / Python)",
                 loc="left", fontsize=11, fontweight="bold")
    ax.grid(True, axis="x", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)


def main() -> None:
    fig = plt.figure(figsize=(16.0, 18))
    gs = fig.add_gridspec(3, 2, hspace=0.40, wspace=0.36,
                          left=0.13, right=0.985,
                          top=0.955, bottom=0.05)
    plot_panel_a(fig.add_subplot(gs[0, 0]))
    plot_panel_b(fig.add_subplot(gs[0, 1]))
    plot_panel_c(fig.add_subplot(gs[1, 0]))
    plot_panel_d(fig.add_subplot(gs[1, 1]))
    plot_panel_e(fig.add_subplot(gs[2, 0]))
    plot_panel_f(fig.add_subplot(gs[2, 1]))

    fig.suptitle(
        "Kozuchi mini-swe-agent + Qwen3.5-27B  —  Python vs. Java side-by-side",
        fontsize=14, fontweight="bold", y=0.985,
    )
    fig.savefig(OUT_PATH, dpi=140)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
