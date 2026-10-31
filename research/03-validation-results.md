# 03 — Validation of the top hypotheses

All numbers come from reproducible scripts:
- `analysis/reanalyse_public_data.py` produces `data/derived/reanalysis.md`, built from the aggregates Hyde embedded in the article.
- `poc/experiments/*` produce `poc/results/*`.

Labels: VERIFIED / STRONGLY SUPPORTED / INFERRED / UNVERIFIED.

---

## H2 — Measurement stability of AtelierBench's reported results

**Hypothesis.** The reported quality numbers depend on scoring choices (judge aggregation, best-of-2) by amounts comparable to the differences the article draws conclusions from, and this is not visible to readers.

**What would disprove it.** Small judge spread, prose and charts using the same method, and conclusions robust to the method.

**Results.**

| Test | Result | Label |
|---|---|---|
| Which method do the Finding 2 prose numbers use? | `j2` (opus+astra only) matches 5/5 rounded values. `avg3`, the chart default, matches 0/5. Example: the prose says "Astra stays at 4.1"; the `avg3` chart shows 4.21 → 4.23. | VERIFIED |
| Per-claim judge spread (avg3 − min-of-3) | 0.41–0.74 on 9/10 categories. **0.010 on Delivery Format.** | VERIFIED (aggregates) |
| Non-contestant judge offset (gemini − mean(opus, astra)) | +0.37 on Text & Logo and on Matches Reference: the categories Hyde calls most important. ≈0 on Delivery. | VERIFIED (derived algebraically) |
| Method effect on level | `avg3` → `low` lowers every model by ~0.5–0.6. `avg3` → `j2` lowers by ~0.1. The 4.5 bar was "calibrated with designers on a sample". Which method it was calibrated under is not stated. | VERIFIED / UNVERIFIED (calibration) |
| Run-to-run noise | Per-task σ ≈ 0.33, from two independent estimators (0.33 and 0.32). | INFERRED (estimator assumptions stated in script) |
| Do the headline harness effects survive noise? | Yes. Fable Base→Ext Δ = −0.36 (z ≈ −11). Opus Base→Ext −0.17 (z ≈ −5). DeepSeek, Sol and Gemini-flash gains have z > 6. Astra's "no change" is a genuine null (z ≈ ±0.5). **The article's qualitative conclusions hold.** | STRONGLY SUPPORTED |
| Best-of-2 artifact (H6) | Max-of-2 adds ~0.17 to strong models' like-for-like scores. Because weak models succeed twice less often on Base, the artifact inflates their Base→ExtPlus gain by an estimated 0.06–0.12. That is small relative to DeepSeek (+0.97) and Sol (+0.52), but **larger than Kimi's entire reported +0.056**. | INFERRED (independence assumption) |

**Verdict: partially survives.** The reporting is internally inconsistent: prose and charts use different judge configurations, and the prose uses the configuration made up only of contestant models. Judge spread is large on subjective categories. But the main conclusions are robust to the method and to run noise. This is a reporting and reproducibility finding, not "the benchmark is wrong". Since it involves no engineering fix beyond "report CIs and pick one method", it is a secondary contribution.

## H3 — Self-preference of contestant judges (tested because it was cheap)

**Method.** The derived third judge is g = 3·avg3 − 2·j2. I fit (j2 − g) against quality on the 6 non-judge contestants (32 cells, R² driven by a slope of −0.24: stricter judges spread scores more). I then test whether astra's and opus's own outputs sit above the fit.

**Result.** Mean residuals: opus −0.012, astra +0.009. Residual SD is 0.058. **No evidence of self-preference. Discarded.** Caveat: this is an aggregate-level test that cannot detect an effect much smaller than ~0.05, and image outputs come from image models, not from the judge LLM itself, so a strong effect wasn't expected.

## H5 — Stability of the "best value" (Pareto) set

**Result.** Using each attempt separately instead of the pooled average:
- Attempt 1 adds gemini-3.8-flash·Extended to the quality / all-in-cost frontier (all three scoring methods).
- Attempt 2 under `j2` removes Opus.

