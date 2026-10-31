# Research log

Entries are in chronological order. Certainty labels: VERIFIED / STRONGLY SUPPORTED / INFERRED / UNVERIFIED.

## 2026-10-30

### Environment
- The working dir was empty. Tools available: Python 3.12, uv, node, gh, docker, Ollama with `qwen3.5:4b` (Q4_K_M, tools+vision).
- Hardware: GTX 1650 Ti 4 GB, 7.7 GB RAM, 8 cores. No API keys. Budget: $0, no paid APIs.
- Ollama throughput, measured: 7.5 tok/s generation at num_ctx 8192. The model was split 54/46 CPU/GPU while a pip install was running. This sets the size of the E2 experiment.

### Sources inspected
- `https://hyde.ai/blog/atelier`. A plain page fetch truncated it, so I fetched the raw HTML with curl (saved in `data/raw/`). The 7 exhibit iframes embed the benchmark aggregates as JSON (`const D`, `SCORESETS`, `GDSETS`), source-labelled "Benchmark data - all scoring methods.xlsx". Extracted with `analysis/extract_exhibit_data.py`. **VERIFIED** (data is on the public page).
- Scoring methods in the page code: `avg3` = mean of gpt-6-astra, claude-opus-5, gemini-3.1-pro per claim (chart default); `low` = min of 3; `j2` = mean of opus + astra.
- Hyde blog (RSS: 12 posts), careers (Ashby), team bylines, SILVERSIDE, comfy-cli, ComfyUI `validate_prompt`, related papers. The arXiv IDs of the key papers were checked against the arXiv API (2409.01392, 2601.04060, 2607.01709, 2610.37673 all exist).
- No public Hyde GitHub org or AtelierBench code found (UNVERIFIED negative).

### Hypotheses generated
See `02-opportunity-landscape.md` (H1–H12).

### Experiments
- E1a: does the prose match the charts? The Finding 2 like-for-like prose matches the `j2` method 5/5 and the chart default `avg3` 0/5. **VERIFIED.**
- E1b: judge disagreement. `avg3 − min-of-3` is 0.41–0.74 for nine categories and **0.010 for Delivery Format Specs**. **VERIFIED** from aggregates. Interpretation: delivery is scored (near-)deterministically. **INFERRED.**
- E1c: self-preference of contestant-judges. Residual of (j2 − g) after a quality fit: opus −0.012, astra +0.009, residual SD 0.058. **No evidence of self-preference; H discarded.** (Aggregate-level test, low power for small effects.)
- E1d: run-to-run per-task σ ≈ 0.33 from two independent estimators (0.33 and 0.32). Paired SE for a like-for-like harness difference ≈ 0.03 (n≈150). Fable's drop (−0.36, z≈−11) and Opus's Ext drop (−0.17, z≈−5) are real; Astra's "no change" is genuinely no change.
- E1e: delivery regression. Base→Ext delivery Δ: Fable −1.07, Kimi −0.96, Opus −0.44, Astra −0.21. Delivery becomes the 2nd-worst category of 10 on Ext for Fable, Kimi and Gemini-flash.
- E1f: Pareto "best value" set. Under per-attempt data, gemini-flash·ext enters (attempt 1) and Opus leaves (j2, attempt 2). The article's "only DeepSeek, Sol, Opus and Astra are ever the best value" is not stable at one-rerun noise. **VERIFIED** from aggregates.

### Decisions
- D1: Do not use any paid API as the experiment model ($0 budget). Use local Ollama.
- D2: Flagship candidate: **brief-contract verification in the harness loop**, i.e. compile the brief's objectively checkable claims into pre-execution graph checks. Motivation: E1b + E1e + Hyde's own hypothesis ("the harness's tools check that a workflow runs, not that the output matches the brief") + Hyde's stated future work ("What happens when models check their own output and retry?").
- D3: To avoid circularity, the E2 outcome metric is measured on **executed ComfyUI output** (PIL size, pixel diff of logo region), never with the verifier's own code.

### Rejected approaches
- The self-preference audit as the flagship (E1c showed no effect).
- A VLM-judge-in-the-loop (COMFYCLAW already does it; it needs image generation that we cannot run at 1080p on 4 GB).
- Type-level compatibility checking (ComfyTy, arXiv 2610.37673, already covers it).

### Reframing (2026-10-30)
- D4: The flagship is reframed to **answer one of Hyde's own open questions** from the post: *"What happens when models check their own output and retry?"*. Scope: the objectively checkable part of a brief (delivery size, deliverable count, exact logo and position, reference composition). VLM self-critique of style, text glyphs and aesthetics is out of scope (content is stubbed).
- D5: The harness was redesigned so checking happens at **submit** (submit → check → retry). The 4B pilot showed the model never calls an optional validate tool (0 validate calls in 12 tool-arm episodes), so feedback in validate_workflow never reached it. Arms:
  - `extended`: executability check only (Hyde-like baseline).
  - `output_retry`: execute, inspect the delivered image, retry. This is the literal "check output and retry".
  - `contract`: static check of the graph before execution, retry.
  - All three share prompt, tools, seed and budget (15 tool calls). Brief-check rejections are capped at 3.
