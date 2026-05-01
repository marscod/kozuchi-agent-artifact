"""Enumerate the agent phase graph from ``configs/agent_sota.yaml``.

Emits the list of phase nodes, their ``on_complete``/``on_giveup``
successors, and an edge list. Uses a tiny purpose-built YAML reader so
this script does not require ``pyyaml``.
"""

from __future__ import annotations

import json
import re

from _paths import CONFIG_AGENT_SOTA, STATS_DIR


def parse_phases(text: str) -> list[dict]:
    """Parse the ``agent.phases`` block.

    Each phase entry has the shape::

        - name: <NAME>
          next_phase:
            # optional inline comments
            on_complete: <NEXT_NAME>
            on_giveup: <NEXT_NAME>

    We deliberately tolerate comment lines and arbitrary blank lines
    between the keys.
    """
    phases: list[dict] = []
    name_re = re.compile(r"^\s{4}-\s+name:\s+(\w+)\s*$")
    on_complete_re = re.compile(r"^\s{8}on_complete:\s+(\S+)\s*$")
    on_giveup_re = re.compile(r"^\s{8}on_giveup:\s+(\S+)\s*$")
    cur: dict | None = None
    in_block = False
    for line in text.splitlines():
        if re.match(r"^\s{2}phases:\s*$", line):
            in_block = True
            continue
        if in_block and re.match(r"^\s{2}\w+:\s*$", line):
            in_block = False
        if not in_block:
            continue
        m_name = name_re.match(line)
        if m_name:
            if cur is not None:
                phases.append(cur)
            cur = {"name": m_name.group(1), "on_complete": None, "on_giveup": None}
            continue
        if cur is None:
            continue
        m_oc = on_complete_re.match(line)
        if m_oc:
            cur["on_complete"] = None if m_oc.group(1) == "null" else m_oc.group(1)
            continue
        m_og = on_giveup_re.match(line)
        if m_og:
            cur["on_giveup"] = None if m_og.group(1) == "null" else m_og.group(1)
            continue
    if cur is not None:
        phases.append(cur)
    return phases


def main() -> None:
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    text = CONFIG_AGENT_SOTA.read_text()
    phases = parse_phases(text)
    edges: list[dict] = []
    for ph in phases:
        if ph["on_complete"]:
            edges.append(
                {"from": ph["name"], "label": "on_complete", "to": ph["on_complete"]}
            )
        if ph["on_giveup"]:
            edges.append(
                {"from": ph["name"], "label": "on_giveup", "to": ph["on_giveup"]}
            )
    initial = re.search(r"^\s{2}initial_phase:\s+(\w+)", text, re.MULTILINE)
    out = {
        "initial_phase": initial.group(1) if initial else None,
        "phases": phases,
        "edges": edges,
        "n_phases": len(phases),
        "n_edges": len(edges),
    }
    (STATS_DIR / "phase_inventory.json").write_text(json.dumps(out, indent=2))

    csv_lines = ["from,label,to"]
    for e in edges:
        csv_lines.append(f"{e['from']},{e['label']},{e['to']}")
    (STATS_DIR / "phase_edges.csv").write_text("\n".join(csv_lines) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
