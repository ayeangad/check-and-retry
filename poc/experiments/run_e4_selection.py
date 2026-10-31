"""E4: the brief contract as a selection signal (best-of-n), the parallel counterpart of retry.

Hyde's post points to fine-tuning smaller models on proven workflows and judge models for scalable
scoring. Both need a cheap, reliable signal for which workflows are good. This experiment measures the
contract as that signal, with no execution:

  for each brief, draw n single-shot workflows (the Base prompt, temperature 0.8), then
    random      pick one ComfyUI-valid sample at random              (expected value over valid samples)
    contract    pick the first sample that is ComfyUI-valid AND passes the static brief contract
                (fallback: first valid sample)
    oracle      any sample meets the brief (upper bound of selection at this n)
Every sample is also executed and scored by the independent evaluator, so all three are measured
on real outputs. Usage cost is tracked by the shared spend ledger and hard cap.

Usage: python poc/experiments/run_e4_selection.py --n 4 --out poc/results/e4_selection.jsonl
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atelier_poc import brief_contract  # noqa: E402
from atelier_poc.briefs import load_briefs  # noqa: E402
from atelier_poc.comfy_client import ComfyClient  # noqa: E402
from atelier_poc.evaluator import evaluate  # noqa: E402
from atelier_poc.harness import SYS_BASE, _user_prompt, extract_json  # noqa: E402
from atelier_poc.llm import BudgetExceeded, DeepSeekChat, SpendLedger  # noqa: E402

log = logging.getLogger("e4")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--briefs", type=Path, default=ROOT / "tasks_long/briefs.jsonl")
    ap.add_argument("--input-dir", type=Path, default=ROOT / "comfy_base/input")
    ap.add_argument("--output-dir", type=Path, default=ROOT / "comfy_base/output")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--model", default="deepseek-flash")
    ap.add_argument("--cap-usd", type=float, default=2.0)
    ap.add_argument("--ledger", type=Path, default=ROOT / "results/deepseek_spend.json")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    comfy = ComfyClient(output_dir=a.output_dir)
    ledger = SpendLedger(a.ledger, a.cap_usd)
    done = {json.loads(l)["brief_id"] for l in a.out.read_text().splitlines()} if a.out.exists() else set()
    for b in load_briefs(a.briefs):
        if b.id in done:
            continue
        llm = DeepSeekChat(a.model, temperature=a.temperature, ledger=ledger)
        samples = []
        try:
            for i in range(a.n):
                msgs = [{"role": "system", "content": SYS_BASE}, {"role": "user", "content": _user_prompt(b)}]
                wf = extract_json(llm.chat(msgs).get("content", ""))
                s = {"i": i, "parsed": wf is not None, "valid": False, "contract_ok": None, "executed": False,
                     "all_pass": False, "claims": None}
                if wf:
                    s["valid"] = comfy.validate(wf).valid
                    if s["valid"]:
                        s["contract_ok"] = brief_contract.check(wf, b.spec, a.input_dir).ok
                        run = comfy.run(wf)
                        o = evaluate(b.spec, run.output_files if run.ok else [], a.input_dir, run.ok)
                        s.update(executed=run.ok, all_pass=o.all_pass, claims=o.claims)
                samples.append(s)
        except BudgetExceeded as e:
            log.error("spend cap reached (%s); stopping before %s", e, b.id)
            return
        valid = [s for s in samples if s["valid"]]
        rand = st.mean(s["all_pass"] for s in valid) if valid else 0.0
        pick = next((s for s in valid if s["contract_ok"]), valid[0] if valid else None)
        rec = {"brief_id": b.id, "family": b.family, "n": a.n, "samples": samples, "n_valid": len(valid),
               "random_pass": rand, "contract_pass": bool(pick and pick["all_pass"]),
               "contract_found": any(s["contract_ok"] for s in valid), "oracle_pass": any(s["all_pass"] for s in samples),
               "usage": {"calls": llm.usage.calls, "usd": llm.usage.usd}}
        with a.out.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        log.info("%s valid=%d/%d random=%.2f contract=%s oracle=%s $%.4f", b.id, len(valid), a.n, rand,
                 rec["contract_pass"], rec["oracle_pass"], llm.usage.usd)
    rows = [json.loads(l) for l in a.out.read_text().splitlines()]
    print(f"briefs={len(rows)}  random-valid pick={st.mean(r['random_pass'] for r in rows):.3f}  "
          f"contract pick={st.mean(r['contract_pass'] for r in rows):.3f}  oracle={st.mean(r['oracle_pass'] for r in rows):.3f}")


if __name__ == "__main__":
    main()
