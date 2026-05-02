"""Inventory of agent tools.

Cross-references the redacted tool-files CSV under
``data/operational_metadata/tool_files.csv`` against what is *enabled*
in ``data/configs/agent_sota.yaml: agent.tools``. The raw tool sources
under ``swe_sota_agent/tools/`` are intentionally not shipped with the
artifact; the CSV captures only the file names the inventory needs.
"""

from __future__ import annotations

import csv
import json
import re

from _paths import CONFIG_AGENT_SOTA, STATS_DIR, TOOL_FILES_CSV


def parse_tool_list(text: str) -> tuple[list[str], list[str]]:
    """Return (active, disabled) tool names from ``agent.tools`` block."""
    active: list[str] = []
    disabled: list[str] = []
    in_block = False
    block_indent = "  tools:"
    for line in text.splitlines():
        if line.startswith(block_indent):
            in_block = True
            continue
        if in_block:
            if not line.strip():
                continue
            if line.startswith(" ") and not line.startswith("    "):
                # left the block
                break
            m_active = re.match(r"^\s{4}-\s+([\w_]+)\s*$", line)
            m_disabled = re.match(r"^\s{4}#\s*-\s+([\w_]+)\s*$", line)
            if m_active:
                active.append(m_active.group(1))
            elif m_disabled:
                disabled.append(m_disabled.group(1))
            else:
                # Unknown line shape - end of block.
                break
    return active, disabled


def _read_tool_files() -> list[str]:
    with TOOL_FILES_CSV.open() as f:
        return sorted({row["name"] for row in csv.DictReader(f) if row.get("name")})


def main() -> None:
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    text = CONFIG_AGENT_SOTA.read_text()
    active, disabled = parse_tool_list(text)

    on_disk = _read_tool_files()

    out = {
        "tool_files_source": "data/operational_metadata/tool_files.csv",
        "on_disk": on_disk,
        "active_in_config": active,
        "disabled_in_config": disabled,
        "active_but_missing_on_disk": sorted(
            t for t in active if t not in on_disk
        ),
        "on_disk_but_not_active": sorted(
            t for t in on_disk if t not in active and t not in disabled
        ),
    }
    (STATS_DIR / "tool_inventory.json").write_text(json.dumps(out, indent=2))

    tex = [
        "% Auto-generated: agent tool inventory.",
        "% Source: data/configs/agent_sota.yaml (agent.tools) + data/operational_metadata/tool_files.csv",
        r"\begin{tabular}{lll}",
        r"\toprule",
        r"Tool & On disk & In \code{agent.tools} \\",
        r"\midrule",
    ]
    everything = sorted(set(on_disk) | set(active) | set(disabled))
    for t in everything:
        on_disk_marker = "yes" if t in on_disk else "--"
        if t in active:
            cfg_marker = "active"
        elif t in disabled:
            cfg_marker = "commented out"
        else:
            cfg_marker = "--"
        escaped = t.replace("_", r"\_")
        tex.append(f"\\code{{{escaped}}} & {on_disk_marker} & {cfg_marker} \\\\")
    tex.append(r"\bottomrule")
    tex.append(r"\end{tabular}")
    (STATS_DIR / "tool_inventory.tex").write_text("\n".join(tex) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
