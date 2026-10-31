"""E2: does brief-contract feedback in the validate tool fix spec drift? (local LLM, real ComfyUI)

Each (brief, arm, seed) episode is written as one JSONL line, including the full transcript.
The run is resumable: episodes already in the output file are skipped.

Usage:
  python poc/experiments/run_e2.py --model qwen3.5:2b --seeds 0 1 --arms base extended output_retry contract \
      --out poc/results/e2_qwen3.5-2b.jsonl [--limit 4]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import urllib.request
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from atelier_poc import brief_contract  # noqa: E402
from atelier_poc.briefs import load_briefs  # noqa: E402
from atelier_poc.comfy_client import ComfyClient  # noqa: E402
from atelier_poc.evaluator import evaluate  # noqa: E402
from atelier_poc.harness import ARMS, run_branched, run_episode  # noqa: E402
from atelier_poc.llm import DeepSeekChat, OllamaChat, SpendLedger  # noqa: E402

log = logging.getLogger("e2")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3.5:2b")
    ap.add_argument("--seeds", type=int, nargs="+", default=[0])
    ap.add_argument("--arms", nargs="+", default=list(ARMS), choices=ARMS)
    ap.add_argument("--briefs", type=Path, default=ROOT / "tasks/briefs.jsonl")
    ap.add_argument("--input-dir", type=Path, default=ROOT / "comfy_base/input")
    ap.add_argument("--output-dir", type=Path, default=ROOT / "comfy_base/output")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-tool-calls", type=int, default=15)
    ap.add_argument("--backend", choices=["ollama", "deepseek"], default="ollama")
    ap.add_argument("--cap-usd", type=float, default=2.0, help="hard spend cap for --backend deepseek")
    ap.add_argument("--ledger", type=Path, default=ROOT / "results/deepseek_spend.json")
    ap.add_argument("--families", nargs="+", default=None, help="only run briefs of these families")
    ap.add_argument("--state-logo-size", action="store_true",
                    help="experiment D-A: append the logo file's pixel size to the brief text (all arms)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    briefs = load_briefs(a.briefs)
    if a.families:
        briefs = [b for b in briefs if b.family in a.families]
    if a.state_logo_size:
        briefs = [with_logo_size(b, a.input_dir) for b in briefs]
    briefs = briefs[: a.limit]
    comfy = ComfyClient(output_dir=a.output_dir)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if a.out.exists():
        for l in a.out.read_text().splitlines():
            r = json.loads(l)
            done.add((r["brief_id"], r["arm"], r["seed"]))
    tool_arms = [x for x in a.arms if x != "base"]
    ledger = SpendLedger(a.ledger, a.cap_usd) if a.backend == "deepseek" else None

    def make_llm(seed):
        if a.backend == "deepseek":
            return DeepSeekChat(a.model, seed=seed, ledger=ledger)
        return OllamaChat(a.model, seed=seed)

    if ledger:
        log.info("DeepSeek backend, model=%s, spent so far $%.4f of cap $%.2f", a.model, ledger.spent(), a.cap_usd)
    for seed in a.seeds:
        for b in briefs:
            for attempt in range(3):      # retry a brief whose episodes hit an outage, after services recover
                todo = [x for x in a.arms if (b.id, x, seed) not in done]
                if not todo:
                    break
                eps = {}
                if "base" in todo:
                    eps["base"] = run_episode(b, "base", make_llm(seed), comfy, a.input_dir)
                if any(x in todo for x in tool_arms):
                    # shared prefix, forked at the first ComfyUI-valid submission (see harness.run_branched)
                    eps.update(run_branched(b, tool_arms, make_llm(seed), comfy, a.input_dir,
                                            max_tool_calls=a.max_tool_calls))
                for arm in todo:
                    if record(a, b, eps[arm], comfy):
                        done.add((b.id, arm, seed))
                if any((b.id, x, seed) not in done for x in todo):
                    wait_for_services(comfy)


def with_logo_size(b, input_dir: Path):
    """Experiment D-A: tell the agent the logo's pixel size, which the contract's feedback otherwise reveals."""
    if not b.spec.logo:
        return b
    from PIL import Image
    with Image.open(input_dir / b.spec.logo.file) as im:
        w, h = im.size
    return replace(b, text=b.text + f" (The logo file {b.spec.logo.file} is {w}x{h} pixels.)")


def wait_for_services(comfy, max_wait_s: float = 1800) -> None:
    """Block until Ollama and ComfyUI both answer again (rather than racing through the queue)."""
    t0 = time.monotonic()
    while time.monotonic() - t0 < max_wait_s:
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5).read()
            comfy._req("/system_stats", timeout=5)
            log.info("services reachable again after %.0fs", time.monotonic() - t0)
            return
        except Exception:
            time.sleep(15)
    log.error("services still unreachable after %.0fs; giving up on this brief for now", max_wait_s)

INFRA_ERRORS = ("timed out", "Connection", "URLError", "RemoteDisconnected", "BrokenPipe")


def record(a, b, ep, comfy) -> bool:
    if ep.error and "BudgetExceeded" in ep.error:
        log.error("spend cap reached; stopping cleanly (%s). %s/%s seed=%d not recorded.", ep.error, b.id, ep.arm, ep.seed)
        raise SystemExit(0)
    if ep.error and any(t in ep.error for t in INFRA_ERRORS):
        # e.g. laptop suspended mid-episode: not a model outcome, so leave it out and let a resume retry it
        log.warning("%s %s seed=%d skipped (infrastructure error, will retry): %s",
                    b.id, ep.arm, ep.seed, ep.error)
        return False
    try:
        run = comfy.run(ep.workflow) if ep.workflow else None
    except OSError as e:
        log.warning("%s %s seed=%d skipped (ComfyUI unreachable, will retry): %s", b.id, ep.arm, ep.seed, e)
        return False
    executed = bool(run and run.ok)
    out = evaluate(b.spec, run.output_files if executed else [], a.input_dir, executed)
    # Post-hoc only, never shown to the agent here: what the verifier WOULD say about the shipped
    # workflow. Feeds the out-of-distribution validity check (verifier vs real outcome).
    pred = brief_contract.check(ep.workflow, b.spec, a.input_dir).verdicts(b.spec) if ep.workflow else None
    rec = {**{k: v for k, v in asdict(ep).items() if k != "transcript"},
           "family": b.family, "spec_div8": b.spec.width % 8 == 0 and b.spec.height % 8 == 0,
           "executed": executed, "run_error": None if executed else (run.error if run else "no workflow"),
           "claims": out.claims, "score": out.score, "all_pass": out.all_pass, "eval_details": out.details,
           "verifier_pred": pred, "transcript": ep.transcript, "ts": time.time()}
    with a.out.open("a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    u = ep.usage
    log.info("%s %-12s seed=%d exec=%s score=%.2f all=%s tools=%d brej=%d runs=%d tok=%d/%d %.0fs %s",
             b.id, ep.arm, ep.seed, executed, out.score, out.all_pass, ep.tool_calls, ep.brief_rejections,
             ep.executions, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), ep.wall_s,
             (ep.error or (run.error if run and not run.ok else "")) or "")
    return True


if __name__ == "__main__":
    main()
