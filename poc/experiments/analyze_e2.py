"""Analyse E2 episodes: arm comparison with paired statistics, cost, and verifier validity on
LLM-written (out-of-distribution) workflows.

Usage: python poc/experiments/analyze_e2.py poc/results/e2_*.jsonl --report poc/results/e2_report.md --fig poc/results/figs
"""
from __future__ import annotations

import argparse
import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

CLAIMS = ["delivery_size", "single_output", "logo_exact", "logo_position", "reference_composition"]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def binom_two_sided(k: int, n: int) -> float:
    """Exact two-sided sign/McNemar test p-value for k successes out of n discordant pairs."""
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def load(paths: list[Path]) -> list[dict]:
    rows = []
    for p in paths:
        rows += [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    return rows


def arm_table(rows, arms) -> str:
    out = ["| arm | n | executed | all claims pass (95% CI) | mean claim pass rate | " +
           " | ".join(CLAIMS) + " | LLM calls | prompt tok | completion tok | LLM s |",
           "|" + "---|" * (10 + len(CLAIMS) - 1)]
    for arm in arms:
        rs = [r for r in rows if r["arm"] == arm]
        if not rs:
            continue
        n = len(rs)
        ex = sum(r["executed"] for r in rs)
        ap = sum(r["all_pass"] for r in rs)
        lo, hi = wilson(ap, n)
        cl = []
        for c in CLAIMS:
            app = [r["claims"][c] for r in rs if c in r["claims"]]
            cl.append(f"{sum(app)}/{len(app)}" if app else "—")
        u = [r["usage"] for r in rs]
        out.append(f"| {arm} | {n} | {ex}/{n} | {ap}/{n} = {ap/n:.0%} ({lo:.0%}–{hi:.0%}) | "
                   f"{st.mean(r['score'] for r in rs):.3f} | " + " | ".join(cl) +
                   f" | {st.mean(x['calls'] for x in u):.1f} | {st.mean(x['prompt_tokens'] for x in u):.0f} | "
                   f"{st.mean(x['completion_tokens'] for x in u):.0f} | {st.mean(x['seconds'] for x in u):.0f} |")
    return "\n".join(out)


def paired(rows, a: str, b: str, key: str = "all_pass") -> str:
    by = defaultdict(dict)
    for r in rows:
        by[(r["model"], r["brief_id"], r["seed"])][r["arm"]] = r
    pairs = [(v[a], v[b]) for v in by.values() if a in v and b in v]
    if not pairs:
        return f"no paired episodes for {a} vs {b}"
    if key == "all_pass":
        b_only = sum(1 for x, y in pairs if not x["all_pass"] and y["all_pass"])
        a_only = sum(1 for x, y in pairs if x["all_pass"] and not y["all_pass"])
        p = binom_two_sided(b_only, a_only + b_only)
        return (f"{b} vs {a} (all claims pass), {len(pairs)} paired episodes: {b} wins {b_only}, {a} wins {a_only}, "
                f"ties {len(pairs) - a_only - b_only}; exact McNemar p = {p:.4f}")
    diffs = [y["score"] - x["score"] for x, y in pairs]
    pos, neg = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    p = binom_two_sided(pos, pos + neg)
    return (f"{b} − {a} (claim pass rate), {len(pairs)} pairs: mean Δ = {st.mean(diffs):+.3f}; "
            f"+{pos} / −{neg} / ={len(diffs) - pos - neg}; sign test p = {p:.4f}")


def split_table(rows, arms, field_name: str, label: str) -> str:
    vals = sorted({str(r[field_name]) for r in rows})
    out = [f"| {label} | " + " | ".join(f"{a} all-pass" for a in arms) + " |", "|" + "---|" * (len(arms) + 1)]
    for v in vals:
        cells = []
        for a in arms:
            rs = [r for r in rows if r["arm"] == a and str(r[field_name]) == v]
            cells.append(f"{sum(r['all_pass'] for r in rs)}/{len(rs)}" if rs else "—")
        out.append(f"| {v} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def verifier_validity(rows) -> str:
    """Post-hoc verifier prediction on every SHIPPED workflow that executed vs actual outcome."""
    tp = fn = fp = tn = ab = 0
    per = defaultdict(lambda: [0, 0, 0, 0, 0])
    for r in rows:
        if not r["executed"] or not r.get("verifier_pred"):
            continue
        for c, act in r["claims"].items():
            pr = r["verifier_pred"].get(c)
            idx = 4 if pr is None else (0 if (not act and pr is False) else 1 if (not act and pr) else
                                        2 if (act and pr is False) else 3)
            per[c][idx] += 1
    out = ["| claim | TP (caught) | FN (missed) | FP (false alarm) | TN | abstain |", "|---|---|---|---|---|---|"]
    for c in CLAIMS:
        if c in per:
            v = per[c]
            out.append(f"| {c} | {v[0]} | {v[1]} | {v[2]} | {v[3]} | {v[4]} |")
            tp, fn, fp, tn, ab = tp + v[0], fn + v[1], fp + v[2], tn + v[3], ab + v[4]
    out.append(f"| **all** | {tp} | {fn} | {fp} | {tn} | {ab} |")
    return "\n".join(out)


def failure_modes(rows, arms) -> str:
    out = ["| arm | no workflow | rejected by ComfyUI validation | execution error | executed |", "|---|---|---|---|---|"]
    for a in arms:
        rs = [r for r in rows if r["arm"] == a]
        nw = sum(1 for r in rs if r["run_error"] == "no workflow")
        rej = sum(1 for r in rs if (r["run_error"] or "").startswith("rejected"))
        exe = sum(1 for r in rs if (r["run_error"] or "").startswith(("execution_error", "timeout")))
        out.append(f"| {a} | {nw} | {rej} | {exe} | {sum(r['executed'] for r in rs)} |")
    return "\n".join(out)


def loop_cost(rows, arms) -> str:
    """What checking costs. In production every workflow execution is a paid image generation
    (Hyde's 'execution_cost'). Generations per episode = executions inside the loop, plus the final
    delivery run if the shipped workflow was not already executed there."""
    out = ["| arm | submits | ComfyUI rejections | brief rejections | generations / episode | "
           "conforming outputs | generations per conforming output | LLM tokens per conforming output | check time / episode |",
           "|---|---|---|---|---|---|---|---|---|"]
    for a in arms:
        rs = [r for r in rows if r["arm"] == a]
        if not rs:
            continue
        gens = [r.get("executions", 0) + (1 if r["executed"] and not r.get("executions", 0) else 0) for r in rs]
        ok = sum(r["all_pass"] for r in rs)
        tok = sum(r["usage"]["prompt_tokens"] + r["usage"]["completion_tokens"] for r in rs)
        out.append(f"| {a} | {st.mean(r.get('submit_calls', 0) for r in rs):.2f} | "
                   f"{st.mean(r.get('exec_rejections', 0) for r in rs):.2f} | {st.mean(r.get('brief_rejections', 0) for r in rs):.2f} | "
                   f"{st.mean(gens):.2f} | {ok}/{len(rs)} | {(sum(gens) / ok) if ok else float('inf'):.2f} | "
                   f"{(tok / ok) if ok else float('inf'):.0f} | {st.mean(r.get('check_ms', 0) for r in rs):.1f} ms |")
    return "\n".join(out)


def figures(rows, arms, figdir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figdir.mkdir(parents=True, exist_ok=True)
    made = []
    present = [a for a in arms if any(r["arm"] == a for r in rows)]
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    w = 0.8 / max(1, len(present))
    for i, a in enumerate(present):
        rs = [r for r in rows if r["arm"] == a]
        ys, errs = [], []
        for c in CLAIMS + ["all_pass"]:
            vals = [r["claims"][c] for r in rs if c in r["claims"]] if c != "all_pass" else [r["all_pass"] for r in rs]
            k, n = sum(vals), len(vals)
            lo, hi = wilson(k, n)
            ys.append(k / n if n else 0); errs.append([(k / n - lo) if n else 0, (hi - k / n) if n else 0])
        xs = [j + i * w for j in range(len(ys))]
        ax.bar(xs, ys, w, label=a, yerr=list(zip(*errs)), capsize=2)
    ax.set_xticks([j + w * (len(present) - 1) / 2 for j in range(len(CLAIMS) + 1)])
    ax.set_xticklabels([c.replace("_", "\n") for c in CLAIMS] + ["ALL\nclaims"], fontsize=8)
    ax.set_ylabel("pass rate (95% Wilson CI)"); ax.set_ylim(0, 1.05); ax.legend(fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); p = figdir / "e2_claims_by_arm.png"; fig.savefig(p, dpi=150); plt.close(fig)
    made.append(str(p))
    return made


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--fig", type=Path, default=None)
    a = ap.parse_args()
    rows = load(a.files)
    arms = ["base", "extended", "output_retry", "contract"]
    parts = ["# E2 results\n", f"Episodes: {len(rows)} · models: {sorted({r['model'] for r in rows})} · "
             f"seeds: {sorted({r['seed'] for r in rows})} · briefs: {len({r['brief_id'] for r in rows})}\n"]
    for model in sorted({r["model"] for r in rows}):
        rs = [r for r in rows if r["model"] == model]
        parts += [f"\n## {model}\n", "### Outcomes by arm\n", arm_table(rs, arms),
                  "\n\n### Failure modes\n", failure_modes(rs, arms),
                  "\n\n### Paired tests (same brief, same seed)\n",
                  "- " + paired(rs, "extended", "contract"), "- " + paired(rs, "extended", "contract", "score"),
                  "- " + paired(rs, "extended", "output_retry"), "- " + paired(rs, "extended", "output_retry", "score"), "- " + paired(rs, "output_retry", "contract"),
                  "- " + paired(rs, "base", "extended"),
                  "\n### By brief family\n", split_table(rs, arms, "family", "family"),
                  "\n\n### By whether delivery size is a multiple of 8\n", split_table(rs, arms, "spec_div8", "size % 8 == 0"),
                  "\n\n### Cost of checking\n", loop_cost(rs, arms),
                  "\n\n### Contract-arm overhead\n",
                  f"verifier time per episode: mean {st.mean([r['check_ms'] for r in rs if r['arm']=='contract'] or [0]):.2f} ms; "
                  f"validate calls per episode: " + ", ".join(
                      f"{arm} {st.mean([r['validate_calls'] for r in rs if r['arm']==arm] or [0]):.2f}" for arm in arms[1:]),
                  "\n\n### Verifier vs actual outcome on shipped, executed LLM workflows (all arms; post-hoc)\n",
                  verifier_validity(rs)]
    if a.fig:
        figs = figures(rows, arms, a.fig)
        parts += ["\n\n## Figures\n"] + [f"![]({Path(f).relative_to(a.report.parent) if a.report.parent in Path(f).parents else f})" for f in figs]
    a.report.write_text("\n".join(parts) + "\n")
    print("\n".join(parts))


if __name__ == "__main__":
    main()
