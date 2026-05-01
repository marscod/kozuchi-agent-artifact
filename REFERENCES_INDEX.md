# References Index for `paper/references.bib`

This file enumerates every `@entry{}` in
[`paper/references.bib`](paper/references.bib) with its publishable URL
and a one-line note explaining why the paper cites it. The source of
truth for the URLs is also recorded in
[`paper/source-index.md`](paper/source-index.md).

For each entry below, "Cite as" is the BibTeX key you reference inside
`main.tex` (e.g. `\cite{jimenez2024swebench}`).

---

## Benchmarks and evaluation

| Cite as | URL | Used in paper for |
|---|---|---|
| `jimenez2024swebench` | https://openreview.net/forum?id=VTF8yNQM66 | Defines SWE-bench and the repository-level issue-resolution evaluation setup. |
| `openai2024swebenchverified` | https://openai.com/index/introducing-swe-bench-verified/ | Grounds the SWE-bench Verified subset and official evaluator context. |
| `sbcli2026` | https://www.swebench.com/sb-cli/ | Cloud evaluation CLI used for the Python headline result. |
| `zan2025multiswebench` | https://arxiv.org/abs/2504.02605 | Grounds Multi-SWE-bench and the multilingual / Java issue-resolution benchmark context. |

## Agent runtimes and prior agent designs

| Cite as | URL | Used for |
|---|---|---|
| `yang2024sweagent` | https://proceedings.neurips.cc/paper_files/paper/2024/hash/5a7c947568c1b1328ccc5230172e1e7c-Abstract-Conference.html | Closest prior agent-computer-interface pattern for SWE agents. |
| `miniswea` | https://github.com/SWE-agent/mini-swe-agent | Identifies the minimal open-source runtime Kozuchi Agent builds on. |
| `xia2024agentless` | https://arxiv.org/abs/2407.01489 | Contrasts the long agentic loop with a localization-fix-verify pipeline. |
| `wang2024openhands` | https://arxiv.org/abs/2407.16741 | Open software-agent platform work adjacent to Kozuchi Agent. |
| `zhang2024autocoderover` | https://doi.org/10.1145/3650212.3680384 | Autonomous program-improvement work evaluated on SWE-style tasks. |
| `cortexa2025` | https://proceedings.mlr.press/v267/sohrabizadeh25a.html | Recent SWE-agent enhancement through localization and diversity. |
| `r2egym2025` | https://arxiv.org/abs/2504.07164 | Verifier and BEST@K work for open-weight SWE agents. |

## Reasoning / acting / reflective agent patterns

| Cite as | URL | Used for |
|---|---|---|
| `yao2023react` | https://arxiv.org/abs/2210.03629 | Observe-reason-act loop used to describe modern tool-using agents. |
| `shinn2023reflexion` | https://openreview.net/forum?id=vAElhFcKW6 | Reflective language-agent behavior and long-horizon retry patterns. |
| `madaan2023selfrefine` | https://arxiv.org/abs/2303.17651 | Iterative self-feedback and refinement as related agent-loop machinery. |
| `yao2023tree` | https://arxiv.org/abs/2305.10601 | Deliberate multi-step reasoning as related long-horizon agent planning work. |
| `komoravolu2026agent` | https://aclanthology.org/2026.eacl-long.339/ | Cross-agent testing as a related evaluation/agent-testing idea. |
| `schick2023toolformer` | https://proceedings.neurips.cc/paper_files/paper/2023/hash/d842425e4bf79ba039352da0f658a906-Abstract-Conference.html | Model-side tool-use training, contrasted with Kozuchi's harness-side tools. |

## Code generation and program repair (pre-SWE-bench)

| Cite as | URL | Used for |
|---|---|---|
| `chen2021codex` | https://arxiv.org/abs/2107.03374 | HumanEval, Codex, and pass@k / pass@1 terminology for code generation. |
| `hendrycks2021apps` | https://arxiv.org/abs/2105.09938 | Pre-SWE-bench code-generation benchmark context. |
| `li2022alphacode` | https://doi.org/10.1126/science.abq1158 | Large-sample competitive programming generation as prior code-model evaluation. |
| `chen2023codet` | https://openreview.net/forum?id=ktrw68Cmu9c | Generated tests as execution evidence for selecting generated code. |
| `legoues2012genprog` | https://doi.org/10.1109/TSE.2011.104 | Classic automatic program repair before LLM agents. |
| `long2016prophet` | https://doi.org/10.1145/2837614.2837617 | Learned patch generation in automatic repair. |
| `gazzola2019automatic` | https://doi.org/10.1109/TSE.2017.2755013 | Broader automatic software repair literature. |
| `Zhengetal2024` | https://aclanthology.org/2024.findings-acl.762/ | Execution / refinement benefits for code LLMs beyond model choice alone. |

## Industry coding agents and CI / CD

