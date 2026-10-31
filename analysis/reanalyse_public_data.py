"""Re-analysis of the aggregate data Hyde published inside the AtelierBench article exhibits.

Everything here is computed from `data/derived/atelier_data.json` (see extract_exhibit_data.py).
No per-task data is public, so every per-task quantity below is an *estimate* derived from
aggregates, and is labelled as such in the output.

Usage: python analysis/reanalyse_public_data.py data/derived/atelier_data.json data/derived/reanalysis.md
"""
from __future__ import annotations

import json
import math
import statistics as st
import sys
from pathlib import Path

H = ("base", "ext", "extp")
HN = {"base": "Base", "ext": "Extended", "extp": "Ext Plus"}
CAT = ("Required Scene Content", "Matches Reference", "Object & Scene Construction",
       "Camera, Lighting & Framing", "Look & Feel", "Text & Logo Readability",
       "Body & Figure Integrity", "Clean Edit", "Forbidden Content", "Delivery Format Specs")
CONTESTANT_JUDGES = {"gpt-6-astra", "claude-opus-5"}
N_TASKS = 156


class Data:
    def __init__(self, raw: dict):
        self.D = raw["D"]
        self.S = raw["SCORESETS"]
        self.G = raw["GDSETS"]
        self.models = [m["model"] for m in self.D["models"]]
        self._m = {m["model"]: m for m in self.D["models"]}

    def cell(self, model: str, h: str, method: str = "avg3", attempt: int | None = None) -> dict:
        """Return the (model, harness) record for a scoring method; cost/exec always from D."""
        base = self._m[model][h] if attempt is None else self._m[model][h]["attempts"][attempt]
        if method == "avg3":
            return base
        s = self.S[method]["models"][model][h]
        s = s if attempt is None else s["attempts"][attempt]
        return {**base, "scoreOk": s["scoreOk"], "scoreAll": s["scoreAll"]}

    def common(self, method: str) -> dict:
        return self.D["common"] if method == "avg3" else self.S[method]["common"]


def md_table(header: list[str], rows: list[list]) -> str:
    fmt = lambda v: f"{v:.3f}" if isinstance(v, float) else str(v)
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(fmt(v) for v in r) + " |" for r in rows]
    return "\n".join(lines)


# ---------------------------------------------------------------- analyses

PROSE_LIKE_FOR_LIKE = {  # Finding 2, like-for-like, Base -> Extended Plus, as printed in the article
    "gpt-6-astra": (4.1, 4.1), "claude-opus-5": (3.8, 3.8), "fable-5.1": (4.1, 3.8),
    "deepseek-v4.1-flash": (2.5, 3.4), "gpt-5.6-sol": (3.4, 3.9),
}


def prose_vs_methods(d: Data) -> str:
    rows, hits = [], {m: 0 for m in ("avg3", "low", "j2")}
    for model, (pb, pe) in PROSE_LIKE_FOR_LIKE.items():
        row = [model, f"{pb} → {pe}"]
        for meth in ("avg3", "j2", "low"):
            c = d.common(meth)[model]
            b, e = round(c["base"]["score"], 1), round(c["extp"]["score"], 1)
            ok = (b, e) == (pb, pe)
            hits[meth] += ok
            row.append(f"{c['base']['score']:.2f} → {c['extp']['score']:.2f} {'✓' if ok else '✗'}")
        rows.append(row)
    t = md_table(["model", "article prose", "avg3 (chart default)", "j2 (opus+astra)", "low (min of 3)"], rows)
    return t + f"\n\nRounded matches out of {len(PROSE_LIKE_FOR_LIKE)}: " + \
        ", ".join(f"{k}={v}" for k, v in hits.items())


def judge_disagreement(d: Data) -> tuple[str, dict]:
    rows, out = [], {}
    for i, c in enumerate(CAT):
        dl, dj = [], []
        for h in H:
            for m in d.models:
                a, lo, j = d.G["avg3"][h][m][i], d.G["low"][h][m][i], d.G["j2"][h][m][i]
                if a and a[1] >= 30:
                    dl.append(a[0] - lo[0])
                    dj.append(a[0] - j[0])
        out[c] = (st.mean(dl), 3 * st.mean(dj))
        # For 3 iid N(0, s^2) judge scores, E[mean - min] = 0.8463 s  (expected max of 3 std normals).
        rows.append([c, st.mean(dl), 3 * st.mean(dj), st.mean(dl) / 0.8463, len(dl)])
    t = md_table(["category", "avg3 − min-of-3", "gemini − mean(opus,astra)",
                  "implied per-judge spread s (if iid normal)", "cells"], rows)
    return t, out


