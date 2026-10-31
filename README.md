# Check and retry

An independent experiment answering the open question at the end of Hyde × SILVERSIDE's
[AtelierBench](https://hyde.ai/blog/atelier): *what happens when models check their own output and retry?*

**Short answer.** On DeepSeek V4.1 Flash (the open-weights contestant in AtelierBench), checking the brief
and retrying fixes violations that ComfyUI's validator lets through, but only when the check says how to fix
them. Checking the workflow graph before it runs gets the same result as checking the rendered image, with half
the image generations. Much of what the check fixed turned out to be information the agent was never given
(the logo's pixel size).

| | result | sample |
|---|---|---|
| Brief met, validation only | 9% (5–16) | 111 runs |
| Brief met, check the output | 27% (20–36) | 111 runs |
| Brief met, check the output with the fix | 88% (81–93) | 111 runs |
| Brief met, check the plan (static brief contract) | 88% (81–93) | 111 runs |
| Plan check minus output check with the fix | 0.0 points (−5.4 to +5.4) | 111 paired runs |
| Image renders per run, plan vs output check | 0.94 vs 1.95 | 111 runs each |
| Validation only, logo size written into the brief | 89% (75–96) | 37 runs |
| Brief-violating workflows that pass ComfyUI validation | 142 of 142 | 214 workflows |
| Plan check on model-written workflows | 0 false alarms, 94% of violations caught | 3,011 claim checks |

Not affiliated with Hyde or SILVERSIDE. None of Hyde's tasks, harness or per-task data were available.
Objective claims only (size, count, logo pixels and position, reference composition); image content is stubbed.

## Where things are

- `deliverables/site/` — the write-up as a small static site (open `index.html` via any static server).
- `poc/` — the verifier (`brief_contract.py`), the independent evaluator, the agent harness, experiments, tests
  and raw results including every transcript. Setup and reproduction: [`poc/README.md`](poc/README.md).
- `research/` — investigation notes: what AtelierBench measures, ranked opportunities, validation results,
  the flagship problem statement, and a self-audit.
- `analysis/` — re-analysis of the aggregates embedded in Hyde's article.
