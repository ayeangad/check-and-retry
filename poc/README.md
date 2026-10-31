# brief-contract: pre-execution brief conformance for LLM-authored ComfyUI workflows

An independent proof of concept motivated by Hyde × SILVERSIDE's AtelierBench (https://hyde.ai/blog/atelier).
**It is not Hyde's code, and none of Hyde's tasks, prompts or harness were available.**

## The problem in one paragraph

AtelierBench's "Extended" harness lets a model look up ComfyUI nodes and *validate* its workflow before
running it. Hyde's own data shows that this better harness makes strong models worse on **Delivery Format**:
Fable 4.56 → 3.49 and Kimi 3.90 → 2.94 on a 0–5 scale. All three LLM judges agree on this category to within
0.01, so the drop is not judge noise. Hyde's hypothesis is that "the harness's tools check that a workflow runs,
not that the output matches the brief". ComfyUI's validator is indeed brief-blind. In experiment E3 below, **142 of
142 workflows that break a brief requirement pass ComfyUI validation**.

## What this builds

`atelier_poc/brief_contract.py` is a static verifier that abstractly interprets a ComfyUI API-format graph. Every
IMAGE/LATENT edge carries an abstract value: pixel size and batch, whether the supplied logo's pixels are still
intact and where they sit, and whether the reference image's layout still reaches the output. The verifier checks
the brief's objectively checkable claims **before execution**, in under 1 ms, with no model calls:

| claim | what it catches (all of these pass ComfyUI validation) |
|---|---|
| `delivery_size` | latent sizes floored to /8 (1350 → 1344), missing final resize, upscaler without exact rescale |
| `single_output` | batch_size > 1, extra SaveImage nodes |
| `logo_exact` | logo resized (`resize_source`, any resample after pasting), regenerated (VAE/KSampler after pasting), used as background, cropped |
| `logo_position` | logo not in the requested corner (position tracked through crops and pads) |
| `reference_composition` | reference never loaded or never encoded, img2img at denoise 1.0, reference covered |

Nodes it has no model for make it **abstain** ("could not verify") instead of raising a false alarm.
Violations come back as node-level causes plus a concrete fix, formatted to sit next to ComfyUI's own validation
errors in an agent's tool loop.

## Layout

```
atelier_poc/
  brief_contract.py      the verifier (the contribution)
  evaluator.py           INDEPENDENT outcome scorer: reads only the PNGs ComfyUI wrote (size, exact logo match via FFT, layout correlation)
  harness.py             agent harnesses: base / extended / output_retry / output_retry_rich / contract
  comfy_client.py        ComfyUI HTTP client (validate, run, collect outputs)
  llm.py                 Ollama + DeepSeek clients with token/latency/$ accounting and a hard spend cap
  briefs.py              Brief + Spec (the objectively checkable claims)
  reference_workflows.py correct reference workflows + 12 realistic mutations (E3 corpus)
comfy_base/
  custom_nodes/atelier_stub/   geometry-faithful stand-ins for model internals + /atelier/validate route
  models/                      empty placeholder files named in the model catalog
tasks/generate_tasks.py  24 seeded short briefs + synthetic logos / reference images
tasks_long/               73 long Exhibit-style briefs (main run), incl. Hyde's Exhibit 1 brief verbatim
experiments/             run_e2.py, run_e3_verifier.py, run_e4_selection.py, analyze_e2.py, analyze_d.py, primary_test.py
tests/                   pytest suite (offline)
results/                 raw JSONL + reports + figures
```

## Setup and reproduction

Requirements: Python 3.12, `uv`, Ollama, about 3 GB disk. Tested on a GTX 1650 Ti (4 GB) laptop. CPU-only works but is slower.

