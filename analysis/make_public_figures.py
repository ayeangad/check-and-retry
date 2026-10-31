"""Figures for the re-analysis of Hyde's published AtelierBench aggregates.

Usage: python analysis/make_public_figures.py data/derived/atelier_data.json deliverables/figs
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Reference palette, categorical slots 1–3 (validated all-pairs, light mode) + text/grid tokens.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
TEXT, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
H = [("base", "Base"), ("ext", "Extended"), ("extp", "Extended Plus")]
CAT = ["Required Scene Content", "Matches Reference", "Object & Scene Construction", "Camera, Lighting & Framing",
       "Look & Feel", "Text & Logo Readability", "Body & Figure Integrity", "Clean Edit", "Forbidden Content",
       "Delivery Format Specs"]
DELIV = 9


def _style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=8, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def delivery_dotplot(raw: dict, out: Path) -> None:
    G = raw["GDSETS"]["avg3"]
    models = [m["model"] for m in raw["D"]["models"]]
    fig, ax = plt.subplots(figsize=(7.2, 3.8), facecolor=SURFACE)
    _style(ax)
    for yi, m in enumerate(models[::-1]):
        vals = [G[h][m][DELIV] for h, _ in H]
        ok = [v[1] >= 30 for v in vals]
        xs = [v[0] for v, o in zip(vals, ok) if o]
        if len(xs) > 1:
            ax.plot([min(xs), max(xs)], [yi, yi], color=GRID, linewidth=2, zorder=1)
        for k, ((h, lab), v, o) in enumerate(zip(H, vals, ok)):
            if o:
                ax.scatter(v[0], yi, s=46, color=SERIES[k], edgecolor=SURFACE, linewidth=2, zorder=3,
                           label=lab if yi == 0 else None)
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels(models[::-1], color=TEXT, fontsize=8)
    ax.set_xlim(2.5, 5.0)
    ax.set_xlabel("Delivery Format Specs score (0–5, 3-judge average)", color=MUTED, fontsize=8)
    ax.set_title("A validating harness lowers delivery-format scores for 3 of 8 models",
                 loc="left", color=TEXT, fontsize=10)
    ax.legend(loc="lower left", fontsize=8, frameon=False, ncol=3, bbox_to_anchor=(-0.01, 0.99),
              handletextpad=0.3, columnspacing=1.2)
    ax.set_title(ax.get_title(loc="left"), loc="left", color=TEXT, fontsize=10, pad=22)
    fig.text(0.01, 0.01, "Source: data embedded in hyde.ai/blog/atelier exhibits. Cells with n<30 claims omitted.",
             color=MUTED, fontsize=6.5)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out, dpi=170, facecolor=SURFACE)
    plt.close(fig)


def judge_spread(raw: dict, out: Path) -> None:
    import statistics as st
    G = raw["GDSETS"]
    vals = []
    for i, c in enumerate(CAT):
        d = [G["avg3"][h][m][i][0] - G["low"][h][m][i][0] for h, _ in H for m in G["avg3"][h]
             if G["avg3"][h][m][i] and G["avg3"][h][m][i][1] >= 30]
        vals.append((c, st.mean(d)))
    vals.sort(key=lambda x: x[1])
    fig, ax = plt.subplots(figsize=(7.2, 3.6), facecolor=SURFACE)
    _style(ax)
    ys = range(len(vals))
    ax.barh(ys, [v for _, v in vals], height=0.6, color=SERIES[0], edgecolor=SURFACE, linewidth=2)
    for y, (_, v) in zip(ys, vals):
        ax.text(v + 0.012, y, f"{v:.2f}", va="center", color=TEXT, fontsize=7.5)
    ax.set_yticks(list(ys))
    ax.set_yticklabels([c for c, _ in vals], color=TEXT, fontsize=8)
    ax.set_xlim(0, 0.85)
    ax.set_xlabel("mean of (3-judge average − lowest judge), per claim, 0–5 scale", color=MUTED, fontsize=8)
    ax.set_title("Judges agree on delivery format; elsewhere they differ by 0.4–0.7",
                 loc="left", color=TEXT, fontsize=10)
    fig.text(0.01, 0.01, "Source: hyde.ai/blog/atelier exhibit data; judges gpt-6-astra, claude-opus-5, gemini-3.1-pro.",
             color=MUTED, fontsize=6.5)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out, dpi=170, facecolor=SURFACE)
    plt.close(fig)


def main(argv):
    raw = json.loads(Path(argv[1]).read_text())
    out = Path(argv[2]); out.mkdir(parents=True, exist_ok=True)
    delivery_dotplot(raw, out / "delivery_regression.png")
    judge_spread(raw, out / "judge_spread.png")
    print("wrote", sorted(p.name for p in out.glob("*.png")))


if __name__ == "__main__":
    main(sys.argv)
