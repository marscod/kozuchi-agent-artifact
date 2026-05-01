"""Generate publication-quality PNG figures from the analysis CSVs.

Design goals (NeurIPS / ICML / ICLR camera-ready style):
  * Single-column (3.3 in), 1.5-column (5 in), and full-width (7 in)
    figures only -- never larger than 7.0 in across.
  * Tight whitespace: ``tight_layout(pad=0.4)`` plus
    ``bbox_inches='tight'`` on save.
  * Numeric value labels are placed *inside* a bar when the bar
    occupies >= 35% of the axis range; otherwise just outside the
    bar tip.  This eliminates the "label hugging the right edge"
    pattern that hurts readability at small widths.
  * Repository and peer-model names are passed through a single
    abbreviation table so they remain short but identifiable.

We avoid seaborn so the script remains dependency-light.

Figures emitted (under ``src/figures/``):

  fig00_overview.png            -- 2x2 paper-grade summary panel.
  fig01_per_repo.png            -- per-repository resolution rate.
  fig02_per_year.png            -- per-year resolution rate.
  fig03_failure_modes.png       -- failure-mode breakdown.
  fig04_patch_loc_buckets.png   -- resolution rate vs LOC churn.
  fig05_effort_buckets.png      -- resolution rate vs api_calls.
  fig06_phase_dynamics.png      -- 1x2: phase activity + GIVEUP rate.
  fig07_correlations.png        -- effort/patch -> success correlations.
  fig08_leaderboard.png         -- top-25 leaderboard.
  fig09_peers.png               -- curated peer comparison.
  fig10_per_repo_vs_peers.png   -- per-repo heatmap vs peers.
  fig11_consensus_vs_rate.png   -- Kozuchi rate by qwen / frontier consensus.
  fig12_consensus_effort.png    -- Kozuchi trajectory effort vs consensus.
  fig13_unresolved_strata.png   -- stratification of the 126 unresolved.
  fig14_effect_sizes.png        -- forest plot of paired effect sizes (log-OR).
  fig15_pareto.png              -- compute-resolution Pareto curve.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from utils import CSV_DIR, FIG_DIR, PHASES_ORDERED, ensure_out_dirs


# ---------------------------------------------------------------------------
# Style and abbreviations
# ---------------------------------------------------------------------------


KOZUCHI_COLOR = "#0072B2"
PEER_COLOR = "#A6A6A6"
FRONTIER_COLOR = "#E69F00"
RESOLVED_COLOR = "#1B9E77"
UNRESOLVED_COLOR = "#D95F02"
GREY = "#444444"


REPO_ABBREV: dict[str, str] = {
    "django/django": "django",
    "sympy/sympy": "sympy",
    "scikit-learn/scikit-learn": "scikit-learn",
    "matplotlib/matplotlib": "matplotlib",
    "sphinx-doc/sphinx": "sphinx",
    "astropy/astropy": "astropy",
    "pydata/xarray": "xarray",
    "pytest-dev/pytest": "pytest",
    "pylint-dev/pylint": "pylint",
    "psf/requests": "requests",
    "mwaskom/seaborn": "seaborn",
    "pallets/flask": "flask",
}


PEER_ABBREV: dict[str, str] = {
    "Kozuchi mini-swe-agent + Qwen3.5-27B": "Kozuchi (Qwen3.5-27B) +TTS@8",
    "EntroPO+R2E (Qwen3-Coder-30B-A3B) +TTS": "EntroPO+R2E (Qwen-30B) +TTS",
    "EntroPO+R2E (Qwen3-Coder-30B-A3B)": "EntroPO+R2E (Qwen-30B)",
    "OpenHands (Qwen3-Coder-30B-A3B)": "OpenHands (Qwen-30B)",
    "OpenHands (Qwen3-Coder-480B-A35B)": "OpenHands (Qwen-480B)",
    "Skywork-SWE-32B +TTS(Bo8)": "Skywork-32B +TTS",
    "Skywork-SWE-32B": "Skywork-32B",
    "DeepSWE-Preview +TTS(Bo16)": "DeepSWE +TTS(Bo16)",
    "DeepSWE-Preview": "DeepSWE",
    "OpenHands + Devstral-Small": "OpenHands + Devstral",
    "SWE-agent + Devstral-Small (2507)": "SWE-agent + Devstral",
    "SWE-agent + SWE-agent-LM-32B": "SWE-agent-LM-32B",
    "Frogboss-32B": "Frogboss-32B",
    "Frogmini-14B": "Frogmini-14B",
    "Z.AI GLM-4.5": "GLM-4.5",
    "Z.AI GLM-4.6": "GLM-4.6",
    "OpenHands + Kimi-K2": "OpenHands + Kimi-K2",
    "Lingxi v1.5 + Kimi-K2": "Lingxi v1.5 + Kimi-K2",
    "OpenHands + Claude-Opus-4.5": "OpenHands + Opus-4.5",
    "live-SWE + Claude-Opus-4.5": "live-SWE + Opus-4.5",
    "Sonar + Claude-Opus-4.5": "Sonar + Opus-4.5",
    "Sonar + Claude-Sonnet-4.5": "Sonar + Sonnet-4.5",
    "live-SWE + Gemini-3-Pro": "live-SWE + Gemini-3-Pro",
    "OpenHands + GPT-5": "OpenHands + GPT-5",
    "OpenHands + Claude-4-Sonnet": "OpenHands + Sonnet-4",
}


def _abbrev_peer(name: str) -> str:
    if name in PEER_ABBREV:
        return PEER_ABBREV[name]
    if len(name) > 32:
        return name[:30] + ".."
    return name


def _abbrev_repo(name: str) -> str:
    return REPO_ABBREV.get(name, name)


def _shorten(s: str, max_len: int = 36) -> str:
    return s if len(s) <= max_len else s[: max_len - 1] + "."


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 200,
            "savefig.dpi": 200,
            "savefig.bbox": "tight",
            "savefig.pad_inches": 0.05,
            "font.family": "DejaVu Sans",
            "font.size": 8.5,
            "axes.titlesize": 9.5,
            "axes.titleweight": "bold",
            "axes.titlepad": 4,
            "axes.labelsize": 8.5,
            "axes.labelpad": 2,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "legend.fontsize": 7.5,
            "legend.frameon": False,
            "legend.handlelength": 1.4,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "xtick.major.size": 2.5,
            "ytick.major.size": 2.5,
            "lines.linewidth": 1.0,
            "errorbar.capsize": 2,
        }
    )


# ---------------------------------------------------------------------------
# Smart bar-label placer
# ---------------------------------------------------------------------------


def _label_horizontal(
    ax: plt.Axes,
    values: Iterable[float],
    suffixes: Iterable[str],
    *,
    in_threshold: float = 0.32,
    pad: float = 0.012,
    color_inside: str = "white",
    color_outside: str = "black",
    fontsize: float = 7.0,
    outside_pos: Iterable[float] | None = None,
) -> None:
    """Place labels for a horizontal bar chart.

    For each bar, place ``label`` inside the bar (right-justified,
    white) if the bar covers at least ``in_threshold`` of the axis
    span; otherwise place it to the right of the bar tip.

    If ``outside_pos`` is supplied (e.g. the upper-CI position), it
    is used as the anchor for outside labels so they never collide
    with error-bar caps.
    """

    xmin, xmax = ax.get_xlim()
    span = xmax - xmin
    values = list(values)
    suffixes = list(suffixes)
    op = list(outside_pos) if outside_pos is not None else values
    for i, (v, lbl, anchor) in enumerate(zip(values, suffixes, op)):
        if v >= xmin + in_threshold * span:
            ax.text(
                v - pad * span,
                i,
                lbl,
                va="center",
                ha="right",
                color=color_inside,
                fontsize=fontsize,
                weight="semibold",
            )
        else:
            ax.text(
                anchor + pad * span,
                i,
                lbl,
                va="center",
                ha="left",
                color=color_outside,
                fontsize=fontsize,
            )


def _label_vertical(
    ax: plt.Axes,
    values: Iterable[float],
    suffixes: Iterable[str],
    *,
    pad: float = 0.012,
    color: str = "black",
    fontsize: float = 6.8,
    outside_pos: Iterable[float] | None = None,
) -> None:
    """Place ``n=...``-style labels above each vertical bar.

    Always-above placement is used because count labels are short
    (1-4 chars) and look cleanest as floating annotations rather
    than over-painted bar interiors.  ``outside_pos`` lets the
    caller anchor labels to the upper-CI position to avoid
    error-bar overlap.
    """

    ymin, ymax = ax.get_ylim()
    span = ymax - ymin
    values = list(values)
    suffixes = list(suffixes)
    op = list(outside_pos) if outside_pos is not None else values
    for i, (lbl, anchor) in enumerate(zip(suffixes, op)):
        ax.text(
            i,
            anchor + pad * span,
            lbl,
            va="bottom",
            ha="center",
            color=color,
            fontsize=fontsize,
        )


# ---------------------------------------------------------------------------
# Per-repo (panel-friendly version + standalone)
# ---------------------------------------------------------------------------


def _draw_per_repo(ax: plt.Axes, df: pd.DataFrame, *, title: str | None = None) -> None:
    df = df.sort_values("n", ascending=True)
    y = np.arange(len(df))
    rates = df["rate"].values
    err_lo = rates - df["ci_lo"].values
    err_hi = df["ci_hi"].values - rates
    ax.barh(y, rates, color=KOZUCHI_COLOR, alpha=0.9, edgecolor="white", height=0.78)
    ax.errorbar(
        rates, y, xerr=[err_lo, err_hi], fmt="none", ecolor=GREY, lw=0.7, capsize=2
    )
    ax.set_yticks(y)
    ax.set_yticklabels([_abbrev_repo(r) for r in df["repo"].tolist()])
    ax.set_xlim(0, 1.18)
    ax.set_xlabel("Resolution rate")
    if title:
        ax.set_title(title)
    ax.axvline(0.748, color="black", linestyle="--", lw=0.7, alpha=0.55)
    ax.text(0.755, len(df) - 0.3, "overall 74.8%", fontsize=6.5, color=GREY)
    labels = [f"{r*100:.1f}%  (n={n})" for r, n in zip(df["rate"], df["n"])]
    _label_horizontal(
        ax,
        df["rate"].values,
        labels,
        in_threshold=0.55,
        pad=0.010,
        fontsize=6.8,
        outside_pos=df["ci_hi"].values,
    )


def fig_per_repo(csv_dir: Path, fig_dir: Path) -> None:
    df = pd.read_csv(csv_dir / "by_repo.csv")
    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    _draw_per_repo(ax, df, title="Per-repository resolution rate")
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig01_per_repo.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Per-year
# ---------------------------------------------------------------------------


def _draw_per_year(
    ax: plt.Axes,
    df: pd.DataFrame,
    *,
    title: str | None = None,
    compact: bool = False,
) -> None:
    """Per-year resolution-rate bar chart.

    ``compact`` controls layout for narrow panels (used inside the
    2x2 overview where the panel is < 3.5 in wide).  In compact
    mode we rotate the year labels 45 degrees and use a smaller
    font so adjacent years no longer collide.
    """

    x = np.arange(len(df))
    rates = df["rate"].values
    err_lo = rates - df["ci_lo"].values
    err_hi = df["ci_hi"].values - rates
    ax.bar(x, rates, color=KOZUCHI_COLOR, alpha=0.9, edgecolor="white", width=0.72)
    ax.errorbar(x, rates, yerr=[err_lo, err_hi], fmt="none", ecolor=GREY, lw=0.7, capsize=2)
    ax.set_xticks(x)
    if compact:
        ax.set_xticklabels(
            df["year"].astype(int).astype(str).tolist(),
            rotation=45,
            ha="right",
            fontsize=6.5,
        )
    else:
        ax.set_xticklabels(df["year"].astype(int).astype(str).tolist())
    ax.set_ylabel("Resolution rate")
    ax.set_ylim(0, 1.18)
    if title:
        ax.set_title(title)
    ax.axhline(0.748, color="black", linestyle="--", lw=0.7, alpha=0.55)
    labels = [f"{int(n)}" for n in df["n"]]
    _label_vertical(ax, rates, labels, pad=0.015, outside_pos=df["ci_hi"].values, fontsize=6.4)


def fig_per_year(csv_dir: Path, fig_dir: Path) -> None:
    df = pd.read_csv(csv_dir / "by_year.csv")
    fig, ax = plt.subplots(figsize=(4.6, 2.4))
    _draw_per_year(ax, df, title="Resolution rate by year of issue")
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig02_per_year.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def fig_failure_modes(csv_dir: Path, fig_dir: Path) -> None:
    df = pd.read_csv(csv_dir / "failure_modes.csv")
    df = df[df["bucket"] != "RESOLVED"].copy().sort_values("n", ascending=True)
    fig, ax = plt.subplots(figsize=(4.6, 2.0))
    y = np.arange(len(df))
    ax.barh(
        y,
        df["n"],
        color=UNRESOLVED_COLOR,
        alpha=0.9,
        edgecolor="white",
        height=0.7,
    )
    ax.set_yticks(y)
    ax.set_yticklabels(df["bucket"].tolist())
    ax.set_xlabel("Unresolved instances (out of 126)")
    ax.set_title("Failure-mode breakdown")
    ax.set_xlim(0, max(df["n"].max() * 1.4, 1))
    labels = [
        f"{int(n)}  ({frac*100:.1f}%)"
        for n, frac in zip(df["n"], df["share_of_unresolved"])
    ]
    _label_horizontal(ax, df["n"].values, labels, in_threshold=0.55, pad=0.012, fontsize=7)
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig03_failure_modes.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# LOC churn buckets
# ---------------------------------------------------------------------------


def _draw_buckets(
    ax: plt.Axes,
    df: pd.DataFrame,
    *,
    xlabel: str,
    title: str | None = None,
) -> None:
    x = np.arange(len(df))
    rates = df["rate"].values
    err_lo = rates - df["ci_lo"].values
    err_hi = df["ci_hi"].values - rates
    ax.bar(x, rates, color=KOZUCHI_COLOR, alpha=0.9, edgecolor="white", width=0.72)
    ax.errorbar(x, rates, yerr=[err_lo, err_hi], fmt="none", ecolor=GREY, lw=0.7, capsize=2)
    ax.set_xticks(x)
    ax.set_xticklabels(df["bucket"].tolist(), rotation=20, ha="right")
    ax.set_ylim(0, 1.18)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Resolution rate")
    if title:
        ax.set_title(title)
    labels = [f"{int(n)}" for n in df["n"]]
    _label_vertical(ax, rates, labels, pad=0.015, outside_pos=df["ci_hi"].values, fontsize=6.6)


def fig_loc_buckets(csv_dir: Path, fig_dir: Path) -> None:
    df = pd.read_csv(csv_dir / "patch_size_buckets.csv")
    fig, ax = plt.subplots(figsize=(4.6, 2.6))
    _draw_buckets(
        ax,
        df,
        xlabel="Patch LOC churn (added + removed)",
        title="Resolution rate vs. patch size",
    )
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig04_patch_loc_buckets.png")
    plt.close(fig)


def fig_effort_buckets(csv_dir: Path, fig_dir: Path) -> None:
    df = pd.read_csv(csv_dir / "effort_buckets.csv")
    df = df[df["n"] > 0]
    fig, ax = plt.subplots(figsize=(4.6, 2.6))
    _draw_buckets(
        ax,
        df,
        xlabel="Per-instance API calls",
        title="Resolution rate vs. inference effort",
    )
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig05_effort_buckets.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Phase activity + GIVEUP rate (combined into a single 2-panel figure)
# ---------------------------------------------------------------------------


def fig_phase_dynamics(csv_dir: Path, fig_dir: Path) -> None:
    phase_short = {
        "ISSUE_REPRODUCT": "Reproduce",
        "TEST_SYNTHSIZE": "Synth.Test",
        "CODE_LOCALIZE": "Loc.Code",
        "TEST_LOCALIZE": "Loc.Test",
        "CODE_FIX": "Fix.Code",
        "VERIFY_PATCH": "Verify",
        "ISSUE_CLOSE": "Close",
        "FINAL_REPORT": "Report",
    }
    dist = pd.read_csv(csv_dir / "phase_distribution.csv")
    gv = pd.read_csv(csv_dir / "phase_giveup_rate.csv")
    dist["i"] = dist["phase"].apply(PHASES_ORDERED.index)
    gv["i"] = gv["phase"].apply(PHASES_ORDERED.index)
    dist = dist.sort_values("i")
    gv = gv.sort_values("i")
    short_phase = [phase_short[p] for p in dist["phase"].tolist()]

    # Explicit gridspec gives us tight control of the inter-panel
    # gap.  ``wspace=0.42`` reserves enough whitespace between the
    # left-panel right ylabel ("Rework factor") and the right-panel
    # left ylabel ("Frac. with >=1 GIVEUP") that they never collide;
    # axis-label padding (``labelpad``) is also bumped so each
    # rotated label clears the adjacent tick numbers.
    fig = plt.figure(figsize=(7.4, 2.9))
    gs = fig.add_gridspec(
        1, 2, wspace=0.42,
        left=0.075, right=0.92, top=0.88, bottom=0.24,
    )
    ax0 = fig.add_subplot(gs[0, 0])
    ax1 = fig.add_subplot(gs[0, 1])

    x = np.arange(len(dist))
    ax0.bar(
        x,
        dist["mean_msgs_per_instance"].values,
        color=KOZUCHI_COLOR,
        alpha=0.9,
        edgecolor="white",
        width=0.7,
    )
    ax0.set_xticks(x)
    ax0.set_xticklabels(short_phase, fontsize=7, rotation=30, ha="right")
    ax0.set_ylabel("Mean msgs / instance", color=KOZUCHI_COLOR, labelpad=4)
    ax0.tick_params(axis="y", labelcolor=KOZUCHI_COLOR)
    ax0.set_title("Per-phase activity + rework factor")

    ax0r = ax0.twinx()
    ax0r.plot(
        x,
        dist["rework_factor"].values,
        "-o",
        color=UNRESOLVED_COLOR,
        markersize=3.5,
        lw=1.0,
    )
    ax0r.set_ylabel("Rework factor", color=UNRESOLVED_COLOR, labelpad=8)
    ax0r.tick_params(axis="y", labelcolor=UNRESOLVED_COLOR, pad=2)
    ax0r.spines["right"].set_visible(True)
    ax0r.spines["top"].set_visible(False)

    rates = gv["rate"].values
    err_lo = rates - gv["ci_lo"].values
    err_hi = gv["ci_hi"].values - rates
    ax1.bar(x, rates, color=UNRESOLVED_COLOR, alpha=0.9, edgecolor="white", width=0.7)
    ax1.errorbar(x, rates, yerr=[err_lo, err_hi], fmt="none", ecolor=GREY, lw=0.7, capsize=2)
    ax1.set_xticks(x)
    ax1.set_xticklabels(short_phase, fontsize=7, rotation=30, ha="right")
    ax1.set_ylabel("Frac. with >=1 GIVEUP", labelpad=4)
    ax1.set_ylim(0, max(0.30, gv["ci_hi"].max() + 0.04))
    ax1.set_title("Per-phase rollback rate")
    labels = [f"k={int(k)}" if k > 0 else "" for k in gv["instances_with_giveup"].values]
    _label_vertical(ax1, rates, labels, pad=0.012, outside_pos=gv["ci_hi"].values, fontsize=6.5)

    fig.savefig(fig_dir / "fig06_phase_dynamics.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Correlations
# ---------------------------------------------------------------------------


def fig_correlations(csv_dir: Path, fig_dir: Path) -> None:
    df = pd.read_csv(csv_dir / "effort_resolution_corr.csv")
    df = df.sort_values("pointbiserial_r", ascending=True).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(4.6, 2.8))
    y = np.arange(len(df))
    colors = ["#D95F02" if r < 0 else "#1B9E77" for r in df["pointbiserial_r"]]
    ax.barh(y, df["pointbiserial_r"], color=colors, alpha=0.9, edgecolor="white", height=0.72)
    ax.axvline(0, color="black", lw=0.7)
    for i, (r, p) in enumerate(zip(df["pointbiserial_r"], df["pointbiserial_p"])):
        sig = "*" if p < 0.05 else ""
        ax.text(0.003, i, f"{r:+.3f}{sig}", va="center", ha="left", fontsize=6.8)
    ax.set_yticks(y)
    ax.set_yticklabels(df["metric"].tolist(), fontsize=7)
    ax.set_xlabel("Point-biserial r with resolution (* p<0.05)")
    ax.set_title("Effort & patch features vs. success")
    rmin = df["pointbiserial_r"].min()
    ax.set_xlim(min(rmin * 1.18, -0.05), 0.10)
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig07_correlations.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Leaderboard (top 25, compact)
# ---------------------------------------------------------------------------


def fig_leaderboard(csv_dir: Path, fig_dir: Path) -> None:
    df = pd.read_csv(csv_dir / "leaderboard.csv").head(25).copy().iloc[::-1]
    fig, ax = plt.subplots(figsize=(5.4, 4.6))
    y = np.arange(len(df))
    is_kozuchi = df["submission_dir"].astype(str).str.contains("kozuchi", case=False)
    colors = [KOZUCHI_COLOR if k else PEER_COLOR for k in is_kozuchi]
    ax.barh(y, df["resolved"].values, color=colors, alpha=0.95, edgecolor="white", height=0.78)
    ax.set_yticks(y)
    ax.set_yticklabels([_shorten(str(n), 36) for n in df["name"].tolist()], fontsize=7)
    ax.set_xlim(0, 500 * 1.04)
    ax.set_xlabel("Resolved on Verified-500")
    ax.set_title("Top-25 SWE-bench Verified leaderboard")
    labels = [f"{int(v)}" for v in df["resolved"]]
    _label_horizontal(
        ax,
        df["resolved"].values,
        labels,
        in_threshold=0.55,
        pad=0.005,
        fontsize=6.5,
    )
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig08_leaderboard.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Peers (curated)
# ---------------------------------------------------------------------------


def fig_peers(csv_dir: Path, fig_dir: Path) -> None:
    df = pd.read_csv(csv_dir / "peers.csv").sort_values("resolved", ascending=True).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(5.6, 4.4))
    y = np.arange(len(df))
    colors = [
        KOZUCHI_COLOR
        if "Kozuchi" in str(n)
        else (FRONTIER_COLOR if str(c) == "closed" else PEER_COLOR)
        for n, c in zip(df["name"], df["weight_class"])
    ]
    rates = df["rate"].values
    err_lo = rates - df["ci_lo"].values
    err_hi = df["ci_hi"].values - rates
    ax.barh(y, rates, color=colors, alpha=0.95, edgecolor="white", height=0.78)
    ax.errorbar(rates, y, xerr=[err_lo, err_hi], fmt="none", ecolor=GREY, lw=0.7, capsize=2)
    ax.set_yticks(y)
    ax.set_yticklabels([_abbrev_peer(str(n)) for n in df["name"].tolist()], fontsize=7)
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("Resolution rate (Wilson 95% CI)")
    ax.set_title("Kozuchi vs. open-weight peers and frontier")
    labels = [f"{r*100:.1f}%" for r in rates]
    _label_horizontal(
        ax,
        rates,
        labels,
        in_threshold=0.65,
        pad=0.008,
        fontsize=6.6,
        outside_pos=df["ci_hi"].values,
    )
    # Legend swatches.
    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, color=KOZUCHI_COLOR, label="Kozuchi (ours)"),
        plt.Rectangle((0, 0), 1, 1, color=PEER_COLOR, label="Open-weight peer"),
        plt.Rectangle((0, 0), 1, 1, color=FRONTIER_COLOR, label="Closed-source frontier"),
    ]
    ax.legend(handles=legend_handles, loc="lower right", fontsize=7)
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig09_peers.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Per-repo heatmap vs peers
# ---------------------------------------------------------------------------


def fig_per_repo_vs_peers(csv_dir: Path, fig_dir: Path) -> None:
    df = pd.read_csv(csv_dir / "per_repo_vs_peers.csv")
    rate_cols = [c for c in df.columns if c.endswith("_rate")]
    matrix = df[rate_cols].values
    repos = [_abbrev_repo(r) for r in df["repo"].tolist()]
    model_full_names = [c[: -len("_rate")] for c in rate_cols]
    # Replace internal label with short alias.
    labels = []
    for n in model_full_names:
        labels.append(PEER_ABBREV.get(n, n))

    fig, ax = plt.subplots(figsize=(7.0, 3.5))
    im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)
    ax.set_xticks(np.arange(len(labels)))
    ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=7)
    ax.set_yticks(np.arange(len(repos)))
    ax.set_yticklabels(repos, fontsize=7.5)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix[i, j]
            ax.text(
                j,
                i,
                f"{v*100:.0f}",
                ha="center",
                va="center",
                fontsize=6.2,
                color="white" if v < 0.42 or v > 0.85 else "black",
            )
    cbar = fig.colorbar(im, ax=ax, fraction=0.022, pad=0.015)
    cbar.set_label("Per-repo resolution rate", fontsize=7.5)
    cbar.ax.tick_params(labelsize=7)
    ax.set_title("Per-repository resolution rate -- Kozuchi vs open-weight peers")
    # Highlight Kozuchi column.
    if "Kozuchi" in labels:
        kj = labels.index("Kozuchi")
        ax.add_patch(
            plt.Rectangle(
                (kj - 0.5, -0.5),
                1,
                matrix.shape[0],
                fill=False,
                edgecolor=KOZUCHI_COLOR,
                lw=1.6,
            )
        )
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig10_per_repo_vs_peers.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Cross-experiment figures: Kozuchi vs Qwen / frontier consensus
# ---------------------------------------------------------------------------


def fig_consensus_vs_rate(csv_dir: Path, fig_dir: Path) -> None:
    """Two-panel figure: Kozuchi resolution rate as a function of how
    many *Qwen peers* (left) and how many *frontier closed systems*
    (right) also resolve the same instance.

    The point: if Kozuchi's success curve rises steeply with peer
    consensus, then most of Kozuchi's wins coincide with what the
    rest of the field already finds easy.  A non-trivial bar at
    consensus = 0 signals that Kozuchi adds *novel* solves on top
    of every other Qwen peer.
    """

    df = pd.read_csv(csv_dir / "qwen_consensus_summary.csv")
    qw = df[df["axis"] == "qwen_consensus"].sort_values("consensus")
    fr = df[df["axis"] == "frontier_consensus"].sort_values("consensus")

    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(7.0, 2.8))

    for ax, sub, xlabel, title, n_peers in [
        (ax0, qw, "# Qwen peers also resolving (out of 4)", "(a) vs. Qwen-family peers", 4),
        (ax1, fr, "# Frontier (closed) systems resolving (out of 7)", "(b) vs. closed frontier", 7),
    ]:
        x = np.arange(len(sub))
        ax.bar(
            x,
            sub["kozuchi_rate"].values,
            color=KOZUCHI_COLOR,
            alpha=0.9,
            edgecolor="white",
            width=0.72,
        )
        ax.set_xticks(x)
        ax.set_xticklabels([str(int(c)) for c in sub["consensus"]])
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Kozuchi resolution rate")
        ax.set_ylim(0, 1.18)
        ax.set_title(title)
        labels = [f"{int(n)}" for n in sub["n_instances"]]
        _label_vertical(
            ax,
            sub["kozuchi_rate"].values,
            labels,
            pad=0.018,
            outside_pos=sub["kozuchi_rate"].values,
            fontsize=6.6,
        )
        ax.axhline(0.748, color="black", linestyle="--", lw=0.7, alpha=0.55)

    fig.suptitle(
        "Kozuchi resolution rate stratified by external consensus",
        fontsize=10,
        y=1.00,
        weight="bold",
    )
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig11_consensus_vs_rate.png")
    plt.close(fig)


def fig_consensus_effort(csv_dir: Path, fig_dir: Path) -> None:
    """Two-panel figure: Kozuchi's *trajectory effort* as a function
    of Qwen peer consensus.

    Left:  median + mean api_calls per instance, by consensus.
    Right: median + mean patch LOC churn, by consensus.

    Reads ``kozuchi_traj_by_qwen_consensus.csv``.  Trajectories are
    only available for Kozuchi (other peers do not ship traces), so
    we only plot Kozuchi.  The *consensus* axis carries the cross-
    experiment information indirectly: high consensus = the rest of
    the Qwen family also resolved this instance, low consensus =
    only Kozuchi (or nobody).
    """

    df = pd.read_csv(csv_dir / "kozuchi_traj_by_qwen_consensus.csv").sort_values(
        "qwen_consensus"
    )
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(7.0, 2.8))
    x = np.arange(len(df))

    ax0.bar(
        x - 0.18,
        df["api_calls_p50"].values,
        width=0.36,
        color=KOZUCHI_COLOR,
        alpha=0.95,
        edgecolor="white",
        label="median",
    )
    ax0.bar(
        x + 0.18,
        df["api_calls_mean"].values,
        width=0.36,
        color="#9DC4E2",
        alpha=0.95,
        edgecolor="white",
        label="mean",
    )
    ax0.set_xticks(x)
    ax0.set_xticklabels([str(int(c)) for c in df["qwen_consensus"]])
    ax0.set_xlabel("# Qwen peers also resolving")
    ax0.set_ylabel("API calls per instance")
    ax0.set_title("(a) Inference effort vs. peer consensus")
    ax0.legend(fontsize=7, loc="upper right")

    ax1.bar(
        x - 0.18,
        df["patch_churn_p50"].values,
        width=0.36,
        color=RESOLVED_COLOR,
        alpha=0.95,
        edgecolor="white",
        label="median",
    )
    ax1.bar(
        x + 0.18,
        df["patch_churn_mean"].values,
        width=0.36,
        color="#A1D7BD",
        alpha=0.95,
        edgecolor="white",
        label="mean",
    )
    ax1.set_xticks(x)
    ax1.set_xticklabels([str(int(c)) for c in df["qwen_consensus"]])
    ax1.set_xlabel("# Qwen peers also resolving")
    ax1.set_ylabel("Patch LOC churn")
    ax1.set_title("(b) Patch size vs. peer consensus")
    ax1.legend(fontsize=7, loc="upper right")

    fig.suptitle(
        "Kozuchi trajectory effort vs. Qwen-peer consensus",
        fontsize=10,
        y=1.00,
        weight="bold",
    )
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig12_consensus_effort.png")
    plt.close(fig)


def fig_unresolved_strata(csv_dir: Path, fig_dir: Path) -> None:
    """Two-panel figure that decomposes Kozuchi's 126 unresolved
    instances by external consensus.

    Left:  stratification donut -- how many of the 126 are solved
    by another Qwen peer ("Qwen blind spot"), how many require a
    *frontier* (closed) system ("frontier-only"), and how many are
    *globally hard* (nobody in the curated set solves them).

    Right: per-repo *frontier solve share* -- of the Kozuchi-
    unresolved instances in each repo, what fraction does the
    closed frontier collectively solve?  A high bar means that
    repository's residual is solvable but blocked by backbone
    quality, not by scaffold design.
    """

    strata = pd.read_csv(csv_dir / "kozuchi_unresolved_strata.csv")
    strata = strata[strata["stratum"] != "TOTAL"].copy()
    fs = pd.read_csv(csv_dir / "frontier_solve_share.csv")
    fs = fs[fs["kozuchi_unresolved"] >= 1].sort_values(
        "kozuchi_unresolved", ascending=True
    )

    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(7.0, 3.0))

    color_map = {
        "peer_qwen_solved": "#A6A6A6",
        "frontier_only": FRONTIER_COLOR,
        "globally_hard": "#7B0033",
    }
    pretty = {
        "peer_qwen_solved": "Another Qwen peer\nresolves it",
        "frontier_only": "Frontier (closed)\nresolves it",
        "globally_hard": "Globally hard\n(nobody resolves)",
    }
    colors = [color_map[s] for s in strata["stratum"]]
    labels = [pretty[s] for s in strata["stratum"]]
    wedges, _ = ax0.pie(
        strata["n"],
        labels=None,
        colors=colors,
        startangle=90,
        wedgeprops=dict(width=0.42, edgecolor="white", linewidth=1.2),
    )
    ax0.set_title("(a) 126 unresolved Kozuchi instances")
    leg_labels = [
        f"{lbl}\nn={int(n)}  ({sh*100:.1f}%)"
        for lbl, n, sh in zip(labels, strata["n"], strata["share"])
    ]
    ax0.legend(
        wedges,
        leg_labels,
        loc="center left",
        bbox_to_anchor=(1.0, 0.5),
        fontsize=7.0,
        frameon=False,
        handlelength=1.2,
        labelspacing=0.9,
    )
    ax0.text(
        0,
        0,
        "126\nunresolved",
        ha="center",
        va="center",
        fontsize=8.5,
        weight="bold",
        color=GREY,
    )

    y = np.arange(len(fs))
    ax1.barh(
        y,
        fs["frontier_share"].values,
        color=FRONTIER_COLOR,
        alpha=0.95,
        edgecolor="white",
        height=0.72,
    )
    ax1.set_yticks(y)
    ax1.set_yticklabels([_abbrev_repo(r) for r in fs["repo"]], fontsize=7)
    ax1.set_xlim(0, 1.18)
    ax1.set_xlabel("Frontier solve share of Kozuchi-unresolved")
    ax1.set_title("(b) Backbone-quality gap by repository")
    labels = [
        f"{int(s*100)}%  ({int(fr)}/{int(n)})"
        for s, fr, n in zip(
            fs["frontier_share"], fs["frontier_solved"], fs["kozuchi_unresolved"]
        )
    ]
    _label_horizontal(
        ax1,
        fs["frontier_share"].values,
        labels,
        in_threshold=0.55,
        pad=0.012,
        fontsize=7,
        outside_pos=fs["frontier_share"].values,
    )
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig13_unresolved_strata.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Statistical figures: effect-size forest + compute-resolution Pareto
# ---------------------------------------------------------------------------


def fig_effect_sizes(csv_dir: Path, fig_dir: Path) -> None:
    """Forest plot of paired effect sizes (log odds ratio) with 95 % CI.

    Reads ``paired_effect_sizes.csv`` written by analyze_statistics.
    Each row is a peer comparison; the marker is the conditional
    odds ratio b/c (mapped to log-OR) with whiskers at the exact
    Clopper-Pearson 95 % CI.  Asterisks annotate the BH-FDR
    significance status: ``***`` = q < 0.001, ``**`` < 0.01,
    ``*`` < 0.05, ``ns`` otherwise.
    """

    df = pd.read_csv(csv_dir / "multiple_comparison_corrected.csv")
    df["log_or"] = np.log(df["odds_ratio"].clip(lower=1e-3, upper=1e3))
    df["log_or_lo"] = np.log(df["odds_ratio_lo"].clip(lower=1e-3, upper=1e3))
    df["log_or_hi"] = np.log(df["odds_ratio_hi"].clip(lower=1e-3, upper=1e3))
    df = df.sort_values("log_or", ascending=True).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(6.0, 5.6))
    y = np.arange(len(df))
    colors = [FRONTIER_COLOR if c == "closed" else PEER_COLOR for c in df["weight_class"]]
    ax.errorbar(
        df["log_or"],
        y,
        xerr=[df["log_or"] - df["log_or_lo"], df["log_or_hi"] - df["log_or"]],
        fmt="o",
        color="black",
        ecolor=GREY,
        markersize=4,
        capsize=2.5,
        lw=0.9,
    )
    for i, c in enumerate(colors):
        ax.scatter(df["log_or"].iloc[i], y[i], s=28, color=c, zorder=3, edgecolor="white", lw=0.6)
    ax.axvline(0, color="black", lw=0.7, alpha=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(
        [f"{_abbrev_peer(str(p))}" for p in df["peer"]],
        fontsize=7,
    )
    ax.set_xlabel("log odds ratio (Kozuchi vs peer; conditional, paired)\nWhiskers: exact Clopper-Pearson 95% CI")
    ax.set_title("Paired effect-size forest plot (Kozuchi vs 24 peers)")

    def _stars(q: float) -> str:
        if q < 1e-3:
            return "***"
        if q < 1e-2:
            return "**"
        if q < 0.05:
            return "*"
        return "n.s."

    xmax = df["log_or_hi"].max()
    for i, q in enumerate(df["bh_fdr_q"]):
        ax.text(
            xmax + 0.18,
            i,
            _stars(q),
            va="center",
            ha="left",
            fontsize=7,
            color=GREY,
        )
    ax.set_xlim(df["log_or_lo"].min() - 0.4, xmax + 1.0)

    legend_handles = [
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=PEER_COLOR, markersize=6, label="Open-weight peer"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=FRONTIER_COLOR, markersize=6, label="Closed-source frontier"),
    ]
    ax.legend(handles=legend_handles, loc="lower right", fontsize=7)

    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig14_effect_sizes.png")
    plt.close(fig)


def fig_pareto(csv_dir: Path, fig_dir: Path) -> None:
    """Compute-resolution Pareto curve.

    Reads ``compute_resolution_pareto.csv``: for each api-call
    budget X, the share of the 374 resolved instances Kozuchi
    finishes within X calls.  Annotated with the budget needed to
    reach 50 / 80 / 95 / 99 % of the resolved set.
    """

    df = pd.read_csv(csv_dir / "compute_resolution_pareto.csv")
    df = df[df["resolved_share_of_374"] > 0]
    fig, ax = plt.subplots(figsize=(5.4, 3.0))
    ax.plot(df["api_call_budget"], df["resolved_share_of_374"], color=KOZUCHI_COLOR, lw=1.4)
    ax.fill_between(
        df["api_call_budget"], 0, df["resolved_share_of_374"], color=KOZUCHI_COLOR, alpha=0.16
    )
    ax.set_xlabel("Per-instance API-call budget (cap)")
    ax.set_ylabel("Share of resolved instances finished")
    ax.set_title("Compute-resolution Pareto curve (374 resolved)")
    ax.set_ylim(0, 1.06)
    ax.set_xlim(left=0)
    for thresh, name in [(0.5, "50%"), (0.8, "80%"), (0.95, "95%"), (0.99, "99%")]:
        # First api_call budget where share >= thresh.
        sub = df[df["resolved_share_of_374"] >= thresh]
        if not len(sub):
            continue
        x = int(sub["api_call_budget"].iloc[0])
        ax.axvline(x, ls="--", lw=0.6, color=GREY, alpha=0.5)
        ax.text(x, thresh + 0.012, f"{name} @ {x}", fontsize=6.5, ha="left", color=GREY)
        ax.scatter([x], [thresh], color=UNRESOLVED_COLOR, s=18, zorder=3)

    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig15_pareto.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 2x2 paper-grade overview panel (NEW).
# ---------------------------------------------------------------------------


def fig_overview(csv_dir: Path, fig_dir: Path) -> None:
    """Single 2x2 figure intended for the main paper or talk slide.

    Top row: per-repo + per-year resolution rates.
    Bottom row: patch-LOC bucket + api-call bucket rates.
    """

    by_repo = pd.read_csv(csv_dir / "by_repo.csv")
    by_year = pd.read_csv(csv_dir / "by_year.csv")
    loc = pd.read_csv(csv_dir / "patch_size_buckets.csv")
    eff = pd.read_csv(csv_dir / "effort_buckets.csv")
    eff = eff[eff["n"] > 0]

    fig = plt.figure(figsize=(7.0, 5.8), constrained_layout=False)
    # Generous top margin (top=0.88) gives ~4 line-heights between the
    # bold suptitle at y=0.965 and the panel titles below.  hspace=0.70
    # keeps the rotated x-axis labels in (b) clear of the (d) panel
    # title underneath.
    gs = fig.add_gridspec(
        2, 2, hspace=0.70, wspace=0.28,
        left=0.075, right=0.985, top=0.88, bottom=0.10,
    )
    ax_r = fig.add_subplot(gs[0, 0])
    ax_y = fig.add_subplot(gs[0, 1])
    ax_l = fig.add_subplot(gs[1, 0])
    ax_e = fig.add_subplot(gs[1, 1])

    _draw_per_repo(ax_r, by_repo, title="(a) Per-repository resolution rate")
    _draw_per_year(ax_y, by_year, title="(b) Resolution by year of issue", compact=True)
    _draw_buckets(
        ax_l,
        loc,
        xlabel="Patch LOC churn",
        title="(c) Resolution rate vs. patch size",
    )
    _draw_buckets(
        ax_e,
        eff,
        xlabel="Per-instance API calls",
        title="(d) Resolution rate vs. inference effort",
    )

    fig.suptitle(
        "Kozuchi (Qwen3.5-27B, TTS@8) -- 74.80% (374/500) on SWE-bench Verified",
        fontsize=11.5,
        y=0.965,
        weight="bold",
    )
    fig.savefig(fig_dir / "fig00_overview.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# §11 TTS@8 candidate-level figures (NEW).
# ---------------------------------------------------------------------------


def fig_tts_per_leg(csv_dir: Path, fig_dir: Path) -> None:
    """Per-leg pass rates with selector and oracle reference lines.

    Reads:
      - tts_per_leg.csv
      - tts_oracle_summary.csv
    """
    df = pd.read_csv(csv_dir / "tts_per_leg.csv")
    summary = pd.read_csv(csv_dir / "tts_oracle_summary.csv")

    sel_rate = float(
        summary.loc[summary["metric"] == "selector_resolved", "value"].iloc[0]
    ) / 500.0
    oracle_rate = float(
        summary.loc[summary["metric"] == "oracle_resolved_any_leg", "value"].iloc[0]
    ) / 500.0

    labels = [lab.split("_")[0] for lab in df["leg"]]
    rates = df["rate"].values
    err_lo = rates - df["ci_lo"].values
    err_hi = df["ci_hi"].values - rates
    err = np.vstack([err_lo, err_hi])

    fig, ax = plt.subplots(figsize=(5.4, 3.0))
    x = np.arange(len(rates))
    bars = ax.bar(x, rates, color=KOZUCHI_COLOR, alpha=0.85, edgecolor="white")
    ax.errorbar(x, rates, yerr=err, fmt="none", ecolor=GREY, lw=0.9, capsize=2.5)

    ax.axhline(
        sel_rate, color=RESOLVED_COLOR, lw=1.2, ls="-",
        label=f"TTS@8 selector pass@1 = {sel_rate:.1%}",
    )
    ax.axhline(
        oracle_rate, color=UNRESOLVED_COLOR, lw=1.2, ls="--",
        label=f"oracle pass@8 ceiling = {oracle_rate:.1%}",
    )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7.5)
    ax.set_ylabel("Resolution rate")
    ax.set_title("Per-leg pass@1 vs. TTS@8 selector vs. oracle pass@8")
    ax.set_ylim(0.55, oracle_rate + 0.04)
    for xi, r in zip(x, rates):
        ax.text(xi, r + 0.003, f"{r:.1%}", ha="center", va="bottom", fontsize=6.8, color=GREY)
    ax.legend(loc="upper right", fontsize=7.0)
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig16_tts_per_leg.png")
    plt.close(fig)


def fig_tts_pass_at_k(csv_dir: Path, fig_dir: Path) -> None:
    """Closed-form oracle pass@k curve plus selector reference points.

    Two annotations: (a) the selector's actual pass@1 with K = 8 legs,
    placed at K = 8 on a separate marker; and (b) the equivalent
    oracle K such that oracle pass@K matches the selector's headline.
    """
    df = pd.read_csv(csv_dir / "tts_pass_at_k_oracle.csv")
    summary = pd.read_csv(csv_dir / "tts_oracle_summary.csv")
    sel_rate = float(
        summary.loc[summary["metric"] == "selector_resolved", "value"].iloc[0]
    ) / 500.0

    fig, ax = plt.subplots(figsize=(5.4, 3.0))
    ax.plot(df["k"], df["expected_rate"], color=KOZUCHI_COLOR, lw=1.4,
            marker="o", markersize=4.0, label="oracle pass@k (closed-form expectation)")
    ax.scatter([8], [sel_rate], color=RESOLVED_COLOR, s=42, zorder=5,
               label=f"TTS@8 selector pass@1 = {sel_rate:.1%}")

    # Equivalent oracle K: smallest k such that expected_rate >= sel_rate.
    eq = df[df["expected_rate"] >= sel_rate]
    if len(eq):
        k_eq = int(eq["k"].iloc[0])
        rate_eq = float(eq["expected_rate"].iloc[0])
        ax.axhline(sel_rate, color=GREY, ls=":", lw=0.7, alpha=0.6)
        ax.axvline(k_eq, color=GREY, ls=":", lw=0.7, alpha=0.6)
        ax.text(k_eq + 0.05, sel_rate - 0.013,
                f"selector $\\equiv$ oracle@{k_eq}", color=GREY, fontsize=6.8)

    for k, r in zip(df["k"], df["expected_rate"]):
        ax.text(k, r + 0.006, f"{r:.1%}", ha="center", va="bottom",
                fontsize=6.5, color=GREY)

    ax.set_xlabel("k legs sampled (without replacement)")
    ax.set_ylabel("Expected oracle pass@k")
    ax.set_xticks(list(range(1, 9)))
    ax.set_ylim(0.6, 0.86)
    ax.set_title("Oracle pass@k curve and TTS@8 selector position")
    ax.legend(loc="lower right", fontsize=7.0)
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig17_pass_at_k.png")
    plt.close(fig)


def fig_tts_resolve_distribution(csv_dir: Path, fig_dir: Path) -> None:
    """Distribution of r_i (#legs resolving) and oracle vs. selector overlay.

    Two-panel figure:
      (a) Histogram of r_count = 0..8 with cumulative share annotation.
      (b) Per-r_count selector vs. oracle resolution rate.

    Together they make visible (i) the bimodality at r=0 and r=8,
    (ii) the marginal r in 1..7 where selection matters.
    """
    rdist = pd.read_csv(csv_dir / "tts_resolve_count_distribution.csv")
    per_inst = pd.read_csv(csv_dir / "tts_per_instance_outcomes.csv")
    # Selector outcomes are recovered directly from the canonical
    # post-merge harness re-eval (results/results.json), so the
    # figure stays consistent with the headline 374 reported in §1.
    res_path = csv_dir.parent.parent / "results" / "results.json"
    final = set(json.loads(res_path.read_text())["resolved"])
    per_inst["selector_resolved"] = per_inst["instance_id"].isin(final).astype(int)

    # Panel B: per r_count selector and oracle rate.
    grouped = (
        per_inst.groupby("r_count")
        .agg(n=("instance_id", "count"),
             selector=("selector_resolved", "sum"))
        .reset_index()
    )
    grouped["selector_rate"] = grouped["selector"] / grouped["n"]
    # Oracle rate by r_count: 1.0 if r_count >= 1, 0.0 otherwise.
    grouped["oracle_rate"] = (grouped["r_count"] >= 1).astype(float)

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.0))

    ax_a, ax_b = axes
    bars = ax_a.bar(rdist["r_count"], rdist["n_instances"],
                    color=KOZUCHI_COLOR, alpha=0.85, edgecolor="white")
    ax_a.set_xticks(list(range(0, 9)))
    ax_a.set_xlabel("# of 8 legs that resolve")
    ax_a.set_ylabel("# of Verified instances")
    ax_a.set_title("(a) Per-instance resolve count distribution")
    for r, n in zip(rdist["r_count"], rdist["n_instances"]):
        ax_a.text(r, n + 4, f"{int(n)}", ha="center", va="bottom",
                  fontsize=6.8, color=GREY)
    # Highlight the bimodality regions.
    ax_a.axvspan(-0.5, 0.5, color=UNRESOLVED_COLOR, alpha=0.06)
    ax_a.axvspan(7.5, 8.5, color=RESOLVED_COLOR, alpha=0.07)
    ax_a.text(0, max(rdist["n_instances"]) * 0.78, "scaffold-hard",
              ha="center", fontsize=6.5, color=UNRESOLVED_COLOR)
    ax_a.text(8, max(rdist["n_instances"]) * 0.78, "scaffold-easy",
              ha="center", fontsize=6.5, color=RESOLVED_COLOR)

    width = 0.4
    rxs = grouped["r_count"].values
    ax_b.bar(rxs - width / 2, grouped["selector_rate"], width=width,
             color=RESOLVED_COLOR, label="TTS@8 selector", alpha=0.85)
    ax_b.bar(rxs + width / 2, grouped["oracle_rate"], width=width,
             color=UNRESOLVED_COLOR, label="oracle (any leg)", alpha=0.85)
    ax_b.set_xticks(list(range(0, 9)))
    ax_b.set_ylim(0, 1.05)
    ax_b.set_xlabel("# of 8 legs that resolve")
    ax_b.set_ylabel("resolution rate within bin")
    ax_b.set_title("(b) Selector vs. oracle within each r-bin")
    ax_b.legend(loc="lower right", fontsize=7.0)

    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig18_tts_resolve_distribution.png")
    plt.close(fig)


def fig_tts_leg_jaccard(csv_dir: Path, fig_dir: Path) -> None:
    """8x8 leg-pair Jaccard agreement heatmap.

    Each cell is |R_i ∩ R_j| / |R_i ∪ R_j| where R_i is leg i's
    resolved set.  Diagonal forced to 1.  Annotated with values.
    """
    df = pd.read_csv(csv_dir / "tts_leg_jaccard.csv")
    legs = df["leg"].tolist()
    M = df.drop(columns=["leg"]).values

    fig, ax = plt.subplots(figsize=(4.4, 3.5))
    im = ax.imshow(M, cmap="viridis", vmin=0.78, vmax=1.0, aspect="equal")
    short = [l.split("_")[0] for l in legs]
    ax.set_xticks(np.arange(len(legs)))
    ax.set_xticklabels(short, rotation=45, ha="right", fontsize=7.0)
    ax.set_yticks(np.arange(len(legs)))
    ax.set_yticklabels(short, fontsize=7.0)
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            v = M[i, j]
            ax.text(j, i, f"{v:.2f}",
                    ha="center", va="center",
                    color="white" if v < 0.92 else "black", fontsize=6.5)
    cbar = fig.colorbar(im, ax=ax, fraction=0.044, pad=0.04)
    cbar.set_label("Jaccard(R_i, R_j)", fontsize=7.5)
    ax.set_title("Pairwise leg agreement on resolved sets")
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig19_leg_jaccard.png")
    plt.close(fig)


def fig_tts_oracle_vs_selector(csv_dir: Path, fig_dir: Path) -> None:
    """Per-repo oracle vs. selector resolved counts plus regret bar.

    Two-panel figure.  Left: side-by-side bars per repo. Right:
    diversity-vs-outcome (the n_unique_patches relationship to the
    selector vs oracle gap).
    """
    repo_df = pd.read_csv(csv_dir / "tts_per_repo_oracle_vs_selector.csv")
    repo_df = repo_df.sort_values("n", ascending=True).reset_index(drop=True)
    div = pd.read_csv(csv_dir / "tts_diversity_vs_outcome.csv")
    div = div[div["n_unique_patches"] >= 1]

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.4))
    ax_a, ax_b = axes

    ys = np.arange(len(repo_df))
    width = 0.4
    ax_a.barh(ys + width / 2, repo_df["selector_rate"], height=width,
              color=RESOLVED_COLOR, label="TTS@8 selector")
    ax_a.barh(ys - width / 2, repo_df["oracle_rate"], height=width,
              color=UNRESOLVED_COLOR, label="oracle (any leg)")
    ax_a.set_yticks(ys)
    ax_a.set_yticklabels([_abbrev_repo(r) for r in repo_df["repo"]])
    ax_a.set_xlabel("Resolution rate")
    ax_a.set_xlim(0, 1.06)
    ax_a.set_title("(a) Per-repo selector vs. oracle pass-rate")
    for y, sel, orr, regret in zip(ys, repo_df["selector_rate"],
                                   repo_df["oracle_rate"], repo_df["regret"]):
        ax_a.text(orr + 0.012, y - width / 2, f"{orr:.0%}",
                  va="center", fontsize=6.5, color=GREY)
        ax_a.text(sel + 0.012, y + width / 2, f"{sel:.0%}",
                  va="center", fontsize=6.5, color=GREY)
        if regret:
            ax_a.text(0.02, y, f"-{int(regret)}", va="center", fontsize=6.5,
                      color=UNRESOLVED_COLOR, alpha=0.7)
    ax_a.legend(loc="lower right", fontsize=7.0)

    # (b) diversity vs outcome
    ax_b.plot(div["n_unique_patches"], div["selector_rate"],
              color=RESOLVED_COLOR, marker="o", lw=1.3,
              label="selector pass-rate")
    ax_b.plot(div["n_unique_patches"], div["oracle_rate"],
              color=UNRESOLVED_COLOR, marker="s", lw=1.3, ls="--",
              label="oracle pass-rate")
    ax_b.fill_between(div["n_unique_patches"], div["selector_rate"],
                      div["oracle_rate"], color="grey", alpha=0.15,
                      label="selector regret region")
    ax_b.set_xticks(list(range(1, 9)))
    ax_b.set_xlabel("# unique deduplicated patches across the 8 legs")
    ax_b.set_ylabel("Resolution rate")
    ax_b.set_ylim(0.55, 1.02)
    ax_b.set_title("(b) Diversity $\\to$ regret")
    for nu, n in zip(div["n_unique_patches"], div["n_instances"]):
        ax_b.text(nu, 0.575, f"n={int(n)}", ha="center", fontsize=6.0,
                  color=GREY, alpha=0.85)
    ax_b.legend(loc="lower left", fontsize=7.0)

    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig20_oracle_vs_selector.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# §12 Conversation-level figures (NEW).
# ---------------------------------------------------------------------------


def fig_conv_lengths(csv_dir: Path, fig_dir: Path) -> None:
    """Conversation length distributions split by outcome.

    Three-panel figure:
      (a) Histogram + violin of n_messages by outcome.
      (b) CDF of n_bash_total by outcome.
      (c) Per-instance bash failure-rate (rc != 0) by outcome.
    """
    df = pd.read_csv(csv_dir / "conv_per_instance.csv")
    res = df[df["resolved"] == 1]
    unr = df[df["resolved"] == 0]

    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.7))
    ax_a, ax_b, ax_c = axes

    # (a) overlapping histograms.
    bins = np.linspace(df["n_messages"].min(), df["n_messages"].max(), 30)
    ax_a.hist(res["n_messages"], bins=bins, color=RESOLVED_COLOR, alpha=0.6,
              label=f"resolved (n={len(res)})", edgecolor="white", linewidth=0.4)
    ax_a.hist(unr["n_messages"], bins=bins, color=UNRESOLVED_COLOR, alpha=0.6,
              label=f"unresolved (n={len(unr)})", edgecolor="white", linewidth=0.4)
    ax_a.set_xlabel("# messages per trajectory")
    ax_a.set_ylabel("# trajectories")
    ax_a.set_title("(a) Conversation length")
    ax_a.legend(loc="upper right", fontsize=6.5)

    # (b) bash CDF.
    for d, color, label in (
        (res["n_bash_total"].sort_values().values, RESOLVED_COLOR, "resolved"),
        (unr["n_bash_total"].sort_values().values, UNRESOLVED_COLOR, "unresolved"),
    ):
        if len(d):
            y = np.arange(1, len(d) + 1) / len(d)
            ax_b.plot(d, y, color=color, lw=1.2, label=label)
    ax_b.set_xlabel("# bash calls per trajectory")
    ax_b.set_ylabel("CDF")
    ax_b.set_title("(b) Bash-call budget")
    ax_b.legend(loc="lower right", fontsize=7.0)

    # (c) rc failure rate by outcome violin.
    parts = ax_c.violinplot(
        [res["rc_failure_rate"].values, unr["rc_failure_rate"].values],
        positions=[0, 1], widths=0.7, showmedians=True, showextrema=False,
    )
    for pc, color in zip(parts["bodies"], [RESOLVED_COLOR, UNRESOLVED_COLOR]):
        pc.set_facecolor(color)
        pc.set_alpha(0.55)
        pc.set_edgecolor("none")
    parts["cmedians"].set_color(GREY)
    ax_c.set_xticks([0, 1])
    ax_c.set_xticklabels(["resolved", "unresolved"])
    ax_c.set_ylabel("Bash returncode != 0 rate")
    ax_c.set_title("(c) Per-instance shell error rate")
    ax_c.set_ylim(0, df["rc_failure_rate"].max() * 1.05)

    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig21_conversation_lengths.png")
    plt.close(fig)


def fig_phase_transition_heatmap(csv_dir: Path, fig_dir: Path) -> None:
    """8x8 phase transition probability heatmap, off-diagonal scale.

    The intra-phase 96-97 % self-loop dominates the colour scale, so
    we plot ``log10(prob + 1e-3)`` and mask the diagonal — what is
    interesting is how clean the off-diagonal flow is.
    """
    df = pd.read_csv(csv_dir / "conv_phase_transition.csv")
    df = df[df["split"] == "all"]
    M = df.pivot(index="from_phase", columns="to_phase", values="prob")
    M = M.reindex(index=PHASES_ORDERED, columns=PHASES_ORDERED).fillna(0.0).values
    M_off = M.copy()
    np.fill_diagonal(M_off, np.nan)

    fig, ax = plt.subplots(figsize=(5.4, 4.0))
    cmap = plt.cm.viridis
    cmap.set_bad(color="white")
    im = ax.imshow(M_off, cmap=cmap, vmin=0.0, vmax=0.04, aspect="equal")
    ax.set_xticks(np.arange(len(PHASES_ORDERED)))
    ax.set_yticks(np.arange(len(PHASES_ORDERED)))
    ax.set_xticklabels(PHASES_ORDERED, rotation=45, ha="right", fontsize=6.5)
    ax.set_yticklabels(PHASES_ORDERED, fontsize=6.5)
    for i in range(len(PHASES_ORDERED)):
        for j in range(len(PHASES_ORDERED)):
            v = M[i, j]
            if i == j:
                ax.text(j, i, f"{v:.0%}", ha="center", va="center",
                        color=GREY, fontsize=5.8)
            elif v > 0.001:
                col = "white" if v > 0.018 else "black"
                ax.text(j, i, f"{v:.1%}", ha="center", va="center",
                        color=col, fontsize=5.8)
    cbar = fig.colorbar(im, ax=ax, fraction=0.044, pad=0.04)
    cbar.set_label("Off-diagonal P(phase$_{t+1}$|phase$_t$)", fontsize=7.0)
    ax.set_xlabel("to phase")
    ax.set_ylabel("from phase")
    ax.set_title("Phase transition matrix (assistant turn t → t+1)")
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig22_phase_transitions.png")
    plt.close(fig)


def fig_bash_verbs(csv_dir: Path, fig_dir: Path) -> None:
    """Top-15 bash verbs by frequency, with outcome-conditional bars."""
    df = pd.read_csv(csv_dir / "conv_bash_verbs.csv").head(15)
    df = df.iloc[::-1].reset_index(drop=True)
    n_res = max(df["resolved_calls"].sum(), 1)
    n_unr = max(df["unresolved_calls"].sum(), 1)

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.5))
    ax_a, ax_b = axes

    ys = np.arange(len(df))
    ax_a.barh(ys, df["total"], color=KOZUCHI_COLOR, alpha=0.85, edgecolor="white")
    ax_a.set_yticks(ys)
    ax_a.set_yticklabels(df["verb"], fontsize=7.0)
    ax_a.set_xlabel("# bash calls (across 495 trajectories)")
    ax_a.set_title("(a) Top-15 bash command verbs")
    for y, v, t in zip(ys, df["total"], df["share_of_calls"]):
        ax_a.text(v + max(df["total"]) * 0.005, y, f"{int(v):,} ({t:.1%})",
                  va="center", fontsize=6.3, color=GREY)

    width = 0.4
    ax_b.barh(ys + width / 2, df["resolved_calls"] / n_res, height=width,
              color=RESOLVED_COLOR, label=f"resolved (374, {int(n_res):,} calls)")
    ax_b.barh(ys - width / 2, df["unresolved_calls"] / n_unr, height=width,
              color=UNRESOLVED_COLOR, label=f"unresolved (121, {int(n_unr):,} calls)")
    ax_b.set_yticks(ys)
    ax_b.set_yticklabels(df["verb"], fontsize=7.0)
    ax_b.set_xlabel("Share of all calls (within outcome)")
    ax_b.set_title("(b) Per-outcome verb mix")
    ax_b.legend(loc="lower right", fontsize=6.5)

    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig23_bash_verbs.png")
    plt.close(fig)


def fig_error_indicators(csv_dir: Path, fig_dir: Path) -> None:
    """Per-trajectory mean count of common Python error markers,
    split by outcome.
    """
    df = pd.read_csv(csv_dir / "conv_error_indicators.csv")
    df = df.sort_values("total", ascending=True).reset_index(drop=True)
    # Compute per-instance means for resolved / unresolved from totals.
    n_res = 374
    n_unr = 121
    df["mean_res"] = df["resolved_total"] / n_res
    df["mean_unr"] = df["unresolved_total"] / n_unr

    fig, ax = plt.subplots(figsize=(5.4, 3.6))
    ys = np.arange(len(df))
    width = 0.4
    ax.barh(ys + width / 2, df["mean_res"], height=width, color=RESOLVED_COLOR,
            label="mean / instance (resolved)")
    ax.barh(ys - width / 2, df["mean_unr"], height=width, color=UNRESOLVED_COLOR,
            label="mean / instance (unresolved)")
    ax.set_yticks(ys)
    ax.set_yticklabels(df["marker"], fontsize=7.0)
    ax.set_xlabel("Occurrences per trajectory (mean)")
    ax.set_title("Python error / traceback markers in tool outputs")
    ax.legend(loc="lower right", fontsize=7.0)
    for y, m_r, m_u in zip(ys, df["mean_res"], df["mean_unr"]):
        ax.text(m_r + 0.5, y + width / 2, f"{m_r:.1f}", va="center",
                fontsize=6.0, color=GREY)
        ax.text(m_u + 0.5, y - width / 2, f"{m_u:.1f}", va="center",
                fontsize=6.0, color=GREY)
    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig24_error_indicators.png")
    plt.close(fig)


def fig_thought_action_phase(csv_dir: Path, fig_dir: Path) -> None:
    """Per-phase mean thought / action character counts (resolved only).

    Two panels:
      (a) Side-by-side bars per phase: thought vs action chars per
          assistant message.
      (b) Thought:action ratio per phase, resolved vs unresolved.
    """
    df = pd.read_csv(csv_dir / "conv_thought_action_stats.csv")
    res = df[df["outcome"] == "resolved"].set_index("phase").reindex(PHASES_ORDERED)
    unr = df[df["outcome"] == "unresolved"].set_index("phase").reindex(PHASES_ORDERED)

    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.0))
    ax_a, ax_b = axes
    xs = np.arange(len(PHASES_ORDERED))
    width = 0.4

    ax_a.bar(xs - width / 2, res["mean_thought_chars_per_msg"], width=width,
             color=RESOLVED_COLOR, label="THOUGHT chars / msg",
             alpha=0.85, edgecolor="white")
    ax_a.bar(xs + width / 2, res["mean_action_chars_per_msg"], width=width,
             color=KOZUCHI_COLOR, label="FINAL_ANSWER chars / msg",
             alpha=0.85, edgecolor="white")
    ax_a.set_xticks(xs)
    ax_a.set_xticklabels([p.replace("_", "\n") for p in PHASES_ORDERED],
                         fontsize=6.5)
    ax_a.set_ylabel("Mean characters per assistant message")
    ax_a.set_title("(a) Thought vs. action by phase (resolved)")
    ax_a.legend(loc="upper right", fontsize=6.5)

    ax_b.plot(xs, res["thought_action_ratio"], color=RESOLVED_COLOR, marker="o",
              lw=1.2, label="resolved")
    ax_b.plot(xs, unr["thought_action_ratio"], color=UNRESOLVED_COLOR, marker="s",
              lw=1.2, ls="--", label="unresolved")
    ax_b.set_xticks(xs)
    ax_b.set_xticklabels([p.replace("_", "\n") for p in PHASES_ORDERED],
                         fontsize=6.5)
    ax_b.set_ylabel("THOUGHT : FINAL_ANSWER chars")
    ax_b.set_title("(b) Reasoning–action balance by outcome")
    ax_b.legend(loc="upper left", fontsize=6.5)

    fig.tight_layout(pad=0.4)
    fig.savefig(fig_dir / "fig25_thought_action.png")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv-dir", type=Path, default=CSV_DIR)
    p.add_argument("--fig-dir", type=Path, default=FIG_DIR)
    args = p.parse_args()
    ensure_out_dirs()
    args.fig_dir.mkdir(parents=True, exist_ok=True)
    _style()
    fig_overview(args.csv_dir, args.fig_dir)
    fig_per_repo(args.csv_dir, args.fig_dir)
    fig_per_year(args.csv_dir, args.fig_dir)
    fig_failure_modes(args.csv_dir, args.fig_dir)
    fig_loc_buckets(args.csv_dir, args.fig_dir)
    fig_effort_buckets(args.csv_dir, args.fig_dir)
    fig_phase_dynamics(args.csv_dir, args.fig_dir)
    fig_correlations(args.csv_dir, args.fig_dir)
    fig_leaderboard(args.csv_dir, args.fig_dir)
    fig_peers(args.csv_dir, args.fig_dir)
    fig_per_repo_vs_peers(args.csv_dir, args.fig_dir)
    fig_consensus_vs_rate(args.csv_dir, args.fig_dir)
    fig_consensus_effort(args.csv_dir, args.fig_dir)
    fig_unresolved_strata(args.csv_dir, args.fig_dir)
    fig_effect_sizes(args.csv_dir, args.fig_dir)
    fig_pareto(args.csv_dir, args.fig_dir)
    n_fig = 16
    # New TTS@8 candidate-level figures (see §11 of analysis.md).
    if (args.csv_dir / "tts_per_leg.csv").exists():
        fig_tts_per_leg(args.csv_dir, args.fig_dir)
        fig_tts_pass_at_k(args.csv_dir, args.fig_dir)
        fig_tts_resolve_distribution(args.csv_dir, args.fig_dir)
        fig_tts_leg_jaccard(args.csv_dir, args.fig_dir)
        fig_tts_oracle_vs_selector(args.csv_dir, args.fig_dir)
        n_fig = 21
    # New conversation-level figures (see §12 of analysis.md).
    if (args.csv_dir / "conv_per_instance.csv").exists():
        fig_conv_lengths(args.csv_dir, args.fig_dir)
        fig_phase_transition_heatmap(args.csv_dir, args.fig_dir)
        fig_bash_verbs(args.csv_dir, args.fig_dir)
        fig_error_indicators(args.csv_dir, args.fig_dir)
        fig_thought_action_phase(args.csv_dir, args.fig_dir)
        n_fig = max(n_fig, 26)
    print(f"[make_figures] wrote {n_fig} figures to {args.fig_dir}")


if __name__ == "__main__":
    main()
