"""List available model and chat-template configs.

Reads ``configs/model_*.yaml``, ``configs/chat-template_*.yaml`` and
``configs/environment_*.yaml`` to emit a JSON summary of the
model-agnostic serving surface, and a LaTeX fragment that just lists the
backends.
"""

from __future__ import annotations

import json

from _paths import CONFIG_DIR, STATS_DIR


def main() -> None:
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    models = sorted(p.stem for p in CONFIG_DIR.glob("model_*.yaml"))
    chat_templates = sorted(p.stem for p in CONFIG_DIR.glob("chat-template_*.yaml"))
    environments = sorted(p.stem for p in CONFIG_DIR.glob("environment_*.yaml"))
    out = {
        "models": models,
        "chat_templates": chat_templates,
        "environments": environments,
        "n_models": len(models),
        "n_chat_templates": len(chat_templates),
        "n_environments": len(environments),
    }
    (STATS_DIR / "model_inventory.json").write_text(json.dumps(out, indent=2))

    tex = [
        "% Auto-generated: configs/ inventory (model_*, chat-template_*, environment_*).",
        r"\begin{tabular}{lr}",
        r"\toprule",
        r"Config family & Count \\",
        r"\midrule",
        f"\\code{{model\\_*.yaml}} (backends)            & {out['n_models']} \\\\",
        f"\\code{{chat-template\\_*.yaml}} (vLLM models) & {out['n_chat_templates']} \\\\",
        f"\\code{{environment\\_*.yaml}} (sandboxes)     & {out['n_environments']} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
    ]
    (STATS_DIR / "model_inventory.tex").write_text("\n".join(tex) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
