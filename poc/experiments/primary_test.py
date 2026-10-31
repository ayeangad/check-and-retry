"""Pre-registered primary test (rule locked 2026-10-31, before results were computed).

For arm B vs `extended`: paired all-pass difference on brief x seed, with
  - a 95% CI from a cluster bootstrap over briefs (seeds of one brief are not independent), used for the rule;
  - a naive paired CI (episodes treated as independent), shown for comparison only;
  - an exact McNemar p-value on discordant pairs.
Verdict: HELPS if gain >= 5 pp and CI lower bound > 0; HARMS if CI upper bound < 0; else NOT SHOWN.

Usage: python poc/experiments/primary_test.py poc/results/e2_deepseek_long.jsonl
"""
from __future__ import annotations

import json
import math
import random
import sys
from collections import defaultdict

MIN_PP = 5.0
B = 10000


def mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def main(path: str) -> None:
    rows = [json.loads(l) for l in open(path) if l.strip()]
    res = {(r["brief_id"], r["seed"], r["arm"]): int(bool(r["all_pass"])) for r in rows}
    briefs = sorted({r["brief_id"] for r in rows})
    seeds = sorted({r["seed"] for r in rows})
    rng = random.Random(0)
    for arm in ("contract", "output_retry"):
        pairs = defaultdict(list)       # brief -> list of (b - a) per seed
        b_only = a_only = 0
        for br in briefs:
            for s in seeds:
                ka, kb = (br, s, "extended"), (br, s, arm)
                if ka in res and kb in res:
                    d = res[kb] - res[ka]
                    pairs[br].append(d)
                    b_only += d == 1
                    a_only += d == -1
        n = sum(len(v) for v in pairs.values())
        diffs = [d for v in pairs.values() for d in v]
        mean = 100 * sum(diffs) / n
        sd = math.sqrt(sum((d - sum(diffs) / n) ** 2 for d in diffs) / (n - 1))
        naive = (mean - 196 * sd / math.sqrt(n), mean + 196 * sd / math.sqrt(n))
        keys = list(pairs)
        boot = []
        for _ in range(B):
            samp = [pairs[rng.choice(keys)] for _ in keys]
            tot = sum(sum(v) for v in samp)
            cnt = sum(len(v) for v in samp)
            boot.append(100 * tot / cnt)
        boot.sort()
        lo, hi = boot[int(0.025 * B)], boot[int(0.975 * B) - 1]
        verdict = ("HELPS" if mean >= MIN_PP and lo > 0 else "HARMS" if hi < 0 else "NOT SHOWN")
        print(f"{arm} vs extended: n_pairs={n} (briefs={len(keys)})  diff={mean:+.1f} pp  "
              f"95% CI cluster-bootstrap [{lo:+.1f}, {hi:+.1f}]  naive [{naive[0]:+.1f}, {naive[1]:+.1f}]  "
              f"discordant: {arm} only={b_only}, extended only={a_only}  McNemar p={mcnemar(b_only, a_only):.2g}  "
              f"-> {verdict}")


if __name__ == "__main__":
    main(sys.argv[1])
