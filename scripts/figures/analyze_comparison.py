# /// script
# dependencies = [
#   "matplotlib",
#   "openpyxl",
#   "pandas",
#   "seaborn",
# ]
# ///
"""Analyze the SWE-bench comparison workbook with a Kozuchi focus.

Run from the repository root with:
    uv run paper/comparison/src/analyze_comparison.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

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
REPORT = PLOTS_DIR / "analysis.md"

SHEETS = {
    "broad": "20260325_Map",
    "java": "20260407_java_Map",
    "baseline": "20250924_Map",
}

KOZUCHI = "Kozuchi mini-swe-agent + Qwen3.5-27B"


@dataclass(frozen=True)
class Comparison:
    name: str
    model: str
    success_rate: float
    params_total: float | None
    delta_pp: float
    size_ratio: float | None
    note: str


def load_map(sheet_name: str) -> pd.DataFrame:
    """Load a manually mapped workbook sheet whose real header is row 3."""
    raw = pd.read_excel(WORKBOOK, sheet_name=sheet_name, header=None)
    df = raw.iloc[3:].copy()
    df.columns = raw.iloc[2]
    df = df.loc[:, [pd.notna(col) for col in df.columns]]
    df = df.loc[:, ~pd.Index(df.columns).duplicated()]
    df = df.rename(
        columns={
            "Model (Coding Agent+LLM)": "model",
            "Success Rate\n (%Resolved)": "success_rate",
            "Date": "date",
            "Local LLM": "local_llm",
            "Leaderboard": "leaderboard",
            "Parameter(Total)": "params_total",
            "Parameter(Activated)": "params_active",
            "total_size(GB)": "total_size_gb",
            "(Info)": "info",
            "Link (Model info)": "link",
        }
    )
    df = df[df["model"].notna()].copy()
    df["model"] = df["model"].astype(str).str.strip()
    df["llm"] = df["LLM"].astype(str).where(df["LLM"].notna(), "")
    for col in ["success_rate", "leaderboard", "params_total", "params_active", "total_size_gb"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["local_llm"] = df["local_llm"].astype(str).where(df["local_llm"].notna(), "")
    df["sheet"] = sheet_name
    df["is_kozuchi"] = df["model"].str.contains("Kozuchi", case=False, na=False)
    df["is_official_leaderboard"] = df["leaderboard"].eq(1)
    df["is_open_or_local"] = df["local_llm"].eq("O")
    df["efficiency_pp_per_b"] = df["success_rate"] / df["params_total"]
    return df.reset_index(drop=True)


def one_row(df: pd.DataFrame, pattern: str) -> pd.Series:
    rows = df[df["model"].str.contains(pattern, case=False, regex=False, na=False)]
    if rows.empty:
        raise ValueError(f"Could not find row matching {pattern!r}")
    return rows.iloc[0]


def fmt_pct(value: float | int | None, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}%"


def fmt_num(value: float | int | None, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}"


def fmt_delta(value: float | int | None, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    sign = "+" if float(value) >= 0 else ""
    return f"{sign}{float(value):.{digits}f} pp"


def markdown_table(rows: list[dict[str, object]], columns: list[str]) -> str:
    if not rows:
        return ""
    out = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join(out)


def rank_position(series: pd.Series, value: float) -> int:
    return int((series.dropna() > value).sum() + 1)


def comparison_rows(broad: pd.DataFrame, java: pd.DataFrame) -> tuple[list[Comparison], list[Comparison]]:
    koz_broad = one_row(broad, KOZUCHI)
    koz_java = one_row(java, KOZUCHI)

    broad_targets = [
        ("Base Qwen3.5-27B", "Qwen3.5-27B", "Same 27B model family without the Kozuchi mini-SWE-agent wrapper."),
        ("Qwen3.5-397B", "Qwen3.5-397B", "Much larger open/local model family."),
        ("Kimi-K2.5-1T", "Kimi-K2.5-1T", "Trillion-parameter frontier open/local peer."),
        ("MiniMax M2.5", "mini-SWE-agent + MiniMax M2.5", "Strong mini-SWE-agent peer using a larger model."),
        ("Lingxi v1.5 x Kimi K2", "Lingxi v1.5 x Kimi K2", "Large Kimi-based agent snapshot."),
        ("OpenHands + Qwen3-Coder-480B", "OpenHands + Qwen3-Coder-480B", "Official leaderboard-scale open/local agent."),
        ("Code World Model", "Code World Model", "Research open-weight coding model baseline."),
    ]
    java_targets = [
        ("CodeArts MiniMax M2.5", "CodeArts Agent + CodeArts-MiniMax-M2.5", "Best custom Java-row result in this sheet."),
        ("MSWE CodeArts MiniMax M2.5", "MSWE-agent + CodeArts-MiniMax-M2.5", "Closest Java-row peer below Kozuchi."),
        ("MagentLess Llama-4-Maverick", "MagentLess + Llama-4-Maverick", "Large-model Java-row baseline."),
        ("MagentLess Qwen2.5-72B", "MagentLess + Qwen2.5-72B-Instruct", "Medium-large Java-row baseline."),
        ("MSWE Llama-4-Maverick", "MSWE-agent + Llama-4-Maverick", "Lowest custom Java-row baseline."),
        ("MopenHands Llama-4-Maverick", "MopenHands + Llama-4-Maverick", "CWM-labeled Java-row baseline."),
    ]

    def build(targets: Iterable[tuple[str, str, str]], koz: pd.Series, frame: pd.DataFrame) -> list[Comparison]:
        rows: list[Comparison] = []
        for name, pattern, note in targets:
            row = one_row(frame, pattern)
            params = None if pd.isna(row["params_total"]) else float(row["params_total"])
            koz_params = None if pd.isna(koz["params_total"]) else float(koz["params_total"])
            ratio = None
            if params and koz_params:
                ratio = params / koz_params
            rows.append(
                Comparison(
                    name=name,
                    model=row["model"],
                    success_rate=float(row["success_rate"]),
                    params_total=params,
                    delta_pp=float(koz["success_rate"] - row["success_rate"]),
                    size_ratio=ratio,
                    note=note,
                )
            )
        return rows

    return build(broad_targets, koz_broad, broad), build(java_targets, koz_java, java)


def selected_open_rows(broad: pd.DataFrame) -> pd.DataFrame:
    labels = [
        "Kimi-K2.5-1T",
        "Qwen3.5-397B",
        "mini-SWE-agent + MiniMax M2.5",
        KOZUCHI,
        "Qwen3.5-27B",
        "Lingxi v1.5 x Kimi K2",
        "OpenHands + Qwen3-Coder-480B",
        "mini-SWE-agent + Qwen3-Coder 480B/A35B Instruct",
        "OpenHands + Qwen3-Coder-30B-A3B-Instruct",
        "Code World Model",
    ]
    parts = []
    for label in labels:
        try:
            parts.append(one_row(broad, label))
        except ValueError:
            continue
    return pd.DataFrame(parts).drop_duplicates(subset=["model"]).sort_values("success_rate", ascending=False)


def custom_java_rows(java: pd.DataFrame) -> pd.DataFrame:
    patterns = [
        "CodeArts Agent + CodeArts-MiniMax-M2.5",
        KOZUCHI,
        "MSWE-agent + CodeArts-MiniMax-M2.5",
        "MagentLess + Llama-4-Maverick",
        "MagentLess + Qwen2.5-72B-Instruct",
        "MSWE-agent + Llama-4-Maverick",
        "MopenHands + Llama-4-Maverick",
    ]
    rows = [one_row(java, pattern) for pattern in patterns]
    return pd.DataFrame(rows).drop_duplicates(subset=["model"]).sort_values("success_rate", ascending=True)


def plot_broad_scatter(broad: pd.DataFrame) -> Path:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    data = broad[broad["success_rate"].notna() & broad["params_total"].notna() & (broad["params_total"] > 0)].copy()
    selected = [
        ("Kozuchi Agent\n+ Qwen3.5-27B", KOZUCHI, "#d95f02", "bold"),
        ("Qwen3.5-27B", "Qwen3.5-27B", "#4c78a8", "normal"),
        ("Qwen3.5-397B", "Qwen3.5-397B", "#4c78a8", "normal"),
        ("Kimi K2.5", "Kimi-K2.5-1T", "#4c78a8", "normal"),
        ("MiniMax M2.5", "mini-SWE-agent + MiniMax M2.5", "#4c78a8", "normal"),
        ("Lingxi Kimi K2", "Lingxi v1.5 x Kimi K2", "#4c78a8", "normal"),
        ("OpenHands\n+ Qwen3-Coder", "OpenHands + Qwen3-Coder-480B", "#4c78a8", "normal"),
        ("Code World Model", "Code World Model", "#4c78a8", "normal"),
    ]
    selected_rows = []
    for label, pattern, color, weight in selected:
        row = one_row(data, pattern).copy()
        row["label"] = label
        row["label_color"] = color
        row["label_weight"] = weight
        selected_rows.append(row)
    selected_df = pd.DataFrame(selected_rows).drop_duplicates(subset=["model"])
    pareto = (
        data.groupby("params_total", as_index=False)["success_rate"]
        .max()
        .sort_values("params_total")
        .reset_index(drop=True)
    )
    pareto = pareto[pareto["success_rate"].cummax().eq(pareto["success_rate"])]

    fig, ax = plt.subplots(figsize=(13.4, 8.2))
    ax.plot(
        pareto["params_total"],
        pareto["success_rate"],
        color="#d95f02",
        linestyle="--",
        linewidth=2.0,
        alpha=0.75,
        marker="o",
        markersize=4,
        zorder=2,
    )
    ax.text(
        115,
        75.4,
        "Pareto front",
        color="#d95f02",
        fontsize=14,
        fontweight="bold",
        ha="left",
        va="bottom",
        bbox={"boxstyle": "round,pad=0.2", "fc": "white", "ec": "#d95f02", "lw": 0.6, "alpha": 0.9},
    )
    ax.scatter(
        selected_df["params_total"],
        selected_df["success_rate"],
        s=105,
        c=selected_df["label_color"],
        alpha=0.95,
        edgecolors="black",
        linewidths=0.45,
        label="Highlighted open/local peers",
        zorder=3,
    )
    ax.set_xscale("log")
    ax.set_xlim(20, 1600)
    ax.set_ylim(47, 82)
    ax.set_xlabel("Total parameters (B, log scale)", fontsize=18)
    ax.set_ylabel("SWE-Bench success rate (% resolved)", fontsize=18)
    ax.set_title("Parameter Efficiency of Kozuchi Agent vs Open/Local SWE-Bench Peers", fontsize=20, pad=14)
    ax.tick_params(axis="both", labelsize=18)
    ax.grid(True, which="both", linestyle="-", linewidth=0.5, alpha=0.25)
    for x_value in [27, 100, 300, 1000]:
        ax.axvline(x_value, color="0.62", linestyle="--", linewidth=0.8, alpha=0.45, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)

    placements = {
        "Kozuchi Agent\n+ Qwen3.5-27B": (59, 70.7, "left", "top", "arc3,rad=0.04"),
        "Qwen3.5-27B": (28, 69.6, "left", "top", "arc3,rad=-0.10"),
        "Qwen3.5-397B": (280, 74.0, "left", "top", "arc3,rad=-0.08"),
        "Kimi K2.5": (1100, 75, "right", "top", "arc3,rad=0.08"),
        "MiniMax M2.5": (140, 72, "left", "top", "arc3,rad=-0.08"),
        "Lingxi Kimi K2": (1090, 65.4, "right", "top", "arc3,rad=0.06"),
        "OpenHands\n+ Qwen3-Coder": (330, 65.8, "center", "top", "arc3,rad=-0.06"),
        "Code World Model": (36, 64.4, "left", "top", "arc3,rad=0.10"),
    }
    for _, row in selected_df.iterrows():
        label = f"{row['label']}\n{row['success_rate']:.1f}%, {row['params_total']:.0f}B"
        label_x, label_y, ha, va, connectionstyle = placements[row["label"]]
        ax.annotate(
            label,
            (row["params_total"], row["success_rate"]),
            xytext=(label_x, label_y),
            textcoords="data",
            fontsize=18.0,
            fontweight=row["label_weight"],
            ha=ha,
            va=va,
            annotation_clip=True,
            bbox={"boxstyle": "round,pad=0.24", "fc": "white", "ec": "0.72", "lw": 0.55, "alpha": 0.95},
            arrowprops={
                "arrowstyle": "->",
                "color": "0.35",
                "lw": 1.0,
                "alpha": 0.75,
                "shrinkA": 8,
                "shrinkB": 7,
                "mutation_scale": 11,
                "connectionstyle": connectionstyle,
            },
        )
    ax.text(
        0.01,
        0.02,
        "Labels: model, SWE-Bench success rate, total parameters. Dashed orange line: Pareto front.",
        transform=ax.transAxes,
        fontsize=11.0,
        color="0.35",
        ha="left",
        va="bottom",
    )
    out = PLOTS_DIR / "broad_success_vs_params.png"
    fig.subplots_adjust(left=0.09, right=0.98, bottom=0.13, top=0.9)
    fig.savefig(out, dpi=240)
    plt.close(fig)
    return out


def plot_open_bar(broad: pd.DataFrame) -> Path:
    data = selected_open_rows(broad).copy()
    data = data.sort_values("success_rate", ascending=True)
    colors = ["#d95f02" if bool(v) else "#1f77b4" for v in data["is_kozuchi"]]

    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    ax.barh(data["model"], data["success_rate"], color=colors, alpha=0.9)
    for y, (_, row) in enumerate(data.iterrows()):
        params = fmt_num(row["params_total"], 0)
        ax.text(row["success_rate"] + 0.4, y, f"{row['success_rate']:.1f}% / {params}B", va="center", fontsize=8.5)
    ax.set_xlabel("Success Rate [%]")
    ax.set_title("Selected Open/Local SWE-Bench Comparisons")
    ax.set_xlim(0, max(data["success_rate"]) + 9)
    ax.grid(axis="x", alpha=0.25)

    out = PLOTS_DIR / "selected_open_local_bar.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_java_custom(java: pd.DataFrame) -> Path:
    data = custom_java_rows(java)
    colors = ["#d95f02" if bool(v) else "#4c78a8" for v in data["is_kozuchi"]]

    fig, ax = plt.subplots(figsize=(10.8, 5.8))
    ax.barh(data["model"], data["success_rate"], color=colors, alpha=0.9)
    for y, (_, row) in enumerate(data.iterrows()):
        params = fmt_num(row["params_total"], 0)
        ax.text(row["success_rate"] + 0.4, y, f"{row['success_rate']:.2f}% / {params}B", va="center", fontsize=8.5)
    ax.set_xlabel("Success Rate [%]")
    ax.set_title("Java Map: Custom Open/Local Rows")
    ax.set_xlim(0, max(data["success_rate"]) + 12)
    ax.grid(axis="x", alpha=0.25)

    out = PLOTS_DIR / "java_custom_rows.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def plot_efficiency(broad: pd.DataFrame, java: pd.DataFrame) -> Path:
    broad_eff = selected_open_rows(broad).assign(scope="Broad SWE-Bench map")
    java_eff = custom_java_rows(java).assign(scope="Java custom rows")
    data = pd.concat([broad_eff, java_eff], ignore_index=True)
    data = data[data["params_total"].notna() & (data["params_total"] > 0)].copy()
    data["pp_per_b"] = data["success_rate"] / data["params_total"]
    data["short_model"] = data["model"].str.replace("Kozuchi mini-swe-agent + ", "Kozuchi + ", regex=False)
    data["display_model"] = data["scope"].str.replace(" map", "", regex=False) + ": " + data["short_model"]
    data = data.sort_values("pp_per_b", ascending=True).tail(14)
    colors = ["#d95f02" if bool(v) else "#2f4b7c" for v in data["is_kozuchi"]]

    fig, ax = plt.subplots(figsize=(11.8, 6.4))
    ax.barh(data["display_model"], data["pp_per_b"], color=colors, alpha=0.9)
    ax.set_xlabel("Success-rate points per total parameter B")
    ax.set_title("Parameter Efficiency Snapshot")
    ax.grid(axis="x", alpha=0.25)
    for y, (_, row) in enumerate(data.iterrows()):
        ax.text(row["pp_per_b"] + 0.03, y, f"{row['pp_per_b']:.2f}", va="center", fontsize=8.5)

    out = PLOTS_DIR / "parameter_efficiency.png"
    fig.tight_layout()
    fig.savefig(out, dpi=180)
    plt.close(fig)
    return out


def build_report(broad: pd.DataFrame, java: pd.DataFrame, plots: list[Path]) -> str:
    koz_broad = one_row(broad, KOZUCHI)
    koz_java = one_row(java, KOZUCHI)
    official = broad[broad["is_official_leaderboard"] & broad["success_rate"].notna()]
    open_local = broad[broad["is_open_or_local"] & broad["success_rate"].notna()]
    with_params = broad[broad["params_total"].notna() & broad["success_rate"].notna() & (broad["params_total"] > 0)]
    broad_comps, java_comps = comparison_rows(broad, java)

    broad_rows = [
        {
            "Comparison": item.name,
            "Peer Success": fmt_pct(item.success_rate),
            "Peer Params": f"{fmt_num(item.params_total, 1)}B",
            "Kozuchi Delta": fmt_delta(item.delta_pp),
            "Peer / Kozuchi Params": f"{fmt_num(item.size_ratio, 1)}x" if item.size_ratio else "n/a",
            "Read": item.note,
        }
        for item in broad_comps
    ]
    java_rows = [
        {
            "Comparison": item.name,
            "Peer Success": fmt_pct(item.success_rate, 2),
            "Peer Params": f"{fmt_num(item.params_total, 1)}B",
            "Kozuchi Delta": fmt_delta(item.delta_pp, 2),
            "Peer / Kozuchi Params": f"{fmt_num(item.size_ratio, 1)}x" if item.size_ratio else "n/a",
            "Read": item.note,
        }
        for item in java_comps
    ]

    top_open = selected_open_rows(broad).sort_values("success_rate", ascending=False)
    top_open_rows = [
        {
            "Rank": i + 1,
            "Model": row["model"],
            "Success": fmt_pct(row["success_rate"]),
            "Params": f"{fmt_num(row['params_total'], 1)}B",
            "Efficiency": fmt_num(row["efficiency_pp_per_b"], 2),
        }
        for i, (_, row) in enumerate(top_open.head(10).iterrows())
    ]

    java_custom = custom_java_rows(java).sort_values("success_rate", ascending=False)
    java_custom_rows = [
        {
            "Rank": i + 1,
            "Model": row["model"],
            "Success": fmt_pct(row["success_rate"], 2),
            "Params": f"{fmt_num(row['params_total'], 1)}B",
            "Efficiency": fmt_num(row["efficiency_pp_per_b"], 2),
        }
        for i, (_, row) in enumerate(java_custom.iterrows())
    ]

    broad_eff_rank = rank_position(with_params["efficiency_pp_per_b"], koz_broad["efficiency_pp_per_b"])
    java_eff = java_custom[java_custom["params_total"].notna()].copy()
    java_eff_rank = rank_position(java_eff["efficiency_pp_per_b"], koz_java["efficiency_pp_per_b"])

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    plot_lines = "\n".join(f"![{plot.stem}](plots/{plot.name})" for plot in plots)

    return f"""# SWE-Bench Comparison Analysis

