# 01 — Hyde and AtelierBench: what is actually known

Labels: **[DOC]** stated in the article/its embedded data · **[OBS]** observed in the public page code/data · **[INF]** my inference · **[UNK]** unknown.

## 1. Hyde in one paragraph

Hyde (hyde.ai, ~30 people across NYC, London and Mumbai, backed by Bain Capital Ventures and General Catalyst) sells "sovereign AI". Forward-deployed "AI Builders" build private evaluations from a customer's tasks, then post-train and deploy specialist models on the customer's infrastructure [DOC: site, blog, careers]. The platform pieces are:
- **Campfire**: train, evaluate, deploy. Scores every checkpoint against public and custom benchmarks.
- **Refinery**: trace mining.
- Auto model routing.

Every customer engagement starts with the same pattern: define tasks, build rubrics and judges, pick the cheapest model and harness that clears the bar, and specialise if volume justifies it. This shows up in the BCG interview, "Return on Token", the US-stock-exchange post (SME-graded trajectories), the browser-agent posts (three LLM judges, judges proposed as RL reward models), and the AtelierBench conclusion ("private evaluations… help them to choose the right model and harness for each task"). **AtelierBench is a showcase of the eval-design half of Hyde's product.** Its methodology is the product.

## 2. What AtelierBench is

| Question | Answer | Label |
|---|---|---|
| What | A benchmark of "professional design": can an LLM build a ComfyUI workflow that executes (Workflow Execution), and does the image meet the brief (Quality)? | DOC |
| Partner | SILVERSIDE (AI creative lab; Coca-Cola, SVEDKA Super Bowl spot built on ComfyUI) | DOC |
| Tasks | 156 private tasks from real client briefs (social, POS, OOH). Exhibit 1 is illustrative and not in the set. | DOC + OBS (`nTasks: 156`) |
| Inputs | Brief text, input images (reference photos, logos), and a catalog of available image-generation models | DOC |
| Output | A ComfyUI workflow. When executed, it produces the image. | DOC |
| Contestants | 8 LLMs in 3 tiers: premium (gpt-6-astra, fable-5.1), standard (claude-opus-5, gpt-5.6-sol, gemini-3.8-flash), open weights (kimi-k3, qwen3.8-max, deepseek-v4.1-flash) | DOC |
| Harnesses | **Base**: one shot, brief + model catalog, no tools. **Extended**: ComfyUI CLI tools to look up steps and validate before running, 15 tool calls (16 model runs). **Extended Plus**: 30 tool calls (31 model runs). | DOC + OBS (harness labels in data) |
| Repetitions | Every task twice per harness | DOC + OBS |
| Scoring | Brief → claims (Exhibit 1 has 19 claims, weighted 1–3, 10 categories). Each claim is scored 0–5; task score = weighted mean. LLM judges + human designers. | DOC |
| Judges | gpt-6-astra, claude-opus-5, gemini-3.1-pro. Methods: `avg3` (default), `low` (min), `j2` (opus+astra). | OBS (page JS `SCORING_METHODS`) |
| Pro bar | 4.5, calibrated with designers on a sample: the point where the verdict flips from "redo" to "ship" | DOC |
| Cost | Generation (LLM tokens) + workflow execution (image-model inference), USD. All-in cost per success = total spend ÷ successes. | DOC |
| How humans and LLM scores combine | — | UNK |
| Per-task scores, variance, CIs | Not reported | UNK |

### Headline findings (paraphrased) [DOC]
- **F1**: Only Astra, Fable and Opus execute >90% of tasks on Base. Tools lift the weaker five from 3–41% to 59–82%. Doubling the tool budget adds ≤6pp.
- **F2**: Nothing reaches 4.5. A better harness helps only some weaker models, and it makes Fable and Opus *worse*, especially on Delivery Format and Text & Logos. Hyde's hypotheses: (1) "the harness's tools check that a workflow runs, not that the output matches the brief, so a model can fix the workflow at the expense of the brief"; (2) "a longer loop gives more chances to lose track of exact requirements such as size and wording."
- **F3**: Failures cost money. Harnesses raise cost 2.2× (Ext) and 3× (Ext Plus). Cheap models become best value with tools. Only DeepSeek, Sol, Opus and Astra are ever Pareto-best.
- **Future questions Hyde lists**: self-checking and retry, designer-in-the-loop, other media, and brand-specific taste. They also propose judge models trained on ship/redo decisions and fine-tuning small models on proven workflows.

