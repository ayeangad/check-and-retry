# PROJECT_PLAN — Independent technical investigation of Hyde × SILVERSIDE "AtelierBench"

Started 2026-10-30. Source under study: https://hyde.ai/blog/atelier (published 2026-10-20).

## 1. Research objectives

1. Understand what AtelierBench measures, how, and what conclusions Hyde draws from it.
2. Find one technically significant, evidence-backed thing that could be done substantially better.
3. Demonstrate the problem independently and build and benchmark a working fix.
4. Report honestly, including negative results.

## 2. Research questions

- RQ1. Are the published results statistically robust? Consider judge choice, attempt-to-attempt variance, best-of-2 selection, and per-task subsets.
- RQ2. Does the judging setup introduce bias? Two of the three LLM judges (gpt-6-astra, claude-opus-5) are also contestants.
- RQ3. Why does a *better* harness make strong models *worse* on delivery format and text/logos (Finding 2)? Hyde's own hypothesis is that the tools check that a workflow runs, not that it meets the brief.
- RQ4 (**flagship; Hyde's own open question**). "What happens when models check their own output and retry?" Does checking against the brief and retrying recover that loss? Does it matter whether the check runs on the rendered output or on the workflow graph? What does each cost?
- RQ5. Which brief claims are objectively machine-checkable, and should they be scored by LLM judges at all?

## 3. Available tools and access

| Resource | Status |
|---|---|
| Hyde article, including the **embedded exhibit data** (`Benchmark data - all scoring methods.xlsx` aggregates: 156 tasks × 8 models × 3 harnesses × 2 attempts × 3 scoring methods × 10 categories) | Public. Extracted to `data/derived/atelier_data.json` |
| Hyde's private task set, per-task scores, workflows, harness code | **Not available.** Never claimed. |
| ComfyUI (open source, GPL-3.0), cloned at commit `b5a4321` | Local, CPU |
| Local LLM: `qwen3.5:4b` (Q4_K_M) via Ollama on a GTX 1650 Ti 4 GB | Free |
| Paid APIs / cloud GPU | **None. $0 budget, by design.** |

## 4. Investigation strategy

1. Extract every technical claim and every number from the article, including the data embedded in its interactive exhibits.
2. Re-analyse Hyde's own published aggregates. Check judge agreement (`avg3`, `low` = min-of-3, `j2`), derive the third judge (`g = 3·avg3 − 2·j2`), attempt-to-attempt stability, Pareto-frontier stability, and whether the prose matches the charts.
3. Generate 10+ hypotheses, score them on the weighted rubric, and validate the top 3.
4. Build the flagship fix as an independent reference implementation over **real ComfyUI node schemas and real ComfyUI validation**. Never present it as Hyde's harness.

## 5. Proposed experiments

- E1 (free, done on public data): judge disagreement per category; self-preference test; prose-vs-chart method audit; Pareto robustness across attempts and methods.
- E2: an independent mini-benchmark of design briefs with objectively checkable claims (output size and aspect, single output, logo pixel-exact, reference image used, seed set). A local LLM authors ComfyUI API-format workflows under three harnesses:
  - **Base**: single shot.
  - **Extended**: ComfyUI's real `validate_prompt` as a tool, equivalent to Hyde's description of "validate its workflow before it runs".
  - **Extended + Brief-Check**: the same, plus a static brief-conformance verifier.
  
  Outcomes are measured on the **actually executed** ComfyUI output (PIL / pixel diff). That measurement is independent of the verifier, to avoid circularity.
- E3: verifier accuracy on a labelled corpus of mutated workflows (precision and recall per check), plus adversarial cases.

## 6. Milestones

| # | Milestone | Deliverable |
|---|---|---|
| M1 | Understand Hyde / Atelier | `research/01-hyde-atelier-overview.md` |
| M2 | Opportunity landscape (≥10 ranked hypotheses) | `research/02-opportunity-landscape.md` |
| M3 | Validate top 3 | `research/03-validation-results.md` |
| M4 | Flagship problem statement | `research/04-flagship-opportunity.md` |
| M5 | PoC + benchmark | `poc/` |
| M6 | Self-audit | `research/05-independent-audit.md` |
| M7 | Report, proposal, walkthrough, outreach | `deliverables/` |

## 7. Known constraints

- No access to Hyde's tasks, per-task data, prompts, harness, or image-model outputs. All conclusions about Hyde's system come from published aggregates. Anything else is labelled INFERRED.
- A 4B local model is far weaker than the contestants. Its absolute numbers do not transfer. The experiment tests a *mechanism* (does brief-aware validation fix spec drift?), not a leaderboard.
- No GPU image generation at 1920×1080. Diffusion nodes are executed by shape-faithful stubs. Every image-only node (load, scale, crop, composite, save) runs in real ComfyUI code. Text rendered *by* a diffusion model therefore cannot be evaluated.