Generated: {generated}

Source workbook: `SWE-bench comparison.xlsx`

## Executive Takeaway

Kozuchi mini-SWE-agent + Qwen3.5-27B is the parameter-efficiency outlier in the broad SWE-Bench comparison: **{fmt_pct(koz_broad['success_rate'])}** using a **27B** model. Against official leaderboard rows in the same sheet it would sit at about **rank {rank_position(official['success_rate'], koz_broad['success_rate'])} of {len(official) + 1}** if inserted, and it is **rank {rank_position(open_local['success_rate'], koz_broad['success_rate'])} of {len(open_local)}** among open/local rows in the workbook snapshot.

The Java-specific map tells a different story: Kozuchi is **{fmt_pct(koz_java['success_rate'], 2)}**, placing it second among the custom Java-row open/local comparisons in this workbook, behind CodeArts MiniMax M2.5. The Java result is therefore strong on efficiency but not yet the raw-success leader.

## Broad SWE-Bench Map

- Kozuchi improves over the base `Qwen3.5-27B` row by **{fmt_delta(koz_broad['success_rate'] - one_row(broad, 'Qwen3.5-27B')['success_rate'])}** with the same listed total parameter count.
- It beats `Code World Model` by **{fmt_delta(koz_broad['success_rate'] - one_row(broad, 'Code World Model')['success_rate'])}** while using **27B vs 32.6B** total parameters.
- It trails much larger frontier open/local rows only slightly: **{fmt_delta(koz_broad['success_rate'] - one_row(broad, 'Qwen3.5-397B')['success_rate'])}** vs `Qwen3.5-397B`, **{fmt_delta(koz_broad['success_rate'] - one_row(broad, 'Kimi-K2.5-1T')['success_rate'])}** vs `Kimi-K2.5-1T`, and **{fmt_delta(koz_broad['success_rate'] - one_row(broad, 'mini-SWE-agent + MiniMax M2.5')['success_rate'])}** vs `mini-SWE-agent + MiniMax M2.5`.
- Among rows with known total parameters, Kozuchi is **rank {broad_eff_rank} of {len(with_params)}** by success-rate points per parameter B, and it is the top row among models with `params_total <= 50B`.

