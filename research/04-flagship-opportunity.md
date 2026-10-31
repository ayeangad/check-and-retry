# 04 — Flagship: answering Hyde's open question, "What happens when models check their own output and retry?"

> The AtelierBench post closes with: *"The benchmark raises a broader set of questions: What happens when models
> check their own output and retry? …"* This project runs that experiment for the part of a brief that can be
> checked objectively (delivery size, deliverable count, exact logo and position, reference composition). It compares
> three answers to "check": **no brief check** (Hyde's Extended), **check the output and retry** (execute, inspect the
> image, retry), and **check the plan and retry** (a static brief contract on the workflow graph, before anything runs).

## Problem

In AtelierBench's Extended harness the agent can validate its ComfyUI workflow before it runs. That validation answers "will this execute?", not "will the output meet the brief?". A model can therefore converge on a workflow that validates and executes but violates objectively stated requirements: pixel size, number of deliverables, an untouched logo in a specified position, preserved reference composition. Hyde's data shows the effect at benchmark scale. Hyde names the mechanism as a hypothesis. Hyde lists "what happens when models check their own output and retry?" as an open question.

## Evidence

1. **Hyde's published aggregates** (VERIFIED, `data/derived/reanalysis.md` §F):
   - Delivery Format Base→Extended: Fable 4.56 → 3.49, Kimi 3.90 → 2.94, Opus 4.24 → 3.80.
   - On Extended, Delivery is the 2nd-worst of 10 categories for Fable, Kimi and Gemini-flash, though it is the most mechanically checkable.
   - Astra holds 4.6–4.85, so the requirement is achievable.
2. **Measurement is clean** (VERIFIED, §B). The three judges agree on Delivery Format to within 0.01. Every other category spreads 0.41–0.74. The drop is not judge noise.
3. **The validator is brief-blind** (VERIFIED, E3). In an independent reproduction on real ComfyUI, 142/142 brief-violating workflows pass `validate_prompt`.
4. **Hyde's own words**: "the harness's tools check that a workflow runs, not that the output matches the brief, so a model can fix the workflow at the expense of the brief", and "evaluations need to extend beyond whether a workflow runs to whether the output actually meets the design brief."

## Root cause

ComfyUI validation is a type and wiring check: node exists, inputs typed, enum values legal, edges connect. Brief requirements are *semantic properties of the dataflow*, invisible to it:
- **Geometry.** Latent nodes silently floor to multiples of 8. Resizes compose. The last resize wins.
- **Pixel provenance.** Did the supplied logo reach the output untouched, or pass through a resample, a VAE or a sampler?
- **Information flow.** Does the reference's latent survive a sampler at denoise 1.0?

When the only feedback signal is "valid / invalid", an agent's repair moves are free to trade brief conformance for validity. Example: replacing a non-existent compositing node with a simpler graph that drops the logo. The loop then reports success.

## Consequences if unresolved

- Harness improvements that raise execution rate can quietly lower deliverable quality. That is exactly Finding 2's "a better harness can make the most capable models worse".
- Cost: every off-spec output is a paid generation plus a redo.
- For Hyde's eval product: the benchmark ends up measuring a harness defect as a model property ("Fable is worse with tools").

## Experimental question

1. Does checking against the brief and retrying raise the rate of deliverables that meet the brief, compared with executability-only validation at the same budget?
2. Does it matter *what* you check: the rendered output (needs a paid generation per attempt) or the workflow graph (free, before execution)?
3. What does checking cost, in LLM tokens, tool turns and image generations per conforming deliverable?

## Proposed solution: brief contracts (the "check the plan" arm)

Compile the brief's **objectively checkable claims** into a contract, and check the workflow graph against it by **static abstract interpretation**, before execution. The violations go into the **same validate tool** the agent already uses.