| Cite as | URL | Used for |
|---|---|---|
| `githubcopilotagent2025` | https://docs.github.com/copilot/concepts/agents/coding-agent/about-coding-agent | GitHub's cloud coding-agent product context. |
| `amazonqdeveloper2024` | https://aws.amazon.com/blogs/devops/reinventing-the-amazon-q-developer-agent-for-software-development/ | Amazon Q Developer's agentic software-development product context. |
| `googlejules2025` | https://blog.google/innovation-and-ai/models-and-research/google-labs/jules/ | Google's asynchronous coding-agent product context. |
| `openaicodex2025` | https://openai.com/index/introducing-codex/ | OpenAI Codex as a production coding-agent / product reference. |
| `anthropicclaudecode2025` | https://code.claude.com/docs/en/overview | Claude Code as a production coding-agent / product reference. |
| `devin2024` | https://www.cognition.ai/blog/introducing-devin | Cognition Devin as an industrial issue-to-patch agent reference. |
| `openaifunctioncalling2026` | https://developers.openai.com/api/docs/guides/function-calling | Model-family tool / function-calling syntax differences. |
| `anthropictooluse2026` | https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview | Anthropic tool-use syntax and model-family action formatting. |
| `logsage2025` | https://arxiv.org/abs/2506.03691 | LLM-enabled CI/CD failure remediation as adjacent industrial CI work. |

## Open-weight model backbones cited or inventoried

| Cite as | URL | Used for |
|---|---|---|
| `qwen35` | https://huggingface.co/Qwen/Qwen3.5-27B | Headline 27 B open-weight backbone. |
| `devstral` | https://huggingface.co/mistralai/Devstral-Small-2-24B-Instruct-2512 | Inventoried open-weight backend model. |
| `nemotron` | https://huggingface.co/nvidia/Llama-3_3-Nemotron-Super-49B-v1_5 | Inventoried Nemotron backend models and related open-weight context. |

## Serving stack and clusters

| Cite as | URL | Used for |
|---|---|---|
| `kwon2023vllm` | https://doi.org/10.1145/3600006.3613165 | vLLM serving layer used for local / multi-server inference. |
| `yoo2003slurm` | https://doi.org/10.1007/10968987_3 | SLURM as the scheduler abstraction for cluster jobs. |

## CI / DevOps theory

| Cite as | URL | Used for |
|---|---|---|
| `hilton2016ci` | https://doi.org/10.1145/2970276.2970358 | Empirical CI usage, costs, and benefits in software projects. |
| `fowler2006ci` | https://martinfowler.com/articles/continuousIntegration.html | The continuous-integration practice described in the pipeline section. |
| `duvall2007ci` | https://www.informit.com/store/continuous-integration-improving-software-quality-and-9780321336385 | CI as repeatable, risk-reducing build / test automation. |
| `epoch2024swebenchdocker` | https://epoch.ai/blog/swebench-docker | Docker-based SWE-bench runtime estimate used in workflow replacement. |

## Statistics and confidence intervals

| Cite as | URL | Used for |
|---|---|---|
| `wilson1927score` | https://doi.org/10.1080/01621459.1927.10502953 | Wilson confidence intervals reported for headline rates. |
| `mcnemar1947note` | https://doi.org/10.1007/BF02295996 | Paired binary outcome tests for peer comparisons. |
| `holm1979simple` | https://www.jstor.org/stable/4615733 | Family-wise multiple-comparison correction. |
| `benjamini1995controlling` | https://doi.org/10.1111/j.2517-6161.1995.tb02031.x | False-discovery-rate correction (used as headline FDR control). |
| `clopper1934use` | https://doi.org/10.1093/biomet/26.4.404 | Exact confidence intervals for paired effect-size tables. |

---

## How the paper uses the bibliography

The LaTeX file uses **citations grouped by topic**:

* §1 (intro / pains): `jimenez2024swebench`, `Zhengetal2024`,
  `yang2024sweagent`, `yao2023react`, `shinn2023reflexion`,
  `openaifunctioncalling2026`, `anthropictooluse2026`,
  `openai2024swebenchverified`, `sbcli2026`, `yoo2003slurm`,
  `miniswea`, `komoravolu2026agent`.
* §2 Related Work: clustered as listed in the tables above
  (agentic SWE systems, industry coding agents, training & CI).
* §3 Background: `jimenez2024swebench`,
  `chen2021codex`, `hendrycks2021apps`, `li2022alphacode`,
  `legoues2012genprog`, `long2016prophet`, `gazzola2019automatic`,
  `openai2024swebenchverified`, `sbcli2026`, `zan2025multiswebench`,
  `epoch2024swebenchdocker`, `hilton2016ci`, `kwon2023vllm`,
  `fowler2006ci`, `duvall2007ci`.
* §RQ1 / §RQ6 statistics: `wilson1927score`, `mcnemar1947note`,
  `holm1979simple`, `benjamini1995controlling`, `clopper1934use`.
* §RQ5 / Selection: `chen2021codex` (pass@k terminology),
  `chen2023codet`, `r2egym2025`.
* §References artifact lines: `qwen35`, `devstral`, `nemotron` are
  `\nocite{}`-d so they always appear in the bibliography even when
  the model identifier is mentioned only inside a stats fragment.

If you add a new entry to `paper/references.bib`, please add a row
above so the index stays canonical.
