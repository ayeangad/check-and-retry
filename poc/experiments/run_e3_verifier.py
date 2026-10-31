"""E3: verifier accuracy against real execution, on a corpus of reference + mutated workflows.

For every brief: the correct reference workflow plus every applicable mutation. Each one is
  1. validated by ComfyUI's own validator     (does the existing check catch it?)
  2. executed in ComfyUI                       (ground truth: the PNGs it really writes)
  3. scored by evaluator.py                    (actual per-claim pass/fail, from pixels)
  4. statically checked by brief_contract.py  (predicted per-claim pass/fail, from the graph)

Writes per-workflow JSONL plus a summary of per-claim confusion counts.
Usage: python poc/experiments/run_e3_verifier.py --out poc/results/e3_verifier.jsonl
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atelier_poc.brief_contract import check  # noqa: E402
from atelier_poc.briefs import load_briefs  # noqa: E402
from atelier_poc.comfy_client import ComfyClient  # noqa: E402
from atelier_poc.evaluator import evaluate  # noqa: E402
from atelier_poc.reference_workflows import MUTATIONS, build_correct, set_input_dir  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--briefs", type=Path, default=ROOT / "tasks/briefs.jsonl")
    ap.add_argument("--input-dir", type=Path, default=ROOT / "comfy_base/input")
    ap.add_argument("--output-dir", type=Path, default=ROOT / "comfy_base/output")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    set_input_dir(a.input_dir)
    comfy = ComfyClient(output_dir=a.output_dir)
    rows = []
    for b in load_briefs(a.briefs):
        base = build_correct(b, a.input_dir)
        cases = [("correct", base, set())] + [(k, *r) for k, f in MUTATIONS.items() if (r := f(base, b))]
        for name, wf, expected in cases:
            v = comfy.validate(wf)
            run = comfy.run(wf)
            o = evaluate(b.spec, run.output_files if run.ok else [], a.input_dir, run.ok)
            t0 = time.perf_counter()
            rep = check(wf, b.spec, a.input_dir)
            ms = (time.perf_counter() - t0) * 1000
            pred = rep.verdicts(b.spec)
            rows.append({"brief": b.id, "family": b.family, "case": name, "comfy_valid": v.valid,
                         "executed": run.ok, "actual": o.claims, "pred": pred,
                         "expected_broken": sorted(expected), "verify_ms": ms,
                         "nodes": len(wf)})
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    # ---- summary
    cm = Counter()          # (claim, actual_pass, pred) -> n
    for r in rows:
        if not r["executed"]:
            continue
        for c, act in r["actual"].items():
            cm[(c, act, r["pred"].get(c))] += 1
    claims = sorted({k[0] for k in cm})
    print(f"workflows: {len(rows)}  executed: {sum(r['executed'] for r in rows)}  "
          f"ComfyUI-valid: {sum(r['comfy_valid'] for r in rows)}")
    broken = [r for r in rows if r["executed"] and not all(r["actual"].values())]
    print(f"workflows that violate >=1 brief claim: {len(broken)}; of those accepted by ComfyUI's validator: "
          f"{sum(r['comfy_valid'] for r in broken)}")
    print(f"{'claim':24s} {'TP':>4s} {'FN':>4s} {'FP':>4s} {'TN':>4s} {'abst':>5s}  recall  precision")
    for c in claims:
        tp = cm[(c, False, False)]; fn = cm[(c, False, True)]
        fp = cm[(c, True, False)]; tn = cm[(c, True, True)]
        ab = cm[(c, False, None)] + cm[(c, True, None)]
        rec = tp / (tp + fn) if tp + fn else float("nan")
        prec = tp / (tp + fp) if tp + fp else float("nan")
        print(f"{c:24s} {tp:4d} {fn:4d} {fp:4d} {tn:4d} {ab:5d}  {rec:6.3f}  {prec:9.3f}")
    ms = [r["verify_ms"] for r in rows]
    print(f"verifier latency: median {st.median(ms):.2f} ms, max {max(ms):.2f} ms")
    mism = [r for r in rows if r["executed"] and any(r["pred"].get(c) is not None and r["pred"][c] != act
                                                     for c, act in r["actual"].items())]
    for r in mism[:10]:
        print("MISMATCH", r["brief"], r["case"], r["actual"], r["pred"])


if __name__ == "__main__":
    main()