{markdown_table(broad_rows, ["Comparison", "Peer Success", "Peer Params", "Kozuchi Delta", "Peer / Kozuchi Params", "Read"])}

## Selected Open/Local Ranking

{markdown_table(top_open_rows, ["Rank", "Model", "Success", "Params", "Efficiency"])}

## Java Map

Kozuchi's Java-row result is **{fmt_pct(koz_java['success_rate'], 2)}**. It is **{fmt_delta(koz_java['success_rate'] - one_row(java, 'MSWE-agent + CodeArts-MiniMax-M2.5')['success_rate'], 2)}** above the closest lower peer (`MSWE-agent + CodeArts-MiniMax-M2.5`) and **{fmt_delta(koz_java['success_rate'] - one_row(java, 'CodeArts Agent + CodeArts-MiniMax-M2.5')['success_rate'], 2)}** behind the custom-row leader (`CodeArts Agent + CodeArts-MiniMax-M2.5`). Because Kozuchi is listed at 27B and CodeArts MiniMax is listed at 229B, Kozuchi has a much stronger efficiency profile despite lower raw success.

{markdown_table(java_rows, ["Comparison", "Peer Success", "Peer Params", "Kozuchi Delta", "Peer / Kozuchi Params", "Read"])}

## Java Custom-Row Ranking