def self_preference(d: Data) -> str:
    """Derived third judge g = 3*avg3 - 2*j2. Self-preference predicts the contestant judges (j2)
    rate *their own* models' outputs higher relative to g than they rate others', after
    controlling for output quality."""
    pts = []
    for m in d.models:
        for h in H:
            for a in (0, 1):
                c3 = d.cell(m, h, "avg3", a)
                if c3["executed"] < 30:
                    continue
                j2 = d.cell(m, h, "j2", a)["scoreOk"]
                g = 3 * c3["scoreOk"] - 2 * j2
                pts.append((m, h, a, c3["scoreOk"], j2 - g))
    others = [(q, gap) for m, _, _, q, gap in pts if m not in CONTESTANT_JUDGES]
    n = len(others)
    mx, my = st.mean(q for q, _ in others), st.mean(g for _, g in others)
    slope = sum((q - mx) * (g - my) for q, g in others) / sum((q - mx) ** 2 for q, _ in others)
    icpt = my - slope * mx
    rows = []
    for name in sorted({p[0] for p in pts}):
        res = [gap - (icpt + slope * q) for m, _, _, q, gap in pts if m == name]
        rows.append([name, "yes" if name in CONTESTANT_JUDGES else "no", st.mean(res), len(res)])
    resid_others = [gap - (icpt + slope * q) for q, gap in others]
    sd = st.stdev(resid_others)
    t = md_table(["contestant", "is also a judge", "mean residual of (j2 − g) after quality fit", "cells"], rows)
    return (f"Fit on non-judge contestants (n={n} cells): (j2 − g) = {icpt:.3f} + {slope:.3f}·quality; "
            f"residual SD = {sd:.3f}.\n\n" + t +
            "\n\nSelf-preference would show as a **positive** residual for judge-contestants.")


def run_noise(d: Data) -> tuple[str, float]:
    """Two estimators of per-task, run-to-run score SD (sigma) for the strong models whose two
    attempts cover ~the same task set:
      (a) attempt means: Var(m1 - m2) = 2 sigma^2 / n  ->  sigma = rms(d) * sqrt(n / 2)
      (b) best-of-2 inflation: E[max(x1,x2)] - E[x] = sigma / sqrt(pi) for normal noise."""
    strong = ("gpt-6-astra", "fable-5.1", "claude-opus-5")
    sq, ns = [], []
    for m in strong:
        for h in H:
            a0, a1 = d.cell(m, h, "avg3", 0), d.cell(m, h, "avg3", 1)
            sq.append((a0["scoreOk"] - a1["scoreOk"]) ** 2)
            ns.append((a0["executed"] + a1["executed"]) / 2)
    sigma_a = math.sqrt(st.mean(sq)) * math.sqrt(st.mean(ns) / 2)
    infl = [d.common("avg3")[m][h]["score"] - d.cell(m, h)["scoreOk"] for m in strong for h in H]
    sigma_b = st.mean(infl) * math.sqrt(math.pi)
    txt = (f"(a) from attempt-mean differences (9 cells, n≈{st.mean(ns):.0f}): σ ≈ {sigma_a:.2f}\n"
           f"(b) from best-of-2 inflation (common best-of-2 minus pooled mean = {st.mean(infl):.3f}): σ ≈ {sigma_b:.2f}\n"
           f"(b) is an upper bound: it also absorbs the small subset effect of dropping tasks that failed elsewhere.\n")
    return txt, sigma_a


def paired_significance(d: Data, sigma: float) -> str:
    """Like-for-like (common tasks, best of 2) Base -> Ext / ExtPlus differences against the noise
    floor implied by sigma. Task difficulty cancels in a paired comparison, so the SE is
    run noise only: SE = sigma_max * sqrt(2 / n), with sigma_max ≈ 0.83·sigma for max-of-2."""
    rows = []
    for m in d.models:
        c = d.common("avg3")[m]
        n = c["base"]["n"]
        se = 0.8256 * sigma * math.sqrt(2 / n)  # SD of max of 2 iid normals = 0.8256 sigma
        for h in ("ext", "extp"):
            diff = c[h]["score"] - c["base"]["score"]
            z = diff / se
            rows.append([m, f"Base→{HN[h]}", n, diff, se, f"{z:+.1f}", "yes" if abs(z) > 1.96 else "no"])
    return md_table(["model", "comparison", "n common", "Δ score", "SE (est.)", "z", "|z|>1.96"], rows)


