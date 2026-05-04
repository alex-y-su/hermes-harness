# Multi-Agent vs. Single-Agent: The Evidence

A critical survey of the published literature on whether multi-agent LLM systems outperform a strong single-agent baseline. Two regimes are distinguished:

- **Simple delegation (orchestrator–worker)** — independent sub-tasks dispatched in parallel, results aggregated. No inter-agent interaction.
- **Complex multi-agent** — debate, role-play, organizational hierarchies, society-of-mind, graph-structured communication on a coupled problem.

## TL;DR

- **Token spending, not architecture, explains most reported wins.** Anthropic's headline (multi-agent research +90.2% over single Opus-4) comes with their own admission that **token usage alone explains ~80% of BrowseComp variance**, with the system using **~15× chat tokens / ~4× single-agent tokens**.
- **Simple delegation works on parallelizable I/O-bound tasks** — research, browsing, retrieval — where shards are independent and errors don't compound.
- **Complex multi-agent (debate, role-play, org charts) is largely unproven.** When compute-matched against CoT + self-consistency on a single agent, the famous gains shrink dramatically or invert.
- **Cemri et al. (NeurIPS 2025)** is the field-defining negative result: across 7 frameworks, "performance gains on popular benchmarks are often minimal."
- **Error amplification** in multi-agent systems is **17.2× independent / 4.4× centralized** (Towards a Science of Scaling Agent Systems, 2025).

## Bucket A — Simple delegation (orchestrator–worker)

| System | Eval | Number | Compute matched? |
|---|---|---|---|
| Anthropic multi-agent research [1] | Internal research eval | +90.2% over single Opus-4 | **No.** ~15× chat tokens, ~4× single-agent. Authors disclose token usage explains ~80% of BrowseComp variance. |
| OpenAI Deep Research [2] | HLE | 26.6% (>2× prior SOTA ~10%) | No public matched-compute comparison; tool stack also differs. |
| | BrowseComp [15] | ~50% solve | GPT-4o 0.6%; +browsing 1.9%. Tools, not architecture, dominate. |
| More Agents Is All You Need [10] | GSM8K, MMLU, HumanEval | Monotonic gains in N | **Yes — and it's sample-and-vote / self-consistency.** Not "multi-agent" in any organizational sense. |
| Reflexion [11] | HumanEval pass@1 | 91% (vs. GPT-4 ~80%) | Iterative single-agent self-reflection. Often misclassified. |

The Anthropic post is unusually candid: *"some domains that require all agents to share the same context or involve many dependencies between agents are not a good fit … citing coding tasks as an example."*

The 90.2% headline is **not** evidence of architectural superiority. It is evidence that ~15× more tokens applied via parallel browsing yields ~90% better answers on a research task that naturally shards.

## Bucket B — Complex multi-agent

| System | Eval | Number | Replication / critique |
|---|---|---|---|
| Multi-Agent Debate [4] (ICML 2024) | GSM8K, biographies | Improvements over CoT | **Beaten by self-consistency at equal tokens** [12] (EMNLP 2024). |
| MetaGPT [5] (ICLR 2024 Oral) | HumanEval / MBPP | 85.9% / 87.7% | vs. GPT-4 ~67%; *no* best-of-N or SC baseline. |
| ChatDev [6] (ACL 2024) | Custom completeness/exec | Wins over GPT-Engineer | Custom metrics; never replicated under matched compute. |
| AgentVerse [7] (ICLR 2024) | Multi-domain | Beats CoT | No equal-compute ablation. |
| GPTSwarm [8] (ICML 2024 Oral) | MMLU, HumanEval, GAIA | Topology-optimized gains | Gains entangled with increased call count. |
| AutoGen [9] (ICLR 2024 LLM-Agents Workshop) | Math, coding, ops research | Qualitative effectiveness | Framework paper; no clean compute-matched comparison. |
| **Why Do Multi-Agent LLM Systems Fail?** [3] (Cemri et al., NeurIPS 2025) | 7 frameworks, 1,600+ traces | 14 failure modes, κ=0.88 | Field-defining negative result. **"Performance gains on popular benchmarks are often minimal."** |