{markdown_table(java_custom_rows, ["Rank", "Model", "Success", "Params", "Efficiency"])}

## Data Quality Notes

- The mapped sheets contain official leaderboard rows and manually added non-leaderboard snapshot rows; rank statements above explicitly separate those cases.
- `Local LLM = O` is treated as open/local and `X` as non-local/proprietary, following the workbook labels.
- Some manually added Java rows appear to reuse model-family fields from the broad map; the report prioritizes the `Model (Coding Agent+LLM)`, success-rate, and total-parameter columns for comparisons.
- Parameter-efficiency uses listed total parameters, not activated parameters, because activated parameters are missing for several relevant 27B and Java rows.

## Plots

{plot_lines}

## Reproducibility

Regenerate this report and all plots with:

```bash
uv run paper/comparison/src/analyze_comparison.py
```
"""


def main() -> None:
    sns.set_theme(style="whitegrid", context="paper")
    broad = load_map(SHEETS["broad"])
    java = load_map(SHEETS["java"])

    plots = [
        plot_broad_scatter(broad),
        plot_open_bar(broad),
        plot_java_custom(java),
        plot_efficiency(broad, java),
    ]
    REPORT.write_text(build_report(broad, java, plots), encoding="utf-8")
    print(f"Wrote {REPORT}")
    for plot in plots:
        print(f"Wrote {plot}")


if __name__ == "__main__":
    main()