```bash
# from the repo root (../)
uv venv .venv --python 3.12
uv pip install --python .venv torch torchvision --index-url https://download.pytorch.org/whl/cpu
git clone https://github.com/comfyanonymous/ComfyUI vendor/ComfyUI   # tested at b5a4321
uv pip install --python .venv -r vendor/ComfyUI/requirements.txt pytest matplotlib
ollama pull qwen3.5:4b

# placeholder model files (ComfyUI validates names; the stub node pack replaces model internals)
mkdir -p poc/comfy_base/models/{checkpoints,upscale_models} poc/comfy_base/input poc/comfy_base/output
touch poc/comfy_base/models/checkpoints/{sdxl_base_1.0,juggernautXL_photoreal_v9,animagineXL_anime_v3}.safetensors
touch poc/comfy_base/models/upscale_models/4x-UltraSharp.pth

# start ComfyUI with the stub pack
.venv/bin/python vendor/ComfyUI/main.py --cpu --port 8188 --base-directory poc/comfy_base \
    --disable-auto-launch --disable-api-nodes --disable-manager-ui &

.venv/bin/python poc/tasks/generate_tasks.py --out poc/tasks --input-dir poc/comfy_base/input
.venv/bin/python -m pytest -q poc/tests
.venv/bin/python poc/experiments/run_e3_verifier.py --out poc/results/e3_verifier.jsonl
.venv/bin/python poc/experiments/run_e2.py --model qwen3.5:4b --seeds 0 1 --out poc/results/e2_qwen3.5-4b.jsonl
.venv/bin/python poc/experiments/analyze_e2.py poc/results/e2_*.jsonl --report poc/results/e2_report.md --fig poc/results/figs
```

## Results (2026-10-31)

Main model: DeepSeek V4.1 Flash (AtelierBench's `deepseek-v4.1-flash`). Outcome = every objective claim passes on the PNG ComfyUI actually wrote. Full numbers and CIs: `../research/03-validation-results.md`.

| finding | number | n |
|---|---|---|
| ComfyUI validation is brief-blind | 142/142 brief-violating workflows validate | 214 workflows (E3) |
| A check with an actionable fix rescues logo briefs | executability-only 9% → plan check 88% | 111 pairs (D-B) |
| Plan check vs equally-informative output check | 88% vs 88%, Δ 0.0 pp, 95% CI [−5.4, +5.4] | 111 pairs (D-B) |
| …at half the image generations | 1.06 vs 2.20 generations per conforming output | 111 per arm (D-B) |
| But much of it is missing information | stating the logo's pixel size: executability-only → 89% | 37 (D-A) |
| The contract as a best-of-4 selector | = oracle on every brief; 0/149 good samples rejected | 73 briefs (E4) |
| Verifier on LLM-written workflows | 0 false alarms, 94% recall, 2.6% abstain | 2,932 claim checks (E2) |
| Replication on qwen3.5:4b (local) | contract − extended +29 pp [+17, +42] | 48 pairs |
| Check cost | 0.3–0.7 ms CPU, no model calls | — |

Main E2 (73 briefs × 3 seeds): base 49%, extended 53%, output_retry 62%, contract 93%. Most of the contract's E2 advantage turned out to be the information its feedback carried (logo size, exact paste position); see experiment D.

Reproduce the DeepSeek runs (needs `~/.deepseek_key`; ledger at peak prices):
```bash
poc/run_deepseek.sh                     # main E2
poc/queue_e4.sh                         # E4
poc/run_d.sh && poc/run_d_blind_seeds12.sh   # experiment D
.venv/bin/python poc/experiments/primary_test.py poc/results/e2_deepseek_long.jsonl
.venv/bin/python poc/experiments/analyze_d.py poc/results/d_blind.jsonl output_retry_rich:contract
```

## What is real and what is stubbed

The following are all real, unmodified ComfyUI code: the node registry (687 nodes), `validate_prompt`, the graph
executor, and every image-space node (LoadImage, ImageScale, ImageCrop, ImageCompositeMasked, SaveImage, …).
Model *internals* are stubbed, keeping their geometry: VAE ×/÷8 with remainder cropping, the sampler keeps the
latent shape and blends with seeded noise according to `denoise`, and the upscaler is ×4. Delivery size, output
count, logo pixel integrity and reference provenance are therefore measured on real output files. Image *content*
is not realistic, so this project makes **no claims about style, text glyphs, anatomy or aesthetic quality**.

See `../research/` for the investigation and `../deliverables/` for the report and proposal.