## Bucket C — The compute-matching critique

The core argument: gains disappear when the single agent is given the same compute (best-of-N, longer reasoning, self-consistency).

1. **Single-Agent LLMs Outperform Multi-Agent Systems on Multi-Hop Reasoning Under Equal Thinking Token Budgets** [13]. Tested 5 MAS architectures vs. SAS on FRAMES + 4-hop MuSiQue across Qwen3, DeepSeek, Gemini-2.5. At 1000 thinking tokens on Gemini-2.5-Pro/FRAMES: SAS = 0.68, best MAS (Sequential) = 0.67. Conclusion: *"SAS is the strongest default architecture for multi-hop reasoning"* at matched budgets.

2. **Budget-Aware Evaluation of LLM Reasoning Strategies** [12] (EMNLP 2024). CoT + self-consistency beats multi-agent debate at constant compute.

3. **Why Do Multi-Agent LLM Systems Fail?** [3] (Cemri et al., NeurIPS 2025). 1,600+ annotated traces across 7 MAS frameworks, 14 failure modes, κ=0.88. Headline: gains over single-agent baselines on popular benchmarks "are often minimal."

4. **Towards a Science of Scaling Agent Systems** [16]. Across BrowseComp-Plus, Finance-Agent, PlanCraft, Workbench at matched token budgets: same architecture is **+80.9% on Finance-Agent and −70.0% on PlanCraft**. Independent MAS amplify errors **17.2×** versus single-agent; centralized MAS still amplify **4.4×**. Architecture predicts performance with cross-validated R² = 0.513 — MAS performance is a function of *task shape*, not a uniform improvement.

5. **Cognition's "Don't build multi-agents"** [17]. Two principles: *share full traces, not messages*; *actions carry implicit decisions*. The Flappy-Bird-with-Mario-background example: parallel sub-agents make conflicting implicit choices on shared problems, producing fragility. Mechanistic argument that aligns precisely with Cemri's empirical failure taxonomy.

6. **METR's evaluation methodology** [18]. METR scores agents against a total compute-time budget (e.g., 8-hour total) rather than per-attempt allowances. Their Modular and AIDE scaffolds are compared on equal time, not equal "agents." This is the methodologically correct frame — and it consistently shows scaffold differences shrink under matched compute.

7. **Anthropic's own qualifier** [1]. From their post: token usage alone = **~80% of BrowseComp variance**; *"some domains that require all agents to share the same context or involve many dependencies between agents are not a good fit … citing coding tasks as an example."* A self-imposed bound on the claim.

## When multi-agent decomposition reliably wins (Bucket D)

Triangulating across the surveyed evidence:

| Multi-agent helps | Single agent + more thinking / SC wins |
|---|---|
| Breadth-first browsing, research synthesis | Tight reasoning chains (math, multi-hop) |
| Independent sub-tasks (labeling, bulk transforms) | Code with cross-file dependencies |
| Context that genuinely overflows the window | Anything requiring shared coherent state |
| I/O-bound work where parallelism saves wall-clock | CPU-bound reasoning where compute matches anyway |

The honest framing: **simple delegation for parallelizable, context-busting, I/O-heavy work is supported. Complex multi-agent orchestration for cognitive work is not — and the field is converging on that conclusion in 2024–2026.**

## What an experienced ML engineer should believe

**Believe:**

1. Token spending is the dominant explanatory variable. First question on any "multi-agent X beats single-agent Y by Z%" claim is the token ratio.
2. Orchestrator–worker is legitimate for breadth-first I/O-bound tasks where work naturally shards.
3. Sample-and-vote / self-consistency is a strong baseline most published multi-agent systems do not beat at equal compute.
4. Errors compound multiplicatively across coordinating agents (17.2× independent / 4.4× centralized).

**Don't believe:**