- D6: The `restate` ablation was dropped for compute (about 2.5 min per 4B episode). Hyde's hypothesis 2 ("lose track") is therefore not separately tested. Noted as a limitation.
- D7: qwen3.5:2b was rejected after a pilot. It produced no valid workflow even on the simplest brief and was no faster: it also spills to CPU at 8k context on the 4 GB GPU. qwen3.5:4b is used.
- Known confound: `output_retry` feedback says *what* is wrong with the image; `contract` feedback says *where* in the graph and how to fix it. The comparison is "the best feedback each check can naturally give", not timing alone.
- Known circularity: `output_retry` uses the same deterministic checks as the final evaluator. For objective claims that is inherent (checking the output IS the ground truth). The `contract` checker is an independent implementation from the evaluator.
- D8 (pilot v4, kept in `poc/results/pilots/`): with the original tooling, 4 of 6 briefs never reached a ComfyUI-valid submission. The 4B model burned 10–15 calls in `search_nodes`, whose naive scoring returned noise for multi-word queries and ignored ComfyUI's `search_aliases`, so it never found `ImageCompositeMasked`. Without a valid submission the arms cannot diverge, so the run could not test the question. Two fixes, **identical for every arm including base**:
  1. Rewrote `search_nodes` (stopwords, CamelCase splitting, name/alias weighting, skipping deprecated/dev/API nodes).
  2. Added a 12-entry core-node reference to the system prompt.
  This moves the 4B model toward the regime Hyde's frontier models are in (>90% executable), where the brief check is what matters. It is a documented departure from "Hyde-faithful Extended".
- D9 (2026-10-30 night): **one narrative instead of two.** The deliverables are built around answering Hyde's open question. The public-data audit shrinks to the single finding that motivates it (clean delivery-format regression + brief-blind validator). The judge-method mismatch, Pareto instability, best-of-2 artifact and self-preference null move to an appendix. Rationale: two pieces split attention, the audit has a low ceiling without per-task data, and the prose-vs-chart point reads as a gotcha.
- D10 (2026-10-30 night, $2 DeepSeek budget): **main E2 moved to DeepSeek V4.1 Flash** (`deepseek-flash`, served by DeepSeek-V4.1-Flash-1017, i.e. AtelierBench's own `deepseek-v4.1-flash` contestant). Non-thinking mode: cheaper, matches the local run, and Hyde's setting is unknown. New long-brief set: 73 briefs, Exhibit-1-style (median 141 words), including Hyde's Exhibit 1 brief verbatim with synthetic stand-ins, sizes from published platform formats. Oracle check: 73/73 briefs achievable. The pilot cost $0.027 for 5 briefs × 4 arms.
- D11: ship-rule fix for all arms. When the budget runs out, ship the last ComfyUI-valid submission instead of the last attempt. The pilot showed output_retry shipping a graph its final retry had broken, which penalizes retrying for reasons a production loop wouldn't have.
- D12: added E4 (best-of-n selection by contract) to connect the checker to Hyde's post-training direction (verifiable signal for filtering/reward). It runs after the main run under the same cap.
- Verifier: added a TextOverlay transfer function (size unchanged; logo claims abstain because overlap isn't modelled).

## 2026-10-31 (ownership phase)
- Main E2 (DeepSeek, 876) and E4 (73) finished; ledger $1.10 at peak prices.
- Kill criterion locked before any result was computed. New script `poc/experiments/primary_test.py` (cluster bootstrap over briefs + exact McNemar).
- E2 result: contract 93% vs extended 53% (+39.7 pp, HELPS); output_retry 62% (+8.7 pp, HELPS on the line).
- Transcript inspection: 83/87 contract wins involve logo_position; the agent is never told the logo's pixel size; the contract's feedback gives it and the exact x,y. Feedback-richness confound is the main driver.
- D13 (experiment D): new arm `output_retry_rich` (equal-information output check) and `--state-logo-size` (informed briefs). D-B blind, 3 seeds: rich 88% = contract 88%, CI [−5.4, +5.4]; contract half the generations. D-A informed: extended 89%, contract − extended not shown (p = 0.12).
- Headline claim narrowed to what experiment D supports; D-A in limitations; E2's +40 pp not presented as the effect of checking.
- Local qwen3.5:4b seeds 0–1 finished (192): contract − extended +29.2 pp (HELPS); construction is the bottleneck.
- Ledger cap raised to $2.50; final ledger $1.88 (peak prices).
