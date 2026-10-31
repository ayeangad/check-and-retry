# 05 — Independent audit of my own work

Written as a skeptical reviewer. Each item says what I checked, what I found, and what changed.

## A. Does the solution address the root cause?

**Claim under audit:** brief drift happens because the in-loop check is brief-blind, and a brief-aware check fixes it.

- The *existence* of brief-blindness is verified, not argued. In E3, 142/142 brief-violating workflows pass ComfyUI's `validate_prompt`. The validator's error vocabulary (`missing_node_type`, `return_type_mismatch`, `value_not_in_list`, …) has no concept of output size, provenance or position.
- Whether *Hyde's* regression is caused by this is **not proven**. Fable drops in all 10 categories on Extended, not only delivery. So brief-blindness explains at most part of Finding 2. The rest might be loop length, tool-induced behavior change, or different image-model choices. I can't separate these without Hyde's traces. The proposal is worded accordingly.

## B. Is the evaluation fair?

| Risk | Check | Status |
|---|---|---|
| Verifier grades its own arm (circularity) | The outcome comes from `evaluator.py`, which reads only output PNGs (FFT template match, PIL size, layout correlation) and shares no code with `brief_contract.py`. | Mitigated |
| `output_retry` uses the evaluator's checks as feedback | Inherent for objective claims: inspecting the output *is* the ground truth. This favors `output_retry` if anything, which makes it a strong baseline for `contract` to be compared against. | Disclosed |
| Arms differ in more than the check | All tool arms share prompt, tools, seed and budget, and are forked from a literally shared prefix at the first ComfyUI-valid submission (`run_branched`, unit-tested). | Mitigated |
| Feedback richness confound | `contract` feedback names the node and gives a fix; `output_retry` can only say what's wrong with the image. The comparison is "best natural feedback of each check", not timing alone. | Disclosed, not ablated |
| Tasks favour the verifier | 14/24 briefs use non-multiple-of-8 sizes (real ad sizes: 1080×1350, 1200×628, 970×250). Results are reported split by size%8 and by family. | Disclosed, split reported |
| Mutation corpus written by the verifier's author | E3 is an in-distribution upper bound. Out-of-distribution validity is measured post hoc on every LLM-written workflow in E2. | Partially mitigated |
| Evaluator threshold tuned | The reference-composition threshold (0.3, 16×16 centred RGB) was set from oracle correct/broken workflows *before* any arm comparison. | Disclosed |
| Weak model | Main run moved to DeepSeek V4.1 Flash (an AtelierBench contestant); qwen3.5:4b is a replication. No frontier model tested. | Limitation |

## C. Adversarial tests of the verifier (`poc/tests/test_adversarial.py`)

| Attack | Result |
|---|---|
| Letterbox: paste generation onto an exact-size EmptyImage, then the logo | Correctly passes |
| `denoise` fed by a linked primitive node | Abstains (does not guess) |
| Unmodelled geometry node (ImageFlip) before SaveImage | Abstains on dependent claims |
| String-typed numbers | Tolerated |
| Garbage / dangling / empty graphs | No crash |
| **500-node deep chain** | **Found a crash (RecursionError). Fixed** with iterative topological pre-evaluation; a backstop turns deep recursion into an abstention. |
| Pixel-identical logo under another filename | **Known false alarm** ("logo never loaded"). The contract binds to the supplied file. Documented. |
| A later composite painted over the logo | **Known false negative**: occlusion by later sources isn't tracked. Documented. |

Bugs found during development and fixed (all have regression tests):
1. Abstentions raised inside transfer functions were never copied into the report.
2. Logo/reference checks only looked at the first SaveImage.
3. The `resize_source` reference case first overclaimed "destroyed". It now abstains unless the source is pasted at (0,0).

## D. Does it scale and is it maintainable?

- **Latency.** Median 0.28 ms per check on 6–15-node graphs; 500-node chain under 0.5 s. That is negligible next to one LLM turn (tens of seconds locally) or one image generation.
- **Coverage is the real cost.** About 20 core node types have transfer functions. Every new node family a team uses (Flux/Qwen-Image loaders, ControlNet, IP-Adapter, custom compositors) needs a transfer function or the verifier abstains. Abstaining is safe but reduces value. A practical path: transfer functions for the ~50 most-used nodes in a team's own workflow library, plus *execution-based fallback*: run cheap image-space subgraphs for real and measure.
- **The contract source.** The PoC reads a structured spec. In Hyde's setting the claims list already exists (designer-verified, category-tagged), so Delivery Format and Matches-Reference claims map directly. Free-text extraction was not evaluated.

## E. Could something simpler do the same?

- *"Just append the brief to the validator output"* (restate). Dropped for compute (D6), untested.
- *"Just give the model the missing facts"*. Tested in D-A: stating the logo's pixel size lifts unchecked `extended` from ~10% to 89% on logo briefs. **This is the simplest competitor, and it does most of the work.** The check's remaining value is catching what the model still gets wrong, and doing so without paying for a generation.
- *"Just check the output and retry"* is the `output_retry` arm, measured directly. Its costs: one paid generation per check, and feedback that can't localize the cause.
- *"Hard-code a final ImageScale"* fixes delivery size only, and breaks logo exactness if placed after compositing. That ordering trap is exactly what E3's `resize_after_logo` mutation exhibits.

## F. E2-specific audit

| Risk | Finding | Status |
|---|---|---|
| Feedback-richness confound (contract gives a fix, output_retry only a symptom) | **Real and large.** 83/87 contract wins involved logo_position; the contract's feedback revealed the logo's size and exact x,y. Experiment D: with equal information, output check = plan check (88% vs 88%, CI ±5.4). | Tested (D-B); headline narrowed |
| Information leak: agent never told input image sizes | Stating the logo size alone → extended 89% on logo briefs (D-A). | Tested; in limitations |
| "0 extended wins" looks too clean | By construction: shared prefix, 0 verifier false alarms, ship-last-valid. Evidence is the 87 wins, not the zero. | Disclosed |
| Multiple comparisons / post-hoc stories | Kill criterion locked before results; one primary comparison; everything else labelled exploratory. D was designed after seeing E2, run without predictions. | Mitigated / disclosed |
| Seeds within a brief are correlated | CIs by cluster bootstrap over briefs; naive CIs reported alongside. | Mitigated |
| Verifier out-of-distribution | DeepSeek: 0 false alarms, 32 misses (25 logo_position), 2.6% abstain. qwen: 2 false alarms. | Measured |
| Our `extended` ≠ Hyde's Extended | Node reference in prompt, tuned search, forced validation. | Disclosed; no absolute comparisons |