- That MetaGPT / ChatDev / AgentVerse / debate-style scaffolds give a real architectural lift on coding or reasoning at equal compute.
- That "agent debate" reliably improves factuality over self-consistency at equal tokens.
- That Anthropic's 90.2% proves architectural superiority — it proves compute-deployment effectiveness on a parallelizable task.

## Important scope limit

The literature surveyed here measures **task quality**, primarily on benchmarks (HumanEval, MBPP, GSM8K, MMLU, GAIA, BrowseComp, HLE, MuSiQue, FRAMES). It barely measures **autonomy / time horizon** — i.e., how long an agent can run on an open-ended task before stopping prematurely. The "multi-personality extends horizon" effect is real but is **a separate axis** with little compute-matched empirical work. See `05-autonomy-forcing-functions.md`.

## References

1. Anthropic. *How we built our multi-agent research system.* June 2025. https://www.anthropic.com/engineering/built-multi-agent-research-system
2. OpenAI. *Introducing Deep Research.* February 2025. https://openai.com/index/introducing-deep-research/
3. Cemri, M. et al. *Why Do Multi-Agent LLM Systems Fail?* NeurIPS 2025. https://arxiv.org/abs/2503.13657
4. Du, Y. et al. *Improving Factuality and Reasoning in Language Models through Multiagent Debate.* ICML 2024. https://arxiv.org/abs/2305.14325
5. Hong, S. et al. *MetaGPT: Meta Programming for Multi-Agent Collaborative Framework.* ICLR 2024 (Oral). https://arxiv.org/pdf/2308.00352
6. Qian, C. et al. *ChatDev: Communicative Agents for Software Development.* ACL 2024. https://aclanthology.org/2024.acl-long.810/
7. Chen, W. et al. *AgentVerse: Facilitating Multi-Agent Collaboration and Exploring Emergent Behaviors.* ICLR 2024. https://proceedings.iclr.cc/paper_files/paper/2024/file/578e65cdee35d00c708d4c64bce32971-Paper-Conference.pdf
8. Zhuge, M. et al. *GPTSwarm: Language Agents as Optimizable Graphs.* ICML 2024 (Oral). https://arxiv.org/html/2402.16823v3
9. Wu, Q. et al. *AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation.* ICLR 2024 LLM-Agents Workshop. http://ryenwhite.com/papers/WuLLMAgents2024.pdf
10. Li, J. et al. *More Agents Is All You Need.* TMLR 2024. https://arxiv.org/abs/2402.05120
11. Shinn, N. et al. *Reflexion: Language Agents with Verbal Reinforcement Learning.* NeurIPS 2023. https://arxiv.org/abs/2303.11366
12. Wan, Z. et al. *Budget-Aware Evaluation of LLM Reasoning Strategies.* EMNLP 2024. https://aclanthology.org/2024.emnlp-main.1112.pdf
13. *Single-Agent LLMs Outperform Multi-Agent Systems on Multi-Hop Reasoning Under Equal Thinking Token Budgets.* 2026. https://arxiv.org/html/2604.02460v1
14. Shen, Y. et al. *HuggingGPT: Solving AI Tasks with ChatGPT and its Friends in HuggingFace.* NeurIPS 2023. https://arxiv.org/abs/2303.17580
15. OpenAI. *BrowseComp.* 2025. https://openai.com/index/browsecomp/
16. *Towards a Science of Scaling Agent Systems.* 2025. https://arxiv.org/html/2512.08296v1
17. Cognition. *Don't Build Multi-Agents.* 2025. https://cognition.ai/blog/dont-build-multi-agents
18. METR. *Update on Evaluations* (2024); *AI R&D Evaluation Report.* https://metr.org/blog/2024-08-06-update-on-evaluations/ ; https://metr.org/AI_R_D_Evaluation_Report.pdf
19. Zhang, J. et al. *AFlow: Automating Agentic Workflow Generation.* ICLR 2025 (Oral). https://arxiv.org/pdf/2410.10762
