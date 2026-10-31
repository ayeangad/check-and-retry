"""Experiment D (D13): per-arm outcomes and paired comparisons on one JSONL file.

Pairs are brief x seed (one seed here, so pairs = briefs). The CI on a paired difference is a
bootstrap over briefs; p is an exact McNemar test on discordant pairs.

Usage: python poc/experiments/analyze_d.py poc/results/d_blind.jsonl extended:contract output_retry_rich:contract ...
"""
from __future__ import annotations

import json
import math
import random
import sys
from collections import defaultdict

CLAIMS = ["delivery_size", "single_output", "logo_exact", "logo_position", "reference_composition"]


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0, c - h), min(1, c + h)


def mcnemar(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def main(path, comparisons):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    arms = list(dict.fromkeys(r["arm"] for r in rows))
    print(f"## {path}  ({len(rows)} episodes, {len({r['brief_id'] for r in rows})} briefs)\n")
    print("| arm | n | all-pass (95% CI) | " + " | ".join(CLAIMS) + " | generations/ep | brief rejections/ep | tokens/ep |")
    print("|" + "---|" * (6 + len(CLAIMS)))
    for a in arms:
        rs = [r for r in rows if r["arm"] == a]
        n, k = len(rs), sum(r["all_pass"] for r in rs)
        lo, hi = wilson(k, n)
        cl = [f"{sum(r['claims'][c] for r in rs if c in r['claims'])}/{sum(c in r['claims'] for r in rs)}"
              if any(c in r["claims"] for r in rs) else "—" for c in CLAIMS]
        # same definition as analyze_e2.loop_cost: in-loop executions, plus the delivery run if none happened in-loop
        gen = sum(r["executions"] + (1 if r["executed"] and not r["executions"] else 0) for r in rs) / n
        tok = sum(r["usage"]["prompt_tokens"] + r["usage"]["completion_tokens"] for r in rs) / n
        print(f"| {a} | {n} | {k}/{n} = {k/n:.0%} ({lo:.0%}–{hi:.0%}) | " + " | ".join(cl) +
              f" | {gen:.2f} | {sum(r['brief_rejections'] for r in rs)/n:.2f} | {tok:,.0f} |")
    res = {(r["brief_id"], r["seed"], r["arm"]): int(bool(r["all_pass"])) for r in rows}
    rng = random.Random(0)
    print()
    for comp in comparisons:
        a, b = comp.split(":")
        by = defaultdict(list)
        nb = na = 0
        for (br, s, arm), v in res.items():
            if arm == b and (br, s, a) in res:
                d = v - res[(br, s, a)]
                by[br].append(d)
                nb += d == 1
                na += d == -1
        keys = list(by)
        n = sum(len(v) for v in by.values())
        mean = 100 * sum(sum(v) for v in by.values()) / n
        boot = []
        for _ in range(10000):
            samp = [by[rng.choice(keys)] for _ in keys]
            boot.append(100 * sum(map(sum, samp)) / sum(map(len, samp)))
        boot.sort()
        print(f"- {b} − {a}: {mean:+.1f} pp, 95% CI [{boot[250]:+.1f}, {boot[9749]:+.1f}], n={n} pairs; "
              f"{b} only {nb}, {a} only {na}; McNemar p={mcnemar(nb, na):.2g}")
    print()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
