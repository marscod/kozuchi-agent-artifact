"""Inventory of phase-gated skills declared in ``agent_sota.yaml``.

For each skill we record its title, the phases it is gated to, and the
tool prerequisites that must all be in ``agent.tools`` for the skill to
be injected into the prompt. The manuscript uses these counts to
ground its description of phase-gated skill injection.
"""

from __future__ import annotations

import json
import re

from _paths import CONFIG_AGENT_SOTA, STATS_DIR


_TITLE = re.compile(r"^\s{4}- title:\s+(.+?)\s*$")
_PHASES = re.compile(r"^\s{6}phases:\s*(.*)$")
_TOOLS = re.compile(r"^\s{6}tools:\s*(.*)$")
_LIST_ITEM = re.compile(r"^\s{8}-\s+([\w_*]+)\s*$")


def parse_skills(text: str) -> list[dict]:
    skills: list[dict] = []
    in_skills = False
    cur: dict | None = None
    list_target: str | None = None
    for raw in text.splitlines():
        if raw.startswith("  skills:"):
            in_skills = True
            continue
        if not in_skills:
            continue
        m_title = _TITLE.match(raw)
        if m_title:
            if cur is not None:
                skills.append(cur)
            cur = {"title": m_title.group(1), "phases": [], "tools": []}
            list_target = None
            continue
        if cur is None:
            continue
        m_phases = _PHASES.match(raw)
        if m_phases:
            inline = m_phases.group(1).strip()
            if inline.startswith("["):
                cur["phases"] = [
                    s.strip().strip('"') for s in inline.strip("[]").split(",") if s.strip()
                ]
                list_target = None
            else:
                list_target = "phases"
            continue
        m_tools = _TOOLS.match(raw)
        if m_tools:
            inline = m_tools.group(1).strip()
            if inline.startswith("["):
                cur["tools"] = [
                    s.strip().strip('"') for s in inline.strip("[]").split(",") if s.strip()
                ]
                list_target = None
            else:
                list_target = "tools"
            continue
        m_item = _LIST_ITEM.match(raw)
        if m_item and list_target is not None:
            cur[list_target].append(m_item.group(1))
            continue
    if cur is not None:
        skills.append(cur)
    return skills


def main() -> None:
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    text = CONFIG_AGENT_SOTA.read_text()
    skills = parse_skills(text)

    by_phase: dict[str, int] = {}
    for s in skills:
        for ph in s.get("phases", []):
            by_phase[ph] = by_phase.get(ph, 0) + 1

    by_tool: dict[str, int] = {}
    for s in skills:
        for t in s.get("tools", []):
            by_tool[t] = by_tool.get(t, 0) + 1

    out = {
        "n_skills": len(skills),
        "skills": skills,
        "skills_per_phase": dict(sorted(by_phase.items())),
        "skills_per_tool": dict(sorted(by_tool.items())),
    }
    (STATS_DIR / "skill_inventory.json").write_text(json.dumps(out, indent=2))
    print(
        json.dumps(
            {
                "n_skills": out["n_skills"],
                "skills_per_phase": out["skills_per_phase"],
                "skills_per_tool": out["skills_per_tool"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
