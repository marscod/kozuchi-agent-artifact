# /// script
# dependencies = [
#   "matplotlib",
#   "numpy",
#   "openpyxl",
#   "pandas",
#   "seaborn",
# ]
# ///
"""Companion to ``analyze_comparison.py``: regenerate the
``broad_success_vs_params`` figure with a *second* axis showing **real**
Multi-SWE-Bench Java open/local peers and their own Pareto frontier.

Why a separate script?  The shared workbook
(``paper/comparison/SWE-bench comparison.xlsx``) keeps the same row
template across Python and Java sheets but only some of the Java rows
have been filled in with Multi-SWE-Bench Java success rates.  The rest
still hold the *Python* SWE-Bench Verified scores from the broad sheet
(verified empirically: 12 of the 13 open/local rows that appear on both
sheets share identical ``success_rate`` and ``params_total`` columns).
Using those rows for the Java Pareto frontier would put the Java front
above the Python front, which is incorrect.

This script therefore reads:

* Python (broad) success rates from the workbook.
* Java success rates from
  ``paper/java_src/csv/leaderboard.csv``, which is generated from the
  upstream Multi-SWE-Bench Java Verified ``results.json`` artefacts and
  is the same data the Java analysis (``analysis.java.md``) is built
  on.

Parameter counts for Java rows are pulled from the workbook where
available and otherwise from a small curated lookup of well-known
open-weight LLM sizes (DeepSeek-V3 / R1, Llama-4 Maverick, Qwen2.5-72B,
Qwen3.5-27B).

Run from the repository root with::

    uv run paper/comparison/src/plot_broad_with_java.py

Outputs::

    paper/comparison/plots/broad_success_vs_params_with_java.png
    paper/final/figures/broad_success_vs_params_with_java.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

import os

ARTIFACT_ROOT = Path(
    os.environ.get(
        "KOZUCHI_ARTIFACT_ROOT",
        Path(__file__).resolve().parents[2],
    )
).resolve()
ROOT = ARTIFACT_ROOT / "data" / "paper_comparison"
WORKBOOK = ROOT / "SWE-bench comparison.xlsx"
PLOTS_DIR = ARTIFACT_ROOT / "plots"
FINAL_FIG_DIR = ARTIFACT_ROOT / "figures"
JAVA_LEADERBOARD = ARTIFACT_ROOT / "data" / "paper_java_src" / "csv" / "leaderboard.csv"

PYTHON_SHEET = "20260325_Map"
JAVA_SHEET = "20260407_java_Map"

KOZUCHI_PY = "Kozuchi mini-swe-agent + Qwen3.5-27B"
KOZUCHI_JA = "kozuchi-mini-swe-agent + qwen3.5-27b xcheck@8"

PY_COLOR = "#1f77b4"
JA_COLOR = "#d62728"
KOZUCHI_COLOR = "#d95f02"


# ---------------------------------------------------------------------------
# Open-weight LLM size lookup (total parameters in B). Only models that
# appear in the Multi-SWE-Bench Java Verified leaderboard with publicly
# released weights are listed here. Closed-weight rows (Claude, GPT-4o,
# OpenAI o*, Gemini, Doubao, MiniMax, Kimi family without weights, ...)
# are intentionally excluded so the Java open-weight Pareto front
# reflects only models a reproducer can actually self-host.
# ---------------------------------------------------------------------------
OPEN_WEIGHT_PARAMS_B: dict[str, float] = {
    # Multi-SWE-Bench Java leaderboard names -> total parameters (B)
    "kozuchi-mini-swe-agent + qwen3.5-27b xcheck@8": 27.0,
    "iSWE-OpenModels": 120.0,                              # workbook row
    "MagentLess + DeepSeek-R1": 671.0,
    "MagentLess + DeepSeek-V3": 671.0,
    "MSWE-agent + DeepSeek-R1": 671.0,
    "MSWE-agent + DeepSeek-V3": 671.0,
    "MopenHands + DeepSeek-R1": 671.0,
    "MopenHands + DeepSeek-V3": 671.0,
    "MagentLess + Llama-4-Maverick": 402.0,
    "MSWE-agent + Llama-4-Maverick": 402.0,
    "MopenHands + Llama-4-Maverick": 402.0,
    "MagentLess + Qwen2.5-72B-Instruct": 72.0,
    "MSWE-agent + Qwen2.5-72B-Instruct": 72.0,
    "MopenHands + Qwen2.5-72B-Instruct": 72.0,
}


# ---------------------------------------------------------------------------
# Workbook loader (reused for the Python panel)
# ---------------------------------------------------------------------------
def load_workbook_map(sheet_name: str) -> pd.DataFrame:
    raw = pd.read_excel(WORKBOOK, sheet_name=sheet_name, header=None)
    df = raw.iloc[3:].copy()
    df.columns = raw.iloc[2]
    df = df.loc[:, [pd.notna(col) for col in df.columns]]
    df = df.loc[:, ~pd.Index(df.columns).duplicated()]
    df = df.rename(
        columns={
            "Model (Coding Agent+LLM)": "model",
            "Success Rate\n (%Resolved)": "success_rate",
            "Local LLM": "local_llm",
            "Leaderboard": "leaderboard",
            "Parameter(Total)": "params_total",
            "Parameter(Activated)": "params_active",
        }
    )
    df = df[df["model"].notna()].copy()
    df["model"] = df["model"].astype(str).str.strip()
    for col in ["success_rate", "leaderboard", "params_total", "params_active"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["local_llm"] = df["local_llm"].astype(str).where(df["local_llm"].notna(), "")
    df["is_kozuchi"] = df["model"].str.contains("Kozuchi", case=False, na=False)
    df["is_open_or_local"] = df["local_llm"].eq("O")
    return df.reset_index(drop=True)


def python_open_local(broad: pd.DataFrame) -> pd.DataFrame:
    sub = broad[
        broad["is_open_or_local"]
        & broad["success_rate"].notna()
        & broad["params_total"].notna()
        & (broad["params_total"] > 0)
    ].copy()
    sub = sub[~sub["model"].apply(_is_placeholder_name)]
    return sub.sort_values("params_total").reset_index(drop=True)


def _is_placeholder_name(name: str) -> bool:
    if name.startswith("#"):
        return True
    return any(tag in name for tag in ("OpenAIの情報", "TODO", "TBD"))


# ---------------------------------------------------------------------------
# Java open-weight loader (uses the *real* Java leaderboard CSV)
# ---------------------------------------------------------------------------
def java_open_weight() -> pd.DataFrame:
    lb = pd.read_csv(JAVA_LEADERBOARD)
    lb["success_rate"] = lb["rate"].astype(float) * 100.0

    rows: list[dict] = []
    for _, row in lb.iterrows():
        name = str(row["name"]).strip()
        if name not in OPEN_WEIGHT_PARAMS_B:
            continue
        rows.append(
            {
                "model": name,
                "display_model": _short_name(name),
                "success_rate": float(row["success_rate"]),
                "ci_lo": float(row["ci_lo"]) * 100.0,
                "ci_hi": float(row["ci_hi"]) * 100.0,
                "params_total": OPEN_WEIGHT_PARAMS_B[name],
                "rank": int(row["rank"]) if pd.notna(row.get("rank")) else None,
                "is_target": bool(row.get("is_target", False)),
            }
        )
    out = pd.DataFrame(rows).sort_values("params_total").reset_index(drop=True)
    out["is_kozuchi"] = out["model"].eq(KOZUCHI_JA)
    return out


def _short_name(name: str) -> str:
    if name == KOZUCHI_JA:
        return "Kozuchi Agent + Qwen3.5-27B"
    return name


# ---------------------------------------------------------------------------
# Pareto frontier / upper envelope
# ---------------------------------------------------------------------------
def pareto_front(data: pd.DataFrame) -> pd.DataFrame:
    """Strict Pareto frontier: sort by params, keep rows where the
    success_rate equals the running max.  Yields a rising line."""
    sub = (
        data.groupby("params_total", as_index=False)["success_rate"].max()
        .sort_values("params_total")
        .reset_index(drop=True)
    )
    keep = sub["success_rate"].cummax().eq(sub["success_rate"])
    return sub[keep].reset_index(drop=True)


def size_class_envelope(data: pd.DataFrame) -> pd.DataFrame:
    """Upper envelope: for each unique total-parameter size, take the
    best (max) success_rate among rows in that size class.  Unlike the
    strict Pareto frontier, this curve can go up and down -- it traces
    the *achievable peak* at each size class and therefore always
    passes through real data points.  Used for the Java track because
    the strict Java Pareto front collapses to a single point (Kozuchi
    27 B / 32.03 %)."""
    return (
        data.groupby("params_total", as_index=False)["success_rate"].max()
        .sort_values("params_total")
        .reset_index(drop=True)
    )


def filter_below_frontier(
    open_df: pd.DataFrame,
    frontier_df: pd.DataFrame,
    min_rate: float,
) -> pd.DataFrame:
    """Drop rows whose success_rate is below ``min_rate`` *unless*
    they are points on the frontier.  Frontier membership is decided
    by exact (params_total, success_rate) match against the rows of
    ``frontier_df``."""
    frontier_pairs = set(
        zip(frontier_df["params_total"].astype(float),
            frontier_df["success_rate"].astype(float))
    )
    is_frontier = [
        (float(p), float(s)) in frontier_pairs
        for p, s in zip(open_df["params_total"], open_df["success_rate"])
    ]
    keep = (open_df["success_rate"] >= min_rate) | pd.Series(is_frontier,
                                                              index=open_df.index)
    return open_df[keep].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Annotation placements (data coordinates of the *target axis*)
# ---------------------------------------------------------------------------
PY_ANNOTATIONS = {
    KOZUCHI_PY: dict(
        label="Kozuchi Agent + Qwen3.5-27B (Python)",
        # Sits below the Kozuchi star in the open mid-left band; the
        # iSWE-OpenModels box was moved out of this area to make room.
        xy=(50, 70.5),
        ha="left", va="top", weight="bold",
        connectionstyle="arc3,rad=0.10",
        bbox_color=PY_COLOR,
    ),
    "Qwen3.5-397B": dict(
        label="Qwen3.5-397B",
        # Push up into the middle-top white band so the box no longer
        # collides with the iSWE-OpenModels box at the same x-screen
        # range below.
        xy=(330, 88.5),
        ha="center", va="bottom",
        connectionstyle="arc3,rad=-0.10",
    ),
    "Kimi-K2.5-1T": dict(
        label="Kimi K2.5",
        # Centred above the marker rather than tucked in the corner.
        xy=(1100, 89.0),
        ha="center", va="bottom",
        connectionstyle="arc3,rad=0.05",
    ),
    "Code World Model": dict(
        label="Code World Model",
        xy=(55, 60.5),
        ha="left", va="top",
        connectionstyle="arc3,rad=0.10",
    ),
}

JA_ANNOTATIONS = {
    KOZUCHI_JA: dict(
        label="Kozuchi Agent + Qwen3.5-27B (Java)",
        # Move slightly right/down so it doesn't crowd the top-left of
        # the plot and leaves room for the new Kozuchi (Python) box.
        xy=(70, 36.0),
        ha="left", va="bottom", weight="bold",
        connectionstyle="arc3,rad=-0.05",
        bbox_color=KOZUCHI_COLOR,
    ),
    "iSWE-OpenModels": dict(
        label="iSWE-OpenModels",
        # Move to the right of its marker into the empty mid-band; this
        # frees the area below the Kozuchi (Python) box.
        xy=(260, 32.0),
        ha="left", va="bottom",
        connectionstyle="arc3,rad=-0.10",
    ),
    "MagentLess + DeepSeek-R1": dict(
        label="MagentLess + DeepSeek-R1",
        xy=(1500, 26.5),
        ha="right", va="bottom",
        connectionstyle="arc3,rad=-0.05",
    ),
    "MagentLess + Llama-4-Maverick": dict(
        label="MagentLess + Llama-4-Maverick",
        # Pull the box right of the marker into the open right-mid band
        # rather than overlapping the iSWE arrow path.
        xy=(900, 19.0),
        ha="right", va="top",
        connectionstyle="arc3,rad=-0.05",
    ),
    "MagentLess + Qwen2.5-72B-Instruct": dict(
        label="MagentLess + Qwen2.5-72B",
        xy=(150, 13.5),
        ha="left", va="top",
        connectionstyle="arc3,rad=-0.05",
    ),
}


# ---------------------------------------------------------------------------
# Minor (unboxed) labels for dots that don't have a full annotation.
# Each entry: model_name -> (compact_label, x_text, y_text, ha, va).
# Positions are in *target-axis data coordinates*.  Tuned to avoid
# overlapping the boxed annotations above and the markers themselves.
# ---------------------------------------------------------------------------
MINOR_PY_LABELS: dict[str, tuple[str, float, float, str, str]] = {
    # 23.6 B cluster (DevStral): stagger above / below markers
    "OpenHands + DevStral Small 2507":
        ("OH + DevStral-2507",   25.0, 55.4, "left", "bottom"),
    "OpenHands + DevStral Small 2505":
        ("OH + DevStral-2505",   25.0, 45.4, "left", "top"),
    # 27 B (Qwen3.5-27B base, sits just below the Kozuchi star)
    "Qwen3.5-27B":
        ("Qwen3.5-27B (base)",   33.0, 72.4, "left", "center"),
    # 30.5 / 32.8 B cluster
    "OpenHands + Qwen3-Coder-30B-A3B-Instruct":
        ("OH + Qwen3-Coder-30B", 36.0, 51.6, "left", "center"),
    "SWE-agent + SWE-agent-LM-32B":
        ("SWE-agent-LM-32B",     38.0, 41.2, "left", "bottom"),
    # 70.6 B
    "SWE-RL (Llama3-SWE-RL-70B + Agentless Mini) (20250226)":
        ("SWE-RL Llama3-70B",    78.0, 41.4, "left", "center"),
    # 480 B (two rows): right of the markers so the white space to the
    # left can host the iSWE-OpenModels box and other annotations.
    "OpenHands + Qwen3-Coder-480B":
        ("OH + Qwen3-Coder-480B",   525.0, 69.6, "left", "center"),
    "mini-SWE-agent + Qwen3-Coder 480B/A35B Instruct":
        ("mSWE + Qwen3-Coder-480B", 525.0, 55.4, "left", "center"),
    # 1024 B cluster (right of markers, in the open band 1080-1500)
    "Lingxi v1.5 x Kimi K2":
        ("Lingxi v1.5 x K2",     1080.0, 71.2, "left", "center"),
    "OpenHands + Kimi K2":
        ("OH + Kimi K2",         1080.0, 65.4, "left", "center"),
    "mini-SWE-agent + Kimi K2 Instruct":
        ("mSWE + Kimi K2",       1080.0, 43.8, "left", "center"),
}

MINOR_JA_LABELS: dict[str, tuple[str, float, float, str, str]] = {
    # 72 B cluster (right of MagentLess+Qwen2.5-72B annotation arrow)
    "MopenHands + Qwen2.5-72B-Instruct":
        ("MopenHands + Q2.5-72B",  78.0, 3.4, "left", "center"),
    "MSWE-agent + Qwen2.5-72B-Instruct":
        ("MSWE + Q2.5-72B",        78.0, 1.9, "left", "center"),
    # 402 B cluster (two rows tied at 6.25 %; stagger above and below)
    "MopenHands + Llama-4-Maverick":
        ("MopenHands + Llama-4M",  440.0, 7.1, "left", "center"),
    "MSWE-agent + Llama-4-Maverick":
        ("MSWE + Llama-4M",        440.0, 5.4, "left", "center"),
    # 671 B cluster (5 unlabelled rows; stagger vertically to right)
    "MSWE-agent + DeepSeek-V3":
        ("MSWE + DS-V3",       730.0, 11.9, "left", "center"),
    "MSWE-agent + DeepSeek-R1":
        ("MSWE + DS-R1",       730.0,  9.9, "left", "center"),
    "MopenHands + DeepSeek-V3":
        ("MopenHands + DS-V3", 730.0,  8.6, "left", "center"),
    "MopenHands + DeepSeek-R1":
        ("MopenHands + DS-R1", 730.0,  7.4, "left", "center"),
    "MagentLess + DeepSeek-V3":
        ("MagentLess + DS-V3", 730.0,  6.1, "left", "center"),
}


def _annotate(ax, *, x, y, xytext, label, ha, va, connectionstyle,
              weight="normal", bbox_ec="0.65", arrow_color="0.4",
              fontsize=12.5):
    ax.annotate(
        label,
        xy=(x, y),
        xytext=xytext,
        textcoords="data",
        fontsize=fontsize,
        fontweight=weight,
        color="0.15",
        ha=ha, va=va,
        annotation_clip=False,
        bbox={
            "boxstyle": "round,pad=0.26",
            "fc": "white",
            "ec": bbox_ec,
            "lw": 0.9,
            "alpha": 0.95,
        },
        arrowprops={
            "arrowstyle": "->",
            "color": arrow_color,
            "lw": 1.0,
            "alpha": 0.7,
            "shrinkA": 6,
            "shrinkB": 4,
            "mutation_scale": 11,
            "connectionstyle": connectionstyle,
        },
    )


def _minor_label(ax, *, x_text, y_text, label, ha, va, color,
                  fontsize=8.5):
    """Draw a small inline caption next to a marker (no box, no
    arrow).  Used for the unlabelled dots."""
    ax.text(
        x_text, y_text, label,
        fontsize=fontsize, color=color,
        ha=ha, va=va,
        zorder=4,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    sns.set_theme(style="whitegrid", context="paper")
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    broad = load_workbook_map(PYTHON_SHEET)
    py_open_full = python_open_local(broad)
    ja_open_full = java_open_weight()
    py_pareto = pareto_front(py_open_full)             # strict Pareto (Python)
    ja_pareto = pareto_front(ja_open_full)             # strict Pareto (Java) -- 1 pt
    ja_envelope = size_class_envelope(ja_open_full)    # peak per size class (Java)
    # Drop low-performance clutter that is *not* on the frontier:
    #   Python: drop rows below 50 % unless on the strict Pareto front.
    #   Java:   drop rows below 11 % unless on the size-class envelope.
    # The kept rows still include every Pareto / envelope point, so the
    # visualised frontiers are unchanged.
    py_open = filter_below_frontier(py_open_full, py_pareto, min_rate=50.0)
    ja_open = filter_below_frontier(ja_open_full, ja_envelope, min_rate=11.0)

    fig, ax_py = plt.subplots(figsize=(15.5, 8.8))
    ax_ja = ax_py.twinx()

    # ---------------- Python scatter & pareto ----------------
    py_other = py_open[~py_open["is_kozuchi"]]
    py_koz = py_open[py_open["is_kozuchi"]]
    ax_py.scatter(
        py_other["params_total"], py_other["success_rate"],
        s=70, c=PY_COLOR, alpha=0.85, edgecolors="black",
        linewidths=0.5, marker="o", zorder=3,
        label="Python: SWE-Bench Verified (open/local peers)",
    )
    if not py_koz.empty:
        ax_py.scatter(
            py_koz["params_total"], py_koz["success_rate"],
            s=380, c=PY_COLOR, alpha=0.95,
            edgecolors="black", linewidths=0.8, marker="*",
            zorder=6, label="Kozuchi Agent (Python)",
        )
    ax_py.plot(
        py_pareto["params_total"], py_pareto["success_rate"],
        color=PY_COLOR, linestyle="--", linewidth=2.0, alpha=0.85,
        marker="o", markersize=4, zorder=2,
    )

    # ---------------- Java scatter & pareto ----------------
    ja_other = ja_open[~ja_open["is_kozuchi"]]
    ja_koz = ja_open[ja_open["is_kozuchi"]]
    ax_ja.scatter(
        ja_other["params_total"], ja_other["success_rate"],
        s=70, c=JA_COLOR, alpha=0.85, edgecolors="black",
        linewidths=0.5, marker="s", zorder=3,
        label="Java: Multi-SWE-Bench Verified (open-weight peers)",
    )
    if not ja_koz.empty:
        ax_ja.scatter(
            ja_koz["params_total"], ja_koz["success_rate"],
            s=380, c=KOZUCHI_COLOR, alpha=0.95,
            edgecolors="black", linewidths=0.8, marker="*",
            zorder=6, label="Kozuchi Agent (Java)",
        )
    # The strict Java Pareto front is a single point (Kozuchi 27 B /
    # 32.03 %), so a "Pareto line" would float disconnected from every
    # other red square.  Instead we draw the *upper envelope* that
    # connects the peak success rate at each size class -- it visits
    # five real data points (27 / 72 / 120 / 402 / 671 B) and traces
    # the achievable open-weight Java landscape.  The strict
    # Pareto-optimum point is highlighted by the orange Kozuchi-Java
    # star and called out in the legend below.
    ax_ja.plot(
        ja_envelope["params_total"], ja_envelope["success_rate"],
        color=JA_COLOR, linestyle="--", linewidth=1.8, alpha=0.85,
        marker="s", markersize=5, markerfacecolor=JA_COLOR,
        markeredgecolor="black", markeredgewidth=0.5,
        zorder=2,
    )

    # ---------------- Axes / styling ----------------
    ax_py.set_xscale("log")
    ax_py.set_xlim(20, 1600)
    # After dropping non-frontier rows below 50 % (Python) / 11 % (Java)
    # the lowest kept points sit at 51.6 % and 10.94 % respectively, so
    # we tighten the axes to remove dead space at the bottom.  The Java
    # range is also chosen so the Kozuchi-Java star sits clearly above
    # the Kozuchi-Python star (rather than on top of it).
    ax_py.set_ylim(48, 92)
    ax_ja.set_ylim(8, 40)

    ax_py.set_xlabel("Total parameters (B, log scale)", fontsize=18)
    ax_py.set_ylabel(
        "SWE-Bench Verified (Python) — % resolved",
        fontsize=17, color=PY_COLOR,
    )
    ax_ja.set_ylabel(
        "Multi-SWE-Bench Verified (Java) — % resolved",
        fontsize=17, color=JA_COLOR,
    )
    ax_py.tick_params(axis="y", labelcolor=PY_COLOR, labelsize=17)
    ax_ja.tick_params(axis="y", labelcolor=JA_COLOR, labelsize=17)
    ax_py.tick_params(axis="x", labelsize=17)

    ax_py.set_title(
        "Parameter Efficiency of Kozuchi Agent vs. Open-Weight Peers — "
        "Python Pareto front and Java size-class envelope",
        fontsize=16, pad=14,
    )
    # Major gridlines (at the decade ticks 10^2, 10^3) and a denser
    # set of x-axis reference lines at frequently cited parameter
    # sizes -- helps the reader read off the nearest "round" model
    # size for any data point.
    ax_py.grid(True, which="major", linestyle="-", linewidth=0.5, alpha=0.30)
    ax_py.grid(True, which="minor", axis="y", linestyle=":",
               linewidth=0.4, alpha=0.18)
    # Bold dashed reference lines at the data-point clusters used in
    # the paper (Kozuchi size, common open-weight sizes).
    bold_xs = [27, 100, 300, 1000]
    for x_value in bold_xs:
        ax_py.axvline(x_value, color="0.55", linestyle="--",
                      linewidth=0.9, alpha=0.55, zorder=0)
    # Light dotted reference lines at the in-between sizes.
    for x_value in [30, 50, 70, 120, 150, 200, 400, 500, 700, 1500]:
        ax_py.axvline(x_value, color="0.70", linestyle=":",
                      linewidth=0.7, alpha=0.45, zorder=0)
    ax_py.spines[["top"]].set_visible(False)

    # ---------------- Annotations ----------------
    py_lookup = py_open.set_index("model")
    for model, ann in PY_ANNOTATIONS.items():
        if model not in py_lookup.index:
            continue
        row = py_lookup.loc[model]
        x0 = float(row["params_total"])
        y0 = float(row["success_rate"])
        _annotate(
            ax_py, x=x0, y=y0,
            xytext=ann["xy"],
            label=f"{ann['label']}\n{y0:.1f}% / {x0:.0f}B",
            ha=ann["ha"], va=ann["va"],
            connectionstyle=ann["connectionstyle"],
            weight=ann.get("weight", "normal"),
            bbox_ec=ann.get("bbox_color", PY_COLOR),
            arrow_color=PY_COLOR,
        )

    ja_lookup = ja_open.set_index("model")
    for model, ann in JA_ANNOTATIONS.items():
        if model not in ja_lookup.index:
            continue
        row = ja_lookup.loc[model]
        x0 = float(row["params_total"])
        y0 = float(row["success_rate"])
        _annotate(
            ax_ja, x=x0, y=y0,
            xytext=ann["xy"],
            label=f"{ann['label']}\n{y0:.2f}% / {x0:.0f}B",
            ha=ann["ha"], va=ann["va"],
            connectionstyle=ann["connectionstyle"],
            weight=ann.get("weight", "normal"),
            bbox_ec=ann.get("bbox_color", JA_COLOR),
            arrow_color=JA_COLOR,
        )

    # ---------------- Minor (unboxed) inline captions ----------------
    for model, (label, x_text, y_text, ha, va) in MINOR_PY_LABELS.items():
        if model not in py_lookup.index:
            continue
        _minor_label(
            ax_py, x_text=x_text, y_text=y_text,
            label=label, ha=ha, va=va,
            color=PY_COLOR,
        )
    for model, (label, x_text, y_text, ha, va) in MINOR_JA_LABELS.items():
        if model not in ja_lookup.index:
            continue
        _minor_label(
            ax_ja, x_text=x_text, y_text=y_text,
            label=label, ha=ha, va=va,
            color=JA_COLOR,
        )

    # ---------------- Legend (combined) ----------------
    handles_py, labels_py = ax_py.get_legend_handles_labels()
    handles_ja, labels_ja = ax_ja.get_legend_handles_labels()
    pareto_py_handle = plt.Line2D([], [], color=PY_COLOR, linestyle="--",
                                   marker="o", markersize=5, lw=2,
                                   label="Pareto front (Python)")
    envelope_ja_handle = plt.Line2D([], [], color=JA_COLOR, linestyle="--",
                                     marker="s", markersize=5, lw=1.8,
                                     label="Java best per size class")
    ax_py.legend(
        handles=handles_py + handles_ja + [pareto_py_handle, envelope_ja_handle],
        labels=labels_py + labels_ja + ["Pareto front (Python)",
                                          "Java best per size class"],
        loc="upper center", bbox_to_anchor=(0.5, -0.10),
        ncol=3, fontsize=10.5, framealpha=0.95,
    ).set_zorder(20)

    ax_py.text(
        0.5, -0.235,
        "Python: SWE-Bench Verified, n=500.    "
        "Java: Multi-SWE-Bench Verified, n=128 (open-weight rows only).\n"
        "Blue dashed = strict Pareto front (Python).    "
        "Red dashed = max % per Java size class "
        "(strict Java Pareto front = Kozuchi Agent alone).",
        transform=ax_py.transAxes, fontsize=9.5, color="0.35",
        ha="center", va="top",
    )

    fig.subplots_adjust(left=0.07, right=0.93, bottom=0.22, top=0.92)

    out1 = PLOTS_DIR / "broad_success_vs_params_with_java.png"
    fig.savefig(out1, dpi=240)
    out2 = FINAL_FIG_DIR / "broad_success_vs_params_with_java.png"
    out2.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out2, dpi=240)
    plt.close(fig)

    # ---------------- Console summary ----------------
    print(f"wrote {out1}")
    print(f"wrote {out2}")
    print()
    print("Python open-local rows (n =", len(py_open), "):")
    for _, r in py_open.sort_values("success_rate", ascending=False).head(8).iterrows():
        print(f"  {r['params_total']:>7.1f} B   {r['success_rate']:>5.1f} %   {r['model']}")
    print()
    print("Python Pareto frontier:")
    for _, r in py_pareto.iterrows():
        match = py_open[py_open["params_total"].eq(r["params_total"])
                        & py_open["success_rate"].eq(r["success_rate"])]
        model = match.iloc[0]["model"] if not match.empty else "?"
        print(f"  {r['params_total']:>7.1f} B   {r['success_rate']:>5.1f} %   {model}")
    print()
    print("Java open-weight rows (n =", len(ja_open), "):")
    for _, r in ja_open.sort_values("success_rate", ascending=False).iterrows():
        print(f"  {r['params_total']:>7.1f} B   {r['success_rate']:>5.2f} %   {r['model']}")
    print()
    print("Java Pareto frontier:")
    for _, r in ja_pareto.iterrows():
        match = ja_open[ja_open["params_total"].eq(r["params_total"])
                        & ja_open["success_rate"].eq(r["success_rate"])]
        model = match.iloc[0]["model"] if not match.empty else "?"
        print(f"  {r['params_total']:>7.1f} B   {r['success_rate']:>5.2f} %   {model}")


if __name__ == "__main__":
    main()
