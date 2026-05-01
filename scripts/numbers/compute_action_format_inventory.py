"""Enumerate available action formats in ``configs/agent_sota.yaml``.

The agent supports multiple model-specific tool-call bracketings selected
by ``action_format_name``. This script lists each format and the active
default, and writes a tiny LaTeX fragment that the manuscript can include.
"""

from __future__ import annotations

import json
import re

from _paths import CONFIG_AGENT_SOTA, STATS_DIR


def main() -> None:
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    text = CONFIG_AGENT_SOTA.read_text()

    default = re.search(r"^\s{2}action_format_name:\s+(\S+)", text, re.MULTILINE)

    formats: list[str] = []
    in_block = False
    for line in text.splitlines():
        if re.match(r"^\s{2}action_format:", line):
            in_block = True
            continue
        if in_block:
            if re.match(r"^\s{2}\w+:", line):
                in_block = False
                break
            m = re.match(r"^\s{4}(\w+):", line)
            if m:
                formats.append(m.group(1))

    out = {
        "default_action_format": default.group(1) if default else None,
        "available_action_formats": formats,
        "n_formats": len(formats),
    }
    (STATS_DIR / "action_format_inventory.json").write_text(json.dumps(out, indent=2))

    tex = [
        "% Auto-generated: agent.action_format inventory.",
        r"\begin{tabular}{ll}",
        r"\toprule",
        r"Format & Notes \\",
        r"\midrule",
    ]
    for name in formats:
        marker = r"\textbf{(default)}" if name == out["default_action_format"] else ""
        escaped = name.replace("_", r"\_")
        tex.append(f"\\code{{{escaped}}} & {marker} \\\\")
    tex.append(r"\bottomrule")
    tex.append(r"\end{tabular}")
    (STATS_DIR / "action_format_inventory.tex").write_text("\n".join(tex) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
