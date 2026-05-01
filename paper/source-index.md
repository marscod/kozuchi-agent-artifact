# Source Index

This index records external sources cited by `main.tex`, their URLs, and why each source is used in the paper. Internal experiment CSVs, generated figures, and trajectory artifacts are documented inline in LaTeX comments and are not repeated here.

| Key | URL | Why used |
|---|---|---|
| `jimenez2024swebench` | https://openreview.net/forum?id=VTF8yNQM66 | Defines SWE-bench and the repository-level issue-resolution evaluation setup. |
| `openai2024swebenchverified` | https://openai.com/index/introducing-swe-bench-verified/ | Grounds the SWE-bench Verified subset and official evaluator context. |
| `sbcli2026` | https://www.swebench.com/sb-cli/ | Documents the cloud evaluation CLI used for the Python headline result. |
| `zan2025multiswebench` | https://arxiv.org/abs/2504.02605 | Grounds Multi-SWE-bench and the multilingual/Java issue-resolution benchmark context. |
| `yang2024sweagent` | https://proceedings.neurips.cc/paper_files/paper/2024/hash/5a7c947568c1b1328ccc5230172e1e7c-Abstract-Conference.html | Provides the closest prior agent-computer-interface pattern for SWE agents. |
| `miniswea` | https://github.com/SWE-agent/mini-swe-agent | Identifies the minimal open-source runtime Kozuchi Agent builds on. |
| `xia2024agentless` | https://arxiv.org/abs/2407.01489 | Contrasts the paper's long agentic loop with a localization-fix-verify pipeline. |
| `wang2024openhands` | https://arxiv.org/abs/2407.16741 | Grounds open software-agent platform work adjacent to Kozuchi Agent. |
| `zhang2024autocoderover` | https://doi.org/10.1145/3650212.3680384 | Grounds autonomous program-improvement work evaluated on SWE-style tasks. |
| `yao2023react` | https://arxiv.org/abs/2210.03629 | Grounds the observe-reason-act loop used to describe modern tool-using agents. |
| `shinn2023reflexion` | https://openreview.net/forum?id=vAElhFcKW6 | Grounds reflective language-agent behavior and long-horizon retry patterns. |
| `madaan2023selfrefine` | https://arxiv.org/abs/2303.17651 | Grounds iterative self-feedback and refinement as related agent-loop machinery. |
| `yao2023tree` | https://arxiv.org/abs/2305.10601 | Grounds deliberate multi-step reasoning as related long-horizon agent planning work. |
| `komoravolu2026agent` | https://aclanthology.org/2026.eacl-long.339/ | Grounds cross-agent testing as a related evaluation/agent-testing idea. |
| `schick2023toolformer` | https://proceedings.neurips.cc/paper_files/paper/2023/hash/d842425e4bf79ba039352da0f658a906-Abstract-Conference.html | Grounds model-side tool-use training, contrasted with Kozuchi's harness-side tools. |
| `chen2021codex` | https://arxiv.org/abs/2107.03374 | Grounds HumanEval, Codex, and pass@k/pass@1 terminology for code generation. |
| `hendrycks2021apps` | https://arxiv.org/abs/2105.09938 | Grounds pre-SWE-bench code-generation benchmark context. |
| `li2022alphacode` | https://doi.org/10.1126/science.abq1158 | Grounds large-sample competitive programming generation as prior code-model evaluation. |
| `chen2023codet` | https://openreview.net/forum?id=ktrw68Cmu9c | Grounds generated tests as execution evidence for selecting generated code. |
| `legoues2012genprog` | https://doi.org/10.1109/TSE.2011.104 | Grounds classic automatic program repair before LLM agents. |
| `long2016prophet` | https://doi.org/10.1145/2837614.2837617 | Grounds learned patch generation in automatic repair. |
| `gazzola2019automatic` | https://doi.org/10.1109/TSE.2017.2755013 | Grounds the broader automatic software repair literature. |
| `Zhengetal2024` | https://aclanthology.org/2024.findings-acl.762/ | Grounds execution/refinement benefits for code LLMs beyond model choice alone. |
| `cortexa2025` | https://proceedings.mlr.press/v267/sohrabizadeh25a.html | Grounds recent SWE-agent enhancement through localization and diversity. |
| `r2egym2025` | https://arxiv.org/abs/2504.07164 | Grounds verifier and BEST@K work for open-weight SWE agents. |
| `logsage2025` | https://arxiv.org/abs/2506.03691 | Grounds LLM-enabled CI/CD failure remediation as adjacent industrial CI work. |
| `githubcopilotagent2025` | https://docs.github.com/copilot/concepts/agents/coding-agent/about-coding-agent | Grounds GitHub's cloud coding-agent product context. |
| `amazonqdeveloper2024` | https://aws.amazon.com/blogs/devops/reinventing-the-amazon-q-developer-agent-for-software-development/ | Grounds Amazon Q Developer's agentic software-development product context. |
| `googlejules2025` | https://blog.google/innovation-and-ai/models-and-research/google-labs/jules/ | Grounds Google's asynchronous coding-agent product context. |
| `openaicodex2025` | https://openai.com/index/introducing-codex/ | Grounds OpenAI Codex as a production coding-agent/product reference. |
| `anthropicclaudecode2025` | https://code.claude.com/docs/en/overview | Grounds Claude Code as a production coding-agent/product reference. |
| `devin2024` | https://www.cognition.ai/blog/introducing-devin | Grounds Cognition Devin as an industrial issue-to-patch agent reference. |
| `openaifunctioncalling2026` | https://developers.openai.com/api/docs/guides/function-calling | Grounds model-family tool/function-calling syntax differences. |
| `anthropictooluse2026` | https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview | Grounds Anthropic tool-use syntax and model-family action formatting. |
| `qwen35` | https://huggingface.co/Qwen/Qwen3.5-27B | Identifies the headline 27B open-weight backbone. |
| `devstral` | https://huggingface.co/mistralai/Devstral-Small-2-24B-Instruct-2512 | Documents one inventoried open-weight backend model. |
| `nemotron` | https://huggingface.co/nvidia/Llama-3_3-Nemotron-Super-49B-v1_5 | Documents inventoried Nemotron backend models and related open-weight context. |
| `kwon2023vllm` | https://doi.org/10.1145/3600006.3613165 | Grounds the vLLM serving layer used for local/multi-server inference. |
| `yoo2003slurm` | https://doi.org/10.1007/10968987_3 | Grounds SLURM as the scheduler abstraction for cluster jobs. |
| `hilton2016ci` | https://doi.org/10.1145/2970276.2970358 | Grounds empirical CI usage, costs, and benefits in software projects. |
| `fowler2006ci` | https://martinfowler.com/articles/continuousIntegration.html | Grounds the continuous-integration practice described in the pipeline section. |
| `duvall2007ci` | https://www.informit.com/store/continuous-integration-improving-software-quality-and-9780321336385 | Grounds CI as repeatable, risk-reducing build/test automation. |
| `epoch2024swebenchdocker` | https://epoch.ai/blog/swebench-docker | Grounds the Docker-based SWE-bench runtime estimate used in workflow replacement. |
| `wilson1927score` | https://doi.org/10.1080/01621459.1927.10502953 | Grounds Wilson confidence intervals reported for headline rates. |
| `mcnemar1947note` | https://doi.org/10.1007/BF02295996 | Grounds paired binary outcome tests for peer comparisons. |
| `holm1979simple` | https://www.jstor.org/stable/4615733 | Grounds family-wise multiple-comparison correction. |
| `benjamini1995controlling` | https://doi.org/10.1111/j.2517-6161.1995.tb02031.x | Grounds false-discovery-rate correction. |
| `clopper1934use` | https://doi.org/10.1093/biomet/26.4.404 | Grounds exact confidence intervals for paired effect-size tables. |