- **Abstract domain** per edge: `Img(w, h, batch, logo_state, ref_state)` / `Lat(...)`. Transfer functions mirror ComfyUI's implementations (cited in code). Unmodelled nodes yield UNKNOWN, and dependent checks *abstain*, so there is no false alarm.
- **Checks**: delivery size, single deliverable, logo pixel-exactness (no resample, VAE or sampler after paste; not stretched; not used as background; not cropped through), logo corner, reference provenance (loaded, encoded, sampled at denoise < 1, not covered).
- **Feedback**: node-level cause plus concrete fix, e.g. "EmptyLatentImage (node 4) is 1080x1350, but latents are 1/8 scale, so ComfyUI floors it to 1080x1344. Fix: generate at a multiple of 8, then ImageScale(1080, 1350, crop=center) as the last resize before SaveImage and BEFORE compositing the logo."
- **Cost**: no model calls, under 1 ms per check, deterministic.

What it deliberately does *not* do: judge style, text glyphs or aesthetics. Those stay with VLM/LLM judges and designers. The contract covers the slice of the brief where a judge is unnecessary.

## Arms (as run)

All tool arms share one prompt, tool set, seed and 15-call budget, and are forked from one shared conversation at the first ComfyUI-valid submission:
- `extended`: no brief check (executability only; Hyde-like, but friendlier — see Limitations).
- `output_retry`: execute, check the delivered image, retry.
- `output_retry_rich` (experiment D only): `output_retry` whose feedback also states the logo's size and target x,y, i.e. the same information the contract gives.
- `contract`: static graph check before execution, retry.
- `base`: single shot, no tools.

## Validation criteria (locked before any result was computed)

1. Primary: contract vs extended on all-claims-pass, paired on brief × seed. Helps = gain ≥ 5 pp AND 95% CI (cluster bootstrap over briefs) entirely above 0; harms = CI entirely below 0; otherwise not shown. Same rule for output_retry vs extended. Everything else exploratory.
2. Verifier precision and recall vs real execution on LLM-written workflows; abstain rather than guess.
3. Cost per conforming output: image generations, tokens, check time.
4. (Added after E2, D13) Information vs checking: equal-information output check (`output_retry_rich`) and an informed-brief condition.

## Results (full numbers in 03)

- **Brief-blind validation lets violations through**: 142/142 brief-violating workflows pass ComfyUI validation (E3); on logo briefs extended = base (E2).
- **A check that returns an actionable fix rescues them**: logo briefs 9% → 88% (D-B, n = 111).
- **Checking the plan matches checking the output, at half the image generations**: 88% vs 88%, CI [−5.4, +5.4]; 1.06 vs 2.20 generations per conforming output (D-B).
- **But much of it is missing information**: stating the logo's pixel size alone lifts unchecked extended to 89% on logo briefs (D-A, n = 37). Fix the harness's information gap first; the check catches what remains.
- **The contract is an exact selector**: in best-of-4 it equals the oracle (E4), with 0 good samples rejected out of 290 — a cheap deterministic filter/reward.
- **Replicates on a 4B local model** (+29 pp vs extended, n = 48 pairs), where construction, not the brief, is the main failure.

## Limitations

- No access to Hyde's tasks, harness, judges or image models. Main run: DeepSeek V4.1 Flash on 73 synthetic long briefs (3 seeds); replication: qwen3.5:4b on 24 short briefs. Absolute rates do not transfer; no frontier model was tested.
- Our `extended` is friendlier than Hyde's Extended: a 12-node reference in every prompt, a tuned `search_nodes`, and validation forced at submit (D5, D8). Arm comparisons are fair; absolute comparisons with Hyde's numbers are not.
- **Information confound**: in our harness the agent cannot learn an input image's pixel size. Stating it (D-A) makes most of the logo-brief gap disappear. Whether Hyde's agents know input sizes is unknown.
- Hyde's hypothesis 2 ("lose track in long loops") was not tested (`restate` arm dropped, D6).
- Image content is stubbed (geometry exact, pixels meaningless): no claims about text glyphs, style or aesthetics. Stub geometry fidelity is inferred from code, not verified against a real model.
- Contract extraction: the contract comes from a structured spec mirroring the brief's explicit statements (analogous to Hyde's designer-verified claims list). Free-text extraction not evaluated.
- Transfer-function coverage ~20 core nodes; custom nodes → more abstentions.
- Experiment D was designed after seeing E2 results and run without written predictions; its interpretation is post hoc.
