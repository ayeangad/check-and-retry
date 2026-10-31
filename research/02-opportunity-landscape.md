# 02 — Opportunity landscape

These are hypotheses, not findings. Evidence codes refer to `data/derived/reanalysis.md` (sections A–G), produced by `analysis/reanalyse_public_data.py` from the data embedded in Hyde's article.

Scoring: Technical significance 25% · Real-world impact 25% · Evidence strength 20% · Independent validability 15% · Feasibility of a meaningful improvement 15%. Each is scored 1–10.

## Hypotheses

| # | Opportunity | Evidence | Why it matters | Investigation method | Difficulty | Confidence (before testing) |
|---|---|---|---|---|---|---|
| H1 | **Validation is brief-blind.** In the Extended harness the validator checks only executability, so agents "fix the workflow at the expense of the brief". A brief-contract check in the loop would recover the spec. | Hyde's own hypothesis (F2). Delivery Format falls Base→Ext for Fable (−1.07), Kimi (−0.96) and Opus (−0.44), and becomes the 2nd-worst category of 10 for 3 models (F). Delivery is scored with near-zero judge spread, so the drop is not judge noise (B). ComfyUI's `validate_prompt` is type/wiring only (source). | Delivery-format and logo errors are what make an output "unusable however good the rest is" (Hyde's words). They are objectively checkable at ~zero cost. | Static verifier + real ComfyUI execution (E3). LLM harness A/B with identical seeds (E2). | Medium | Medium-high |
| H2 | **Evaluation measurement is less stable than the reporting implies.** Judge disagreement is large, the method choice shifts every score, the prose and charts use different methods, and no CIs are given. | avg3 − min-of-3 = 0.41–0.74 on 9/10 categories (B). The Finding 2 prose matches `j2` 5/5 and the chart default `avg3` 0/5 (A). Gemini is +0.37 above the contestant-judges on Text & Logo and Matches Reference (B). | Hyde sells private evals as the basis for model/harness choice. Unreported measurement variance turns into wrong recommendations. | Re-analysis of embedded aggregates (E1). | Low | High |
| H3 | **Self-preference.** gpt-6-astra and claude-opus-5 judge their own workflows' outputs. | Judge families overlap with contestants. The literature documents self-enhancement bias (arXiv 2404.13076, 2306.05685). | It would bias the leaderboard toward judge models. | Derive the third judge g = 3·avg3 − 2·j2, fit (j2 − g) on quality for non-judge contestants, and test residuals for astra and opus (C). | Low | Low-medium |
| H4 | Deterministic claims (delivery format) are scored by LLM judges, which is wasteful and noisy. | Delivery format is a pixel-size property. | Cost and noise. | B: judge spread on Delivery. | Low | Low |
| H5 | **The "best value" (Pareto) recommendations are not stable at 2 attempts.** | The quality/all-in-cost frontier changes between attempt 1 and attempt 2 (G). | "Which model and harness should we use?" is the decision Hyde's evals exist to support. | Per-attempt frontier, per scoring method (G). | Low | Medium |
| H6 | Best-of-2 selection in "like-for-like" inflates scores, and does so differently across models. | Common (best-of-2) − pooled mean ≈ +0.18 for strong models (D). Weak models have fewer double successes at Base. | It could manufacture apparent harness gains for weak models. | Estimate: inflation ≈ σ/√π × P(both attempts succeed). | Low | Medium |
| H7 | Cross-model "quality on successful tasks" is confounded by which tasks each model completes. | Sol "scores higher than Fable and Opus … though on the smaller set of tasks it completes" (Hyde acknowledges this). | Model ranking. | Needs per-task data. | — | Medium |
| H8 | A compensatory weighted mean contradicts the ship test. A wrong logo is "unusable", yet a 0 on one claim among 19 barely moves the mean. | The article's own words vs its scoring formula (Exhibit 1). | The professional bar of 4.5 on a mean is not the same as a "ship" decision. | Needs per-claim scores and designer verdicts. | — | Medium |
| H9 | The tool budget is spent inefficiently. Extended Plus adds ~40% cost for ≤6pp. | F1, F3. | Cost. | Needs Hyde's traces. | Medium | Medium |
| H10 | Base failures are trivially fixable schema errors ("seed not set", "node not installed"). One validate-and-repair turn would get most of Extended's execution gain at Base cost. | Exhibit 2 failure reasons. | Cost per successful output. | Local harness ablation. | Low | Medium |
| H11 | Long loops lose exact requirements (Hyde's hypothesis 2). Restating the brief inside the loop would help. | F2 hypothesis. | It's a competing explanation for H1. | The `restate` ablation arm in E2. | Low | Medium |
| H12 | The human/LLM score combination and the 4.5-bar calibration method are undocumented. | Article. | Reproducibility. | Not testable externally. | — | — |
| H13 | Cost definitions differ between the Exhibit 6 and 7 captions ("ALL attempts" vs "ALL tasks attempted"). | Captions. | Cosmetic: the numbers match the same formula. | Recompute Kimi $0.41 / Opus $0.38. | Low | High (that it's cosmetic) |

## Scores

| # | Sig (25) | Impact (25) | Evidence (20) | Validate (15) | Feasible (15) | **Weighted** |
|---|---|---|---|---|---|---|
| H1 | 8 | 8 | 8 | 8 | 9 | **8.15** |
| H2 | 7 | 7 | 9 | 9 | 7 | **7.70** |
| H5 | 7 | 7 | 7 | 7 | 7 | **7.00** |
| H10 | 6 | 7 | 6 | 6 | 8 | 6.55 |
| H11 | 6 | 6 | 5 | 7 | 9 | 6.40 (tested inside H1) |
| H8 | 8 | 7 | 6 | 3 | 6 | 6.30 |
| H6 | 5 | 4 | 7 | 6 | 8 | 5.75 |
| H7 | 6 | 6 | 7 | 4 | 5 | 5.75 |
| H3 | 7 | 6 | 3 | 6 | 6 | 5.65 |
| H4 | 4 | 4 | 6 | 7 | 9 | 5.60 |
| H9 | 5 | 6 | 6 | 3 | 6 | 5.30 |
| H12 | 6 | 5 | 5 | 2 | 3 | 4.50 |
| H13 | 1 | 1 | 9 | 9 | 9 | 4.10 |

**Selected for validation: H1, H2 and H5.** H3 was cheap to test, so I tested it anyway (see 03). H11 runs as an ablation arm of H1.

H8 is arguably the most important *conceptual* point: the scoring formula contradicts the ship test. But it can't be validated without per-claim data, so it goes to Future Work rather than the flagship. That follows the brief's rule: don't confuse an interesting question with a validatable engineering opportunity.