def delivery_regression(d: Data) -> str:
    i = CAT.index("Delivery Format Specs")
    j = CAT.index("Text & Logo Readability")
    rows = []
    for m in d.models:
        g = [d.G["avg3"][h][m] for h in H]
        if g[0][i][1] < 30:
            base_d = f"{g[0][i][0]:.2f} (n={g[0][i][1]}, unreliable)"
        else:
            base_d = f"{g[0][i][0]:.2f}"
        ranks = []
        for h in H:
            order = sorted(range(10), key=lambda k: g[H.index(h)][k][0])
            ranks.append(order.index(i) + 1)
        rows.append([m, base_d, g[1][i][0], g[2][i][0], g[1][i][0] - g[0][i][0],
                     g[0][j][0], g[1][j][0], f"{ranks[1]}/10"])
    return md_table(["model", "Delivery Base", "Delivery Ext", "Delivery ExtP", "Δ Base→Ext",
                     "Text&Logo Base", "Text&Logo Ext", "Delivery rank on Ext (1=worst)"], rows)


def pareto_stability(d: Data) -> str:
    def frontier(method, attempt):
        pts = []
        for m in d.models:
            for h in H:
                c = d.cell(m, h, method, attempt)
                if c["executed"]:
                    pts.append((m, h, c["scoreOk"], c["costAll"] * N_TASKS / c["executed"]))
        return {(m, h) for m, h, q, cst in pts
                if not any(q2 >= q and c2 <= cst and (q2 > q or c2 < cst) for _, _, q2, c2 in pts)}

    rows = []
    for meth in ("avg3", "j2", "low"):
        for att in (None, 0, 1):
            f = frontier(meth, att)
            rows.append([meth, "pooled" if att is None else f"attempt {att + 1}",
                         ", ".join(sorted({m for m, _ in f})),
                         ", ".join(f"{m.split('-')[0]}·{h}" for m, h in sorted(f))])
    return md_table(["method", "data", "models on quality/all-in-cost frontier", "points"], rows) + \
        "\n\nArticle claim: \"only DeepSeek, Sol, Opus and Astra are ever the best value … and Fable never is.\""


def best_of_two_artifact(d: Data, sigma: float) -> str:
    """Like-for-like takes the better of two attempts. Max-of-2 inflates a task's score by
    E[max - mean] = sigma/sqrt(pi) only when BOTH attempts succeeded. Weak models succeed twice
    less often on Base than on Extended, so part of their reported Base->ExtPlus gain may be
    selection. Under independence, P(both | at least one) = p / (2 - p) for per-attempt success p."""
    rows = []
    k = sigma / math.sqrt(math.pi)
    for m in d.models:
        pb, pe = d.cell(m, "base")["rate"], d.cell(m, "extp")["rate"]
        ib, ie = k * pb / (2 - pb), k * pe / (2 - pe)
        gain = d.common("avg3")[m]["extp"]["score"] - d.common("avg3")[m]["base"]["score"]
        rows.append([m, pb, pe, ib, ie, ie - ib, gain])
    return md_table(["model", "exec rate Base", "exec rate ExtP", "est. inflation Base", "est. inflation ExtP",
                     "artifact in Δ", "reported like-for-like Δ"], rows)


def main(argv):
    raw = json.loads(Path(argv[1]).read_text())
    d = Data(raw)
    noise_txt, sigma = run_noise(d)
    dis_t, _ = judge_disagreement(d)
    parts = [
        "# Re-analysis of AtelierBench published aggregates\n",
        "Generated by `analysis/reanalyse_public_data.py` from data embedded in the article's exhibits. "
        "Per-task quantities are **estimates from aggregates**.\n",
        "## A. Which scoring method does the Finding 2 prose use?\n", prose_vs_methods(d),
        "\n\n## B. Judge disagreement by claim category\n", dis_t,
        "\n\n## C. Self-preference test (two judges are also contestants)\n", self_preference(d),
        "\n\n## D. Run-to-run noise (estimated)\n", noise_txt,
        "\n## E. Like-for-like harness effects vs the noise floor\n", paired_significance(d, sigma),
        "\n\n## F. Delivery-format regression under a validating harness\n", delivery_regression(d),
        "\n\n## G. Stability of the 'best value' (Pareto) set\n", pareto_stability(d),
        "\n\n## H. Best-of-2 selection artifact in like-for-like harness gains (estimate)\n",
        best_of_two_artifact(d, sigma), "\n",
    ]
    Path(argv[2]).write_text("\n".join(parts))
    print("\n".join(parts))


if __name__ == "__main__":
    main(sys.argv)