## 3. Architecture (reconstructed)

```
                    ┌──────────────────────── TASK (private, 156) ───────────────────────┐
                    │ brief text [DOC] · input images [DOC] · model catalog [DOC]        │
                    │ claims list w/ category + weight 1–3, designer-verified [DOC]       │
                    └───────────────┬──────────────────────────────────┬─────────────────┘
                                    │ brief + inputs + catalog         │ claims (hidden from model) [INF]
                                    ▼                                  │
 ┌──────────── HARNESS [DOC] ───────────────────────────┐             │
 │ Base: 1 LLM call → workflow JSON                      │             │
 │ Extended/Plus: agent loop, ≤15/30 tool calls          │             │
 │   tools: "ComfyUI command-line tools to look up steps │             │
 │   and validate" [DOC] — likely comfy-cli `nodes       │             │
 │   search/show`, `workflow validate` [INF]             │             │
 │   validate = schema/type/enum/wiring only [INF from   │             │
 │   comfy-cli + ComfyUI validate_prompt source]         │             │
 └──────────────┬────────────────────────────────────────┘             │
                │ workflow (API JSON) [INF format]                     │
                ▼                                                      │
 ┌──────── EXECUTION: ComfyUI [DOC] ─────────┐                         │
 │ image models from catalog (incl. paid     │ ── fail → "no image":   │
 │ APIs? execution_cost is billed [DOC])     │    node not installed,  │
 │                                           │    missing field (seed),│
 │                                           │    incompatible schema  │
 └──────────────┬────────────────────────────┘    [DOC, Exhibit 2]      │
                │ image                                                 │
                ▼                                                       ▼
 ┌──────── SCORING ────────────────────────────────────────────────────────────────┐
 │ per claim 0–5 × 3 LLM judges [OBS] (+ human designers [DOC], combination [UNK])  │
 │ Delivery-format claims: judges agree to within 0.01 → likely deterministic [INF] │
 │ task score = weighted mean [DOC]; aggregates: execution rate, quality on         │
 │ successful tasks, like-for-like (best of 2 on tasks run in all harnesses) [DOC]  │
 └──────────────────────────────────────────────────────────────────────────────────┘
```

**Failure points visible from evidence:**
1. Construction errors: missing fields, uninstalled nodes, schema mismatches [DOC].
2. **Brief drift that executes fine**: the workflow runs but violates spec (size, text, logo) [DOC hypothesis + OBS category data].
3. Judge disagreement on subjective categories [OBS].
4. Selection effects in "quality on successful tasks" [DOC acknowledged].

## 4. Assumptions the design makes (and whether they hold)
- *Validated = good enough to run.* That's true for executability, but the validator is brief-blind [INF, strongly supported by ComfyUI source and Hyde's own F2 hypothesis].
- *3-judge average is a stable quality measure.* Per-claim judge spread is large (avg − min ≈ 0.4–0.74 on 9/10 categories) [OBS]. The method choice moves every score by ~0.1 (j2) to ~0.55 (low). The prose reports j2 while the charts default to avg3 [OBS].
- *Two attempts are enough to characterise a model × harness.* For harness *differences*, yes: the paired SE is ~0.03 [INF]. For Pareto "best value" membership, no [OBS].

## 5. What Hyde appears to consider its edge
Private, brand-specific evaluation, with judges eventually trained on ship/redo decisions, plus cheap specialist models fine-tuned on proven workflows, kept on the customer's infrastructure. Atelier is the evidence that off-the-shelf model + harness isn't enough, and the eval layer is where Hyde sits.
