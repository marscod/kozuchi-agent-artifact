"""Render compact figures and a short analysis.md from generated CSVs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from utils import EXPERIMENT_DIR


TARGET = EXPERIMENT_DIR.name
COLOR_MAIN = "#2f6f9f"
COLOR_ACCENT = "#c65f3f"
COLOR_MUTED = "#7a8793"
COLOR_GRID = "#d7dde3"


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#ccd3da",
            "axes.grid": True,
            "grid.color": COLOR_GRID,
            "grid.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
        }
    )


def _save(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _overview(csv_dir: Path, fig_dir: Path) -> None:
    headline = pd.read_csv(csv_dir / "headline.csv")
    by_diff = pd.read_csv(csv_dir / "by_difficulty.csv")
    by_repo = pd.read_csv(csv_dir / "by_repo.csv").head(8)
    failures = pd.read_csv(csv_dir / "failure_modes.csv").head(8)

    resolved_row = headline[headline["metric"] == "resolved_xcheck_at_8"].iloc[0]
    valid_row = headline[headline["metric"] == "report_valid"].iloc[0]

    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    ax = axes[0, 0]
    labels = ["Leaderboard\nresolved", "Report\nvalid"]
    values = [resolved_row["value"], valid_row["value"]]
    bars = ax.bar(labels, values, color=[COLOR_MAIN, COLOR_ACCENT])
    ax.set_ylim(0, 1)
    ax.set_ylabel("Rate")
    ax.set_title("Headline")
    for bar, row in zip(bars, [resolved_row, valid_row]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.025,
            f"{int(row['numerator'])}/{int(row['denominator'])}\n{row['value']:.1%}",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    ax = axes[0, 1]
    order = {"easy": 0, "medium": 1, "hard": 2}
    by_diff = by_diff.sort_values("difficulty", key=lambda s: s.map(order).fillna(9))
    ax.bar(by_diff["difficulty"], by_diff["rate"], color=COLOR_MAIN)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Resolution rate")
    ax.set_title("By Difficulty")
    for i, row in by_diff.reset_index(drop=True).iterrows():
        ax.text(i, row["rate"] + 0.025, f"{int(row['resolved'])}/{int(row['n'])}", ha="center", fontsize=8)

    ax = axes[1, 0]
    ax.barh(by_repo["repo"], by_repo["rate"], color=COLOR_MAIN)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("Resolution rate")
    ax.set_title("Largest Repositories")

    ax = axes[1, 1]
    ax.barh(failures["failure_mode"], failures["n"], color=COLOR_ACCENT)
    ax.invert_yaxis()
    ax.set_xlabel("Unresolved instances")
    ax.set_title("Failure Modes")
    _save(fig, fig_dir / "fig00_overview.png")


def _leaderboard(csv_dir: Path, fig_dir: Path) -> None:
    leaderboard = pd.read_csv(csv_dir / "leaderboard.csv").head(15).iloc[::-1]
    colors = [COLOR_ACCENT if folder == TARGET else COLOR_MUTED for folder in leaderboard["folder"]]
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(leaderboard["name"], leaderboard["rate"], color=colors)
    ax.set_xlim(0, max(0.55, float(leaderboard["rate"].max()) + 0.05))
    ax.set_xlabel("Resolution rate")
    ax.set_title("Java Verified Leaderboard Context")
    for i, (_, row) in enumerate(leaderboard.iterrows()):
        ax.text(row["rate"] + 0.01, i, f"{int(row['resolved_instances'])}/128", va="center", fontsize=8)
    _save(fig, fig_dir / "fig01_leaderboard.png")


def _patch_and_effort(csv_dir: Path, fig_dir: Path) -> None:
    patch = pd.read_csv(csv_dir / "patch_size_buckets.csv")
    effort = pd.read_csv(csv_dir / "effort_buckets.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))

    ax = axes[0]
    ax.bar(patch["bucket"], patch["rate"], color=COLOR_MAIN)
    ax.set_ylim(0, 1)
    ax.set_title("Patch Churn")
    ax.set_xlabel("LOC churn bucket")
    ax.set_ylabel("Resolution rate")
    ax.tick_params(axis="x", rotation=30)
    for i, row in patch.iterrows():
        ax.text(i, row["rate"] + 0.025, str(int(row["n"])), ha="center", fontsize=8)

    ax = axes[1]
    ax.bar(effort["bucket"], effort["rate"], color=COLOR_MAIN)
    ax.set_ylim(0, 1)
    ax.set_title("Agent Effort")
    ax.set_xlabel("API call bucket")
    ax.set_ylabel("Resolution rate")
    ax.tick_params(axis="x", rotation=30)
    for i, row in effort.iterrows():
        ax.text(i, row["rate"] + 0.025, str(int(row["n"])), ha="center", fontsize=8)

    _save(fig, fig_dir / "fig02_patch_effort.png")


def _write_report(csv_dir: Path, fig_dir: Path) -> None:
    headline = pd.read_csv(csv_dir / "headline.csv")
    by_diff = pd.read_csv(csv_dir / "by_difficulty.csv")
    operational = pd.read_csv(csv_dir / "operational.csv")
    leaderboard = pd.read_csv(csv_dir / "leaderboard.csv")
    failures = pd.read_csv(csv_dir / "failure_modes.csv")

    def metric(name: str) -> pd.Series:
        return headline[headline["metric"] == name].iloc[0]

    resolved = metric("resolved_xcheck_at_8")
    valid = metric("report_valid")
    full_traj = metric("full_trajectory_coverage")
    target_rank = leaderboard[leaderboard["folder"] == TARGET]["rank"]
    rank_text = str(int(target_rank.iloc[0])) if len(target_rank) else "n/a"
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Multi-SWE Java Analysis",
        "",
        f"Generated: {generated}",
        "",
        "## Headline",
        "",
        f"- Leaderboard result: {int(resolved['numerator'])}/{int(resolved['denominator'])} = {resolved['value']:.2%}.",
        f"- Report-valid count: {int(valid['numerator'])}/{int(valid['denominator'])} = {valid['value']:.2%}.",
        f"- Full trajectory coverage: {int(full_traj['numerator'])}/{int(full_traj['denominator'])} = {full_traj['value']:.2%}.",
        f"- Leaderboard rank among local Java verified entries: {rank_text}.",
        "",
        "## Difficulty",
        "",
    ]
    for _, row in by_diff.iterrows():
        lines.append(
            f"- {row['difficulty']}: {int(row['resolved'])}/{int(row['n'])} = {row['rate']:.2%}."
        )
    lines.extend(["", "## Top Failure Modes", ""])
    for _, row in failures.head(6).iterrows():
        lines.append(
            f"- {row['failure_mode']}: {int(row['n'])} unresolved ({row['share_of_unresolved']:.1%})."
        )
    lines.extend(
        [
            "",
            "## Figures",
            "",
            "![Overview](figures/fig00_overview.png)",
            "",
            "![Leaderboard](figures/fig01_leaderboard.png)",
            "",
            "![Patch and effort](figures/fig02_patch_effort.png)",
            "",
            "## CSV Outputs",
            "",
        ]
    )
    for path in sorted(csv_dir.glob("*.csv")):
        lines.append(f"- [{path.name}](csv/{path.name})")

    op_map = dict(zip(operational["metric"], operational["value"]))
    if float(op_map.get("report_valid_not_leaderboard_resolved", 0)) > 0:
        lines.extend(
            [
                "",
                "## Note",
                "",
                "Some Multi-SWE per-instance reports are marked valid but are not counted as leaderboard resolved in results/results.json. The analysis keeps the leaderboard result as authoritative and exposes this mismatch in report_valid_vs_results.csv.",
            ]
        )

    (EXPERIMENT_DIR / "src" / "analysis.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv-dir", type=Path, required=True)
    parser.add_argument("--fig-dir", type=Path, required=True)
    args = parser.parse_args()

    args.fig_dir.mkdir(parents=True, exist_ok=True)
    _style()
    _overview(args.csv_dir, args.fig_dir)
    _leaderboard(args.csv_dir, args.fig_dir)
    _patch_and_effort(args.csv_dir, args.fig_dir)
    _write_report(args.csv_dir, args.fig_dir)
    print("[make_figures] wrote fig00_overview.png, fig01_leaderboard.png, fig02_patch_effort.png, analysis.md")


if __name__ == "__main__":
    main()