The article's claim "only DeepSeek, Sol, Opus and Astra are ever the best value … and Fable never is" holds for the pooled data. One rerun changes it. "Fable never" is robust in every configuration. **Verdict: survives as a caution.** The membership claim is at the edge of the noise. That matters because model selection is the decision Hyde's private evals are sold to support, but it's a reporting recommendation (bootstrap frontier-membership probabilities), not a system flaw.

---

## H1 — Brief-blind validation and delivery drift (flagship candidate)

**Exact hypothesis.** (a) ComfyUI-style validation accepts workflows that violate objectively checkable brief requirements. (b) A deterministic brief-contract check, returned through the same validate tool, lets an agent fix those violations, raising the rate at which delivered outputs meet the brief, at negligible cost. (c) The effect comes from *checking*, not merely from information the check happens to carry. (The planned `restate` arm was dropped, D6; question (c) was instead tested by experiment D, which equalises information.)

**Supporting evidence from Hyde's data (VERIFIED from aggregates).** Delivery Format drops Base→Ext for Fable (−1.07), Kimi (−0.96) and Opus (−0.44), and is the 2nd-worst of 10 categories on Ext for 3 of 8 models. Judges agree on delivery to within 0.01, so this is a measurement-clean effect.

**Alternative explanations.**
- (i) The Extended harness's prompt or loop changes model behavior in general. Fable drops in *every* category, not just delivery, so delivery is only part of the story.
- (ii) Image models in the catalog can't natively produce the size, and Extended agents pick different models.
- (iii) "Lose track" in long context (Hyde's hypothesis 2).
- (iv) Hyde may score delivery deterministically and other categories by judges, which would make delivery look different for measurement reasons. The spread analysis shows its *measurement* is clean, but its *weight* in the total is unknown.

**What would disprove it.** (a) ComfyUI validation rejects brief-violating graphs. (b) Contract feedback doesn't raise brief conformance over plain validation, or an equally informative output check / simply stating the missing information does just as well.

### E3 — Is validation brief-blind, and is the verifier accurate? (VERIFIED, independent reproduction)

Corpus: 24 briefs × (correct reference workflow + 12 realistic mutations where applicable) = **214 workflows**, all executed in real ComfyUI. Ground truth comes from `evaluator.py`, which reads only the output PNGs.

- **142 of 142** workflows that violate ≥1 brief claim were **accepted** by ComfyUI's validator. **(a) confirmed.**
- Verifier vs real outcome, per claim:

| claim | TP | FN | FP | TN | abstain |
|---|---|---|---|---|---|
| delivery_size | 66 | 0 | 0 | 148 | 0 |
| logo_exact | 54 | 0 | 0 | 78 | 0 |
| logo_position | 68 | 0 | 0 | 64 | 0 |
| reference_composition | 24 | 0 | 0 | 78 | 6 |
| single_output | 36 | 0 | 0 | 178 | 0 |

Median verifier latency is 0.28 ms. **Caveat:** I wrote the mutations knowing the verifier's design, so this is an in-distribution upper bound. The out-of-distribution test is the verifier's post-hoc accuracy on LLM-written workflows in E2 (below).

Development notes, kept for honesty: three bugs were found and fixed during E3.
1. The evaluator checked only the first output. Fixed so every delivered image must pass.
2. The evaluator's reference measure used a 32×32 luma grid and failed correct workflows on hue-only references. Switched to a per-channel-centred 16×16 RGB grid with threshold 0.3, chosen from oracle correct-vs-broken workflows **before any arm comparison was run**.
3. Abstentions raised inside the verifier's transfer functions were never copied into the report. Fixed, with a regression test.

### E2 — Does a brief check in the loop help an agent? (DeepSeek V4.1 Flash, main run)

Setup: `deepseek-flash` (= DeepSeek-V4.1-Flash-1017, AtelierBench's `deepseek-v4.1-flash`), non-thinking, 73 long Exhibit-style briefs (incl. Hyde's Exhibit 1 brief verbatim with synthetic stand-ins), 3 seeds, 4 arms, 15-tool-call budget, tool arms forked from one shared prefix at the first ComfyUI-valid submission. Outcome = all objective claims pass on the PNG ComfyUI actually wrote (`evaluator.py`). Kill criterion locked before any result was computed: helps = gain ≥ 5 pp AND 95% CI > 0 (cluster bootstrap over briefs).

| arm | all-pass (n = 219) | 95% CI | image generations per conforming output |
|---|---|---|---|
| base | 49% | 42–55 | 2.04 |
| extended (executability check only) | 53% | 46–59 | 1.84 |
| output_retry (execute, inspect PNG, retry) | 62% | 55–68 | 2.43 |
| contract (static check of the graph, retry) | 93% | 88–95 | 1.05 |

- contract − extended **+39.7 pp** [+30.6, +49.3], 87 vs 0 discordant → HELPS. output_retry − extended **+8.7 pp** [+5.0, +12.8] → HELPS (on the line). VERIFIED.
- 85 of contract's 87 wins are logo briefs; 83 involve `logo_position`. The /8 size trap is a minor part (16). VERIFIED.
- extended vs base: not distinguishable (21 vs 12, p = 0.16). On logo briefs extended = base (t2i_logo 7 vs 8, edit_ref_logo 3 vs 4). VERIFIED — brief-blind validation does not fix brief violations.
- "0 extended wins" is largely by construction (shared prefix, 0 false alarms, ship-last-valid rule); the evidence is the 87 wins, not the zero.

### Experiment D — is it the checking, or the information? (D13)

Inspection of E2 transcripts showed the agent is never told the logo's pixel size (no brief states it, no tool reports it), so it cannot compute a corner position; the contract's feedback states it and gives the exact fix ("x=1348, y=32"), output_retry's only says "not in the top-right corner". E2's contract-vs-output_retry comparison therefore compared feedback content, not timing.

**D-B, blind, equal information** (37 logo briefs × 3 seeds, n = 111): new arm `output_retry_rich` = output_retry + the same logo size and target x,y (same formula as the contract).

| arm | all-pass | generations / episode | generations per conforming output |
|---|---|---|---|
| extended | 9% (5–16) | 0.93 | — |
| output_retry | 27% (20–36) | 1.95 | — |
| output_retry_rich | 88% (81–93) | 1.95 | 2.20 |
| contract | 88% (81–93) | 0.94 | 1.06 |

contract − rich **+0.0 pp [−5.4, +5.4]**, 4 vs 4 discordant, stable across seeds. **With equal information, checking the plan and checking the output reach the same pass rate (within ±5 pp); the plan check uses half the image generations** (104 vs 216 for the same 98 passes). VERIFIED.

**D-A, informed** (logo pixel size appended to every brief; 37 logo briefs, 1 seed): base 78%, extended **89%**, output_retry 97%, contract 100%. contract − extended 4 vs 0, McNemar p = 0.12 → not shown. **Most of what the check fixed on logo briefs was information our harness withheld.** VERIFIED (cross-run comparison: blind extended 9–11% vs informed 89%).

### E4 — the contract as a selector (best-of-4 single shot, 73 briefs)

random pick 51%, contract pick 67% (56–77), oracle 67%. The contract equals the oracle on every brief; per sample 0 good samples rejected and 1 bad accepted out of 290. On logo briefs the oracle is 32–39%: failures are systematic, so sampling cannot fix them; feedback can. VERIFIED.

### Verifier validity out of distribution (post hoc, LLM-written workflows)

DeepSeek E2: 469 caught, 32 missed (25 logo_position), **0 false alarms**, 79/3,011 abstentions (2.6%). qwen: 102 caught, 1 missed, 2 false alarms (reference_composition), 6 abstentions. VERIFIED.

### Replication on a weak local model (qwen3.5:4b, 24 short briefs × 2 seeds, n = 48)

base 8%, extended 12%, output_retry 29%, contract 42%. contract − extended +29.2 pp [+16.7, +41.7] → HELPS; output_retry − extended +16.7 pp [+4.2, +29.2] → HELPS; contract vs output_retry 7 vs 1, p = 0.07 → not shown. Only 20–27 of 48 episodes per arm produced a runnable workflow: for a 4B model, construction is the main failure. The D-A information caveat applies (untested on qwen). VERIFIED.

### Verdict on H1
(a) confirmed. (b) confirmed with a correction: a brief check with an *actionable* fix lifts conformance sharply, but much of that lift on logo briefs is information the harness should have supplied. (c) the timing of the check (plan vs output) does not change the pass rate at equal information; it halves image generations.
