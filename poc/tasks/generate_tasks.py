"""Generate the fixed mini-benchmark: briefs.jsonl + procedurally drawn input assets.

Deterministic (seeded). Assets are synthetic: no third-party images or brands are used.
Usage: python poc/tasks/generate_tasks.py --out poc/tasks --input-dir poc/comfy_base/input
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atelier_poc.briefs import Brief, LogoSpec, ReferenceSpec, Spec  # noqa: E402

# Real-world delivery sizes. Several are NOT multiples of 8 (1350, 628, 250, 90),
# which latent-space generation cannot hit directly.
SIZES = [(1080, 1080), (1080, 1350), (1080, 1920), (1920, 1080), (1200, 628), (1600, 900),
         (1200, 1200), (1280, 720), (1080, 1350), (1200, 628), (970, 250), (1456, 180)]
BRANDS = ["NORTHWIND", "KESTREL", "ALDER & CO", "MERIDIAN", "OSPREY", "LUMEN", "HALCYON", "TIDEWATER",
          "CORVID", "FENWICK", "MARLOW", "SABLE"]
SUBJECTS = [
    "a ceramic coffee cup on a sunlit cafe table", "a trail runner on a misty ridge at dawn",
    "a minimalist perfume bottle on wet black stone", "a bowl of ramen with steam rising",
    "a vintage bicycle leaning on a pastel wall", "a pair of headphones floating over a gradient",
    "a lighthouse on a rocky coast at golden hour", "a stack of pancakes with berries",
    "a sneaker mid-air over a city rooftop", "a glass of iced tea with lemon slices",
    "a desk plant beside a laptop in soft morning light", "a surfer silhouetted against a sunset",
]
STYLES = ["clean commercial photography", "flat vector illustration", "1990s cel-animation look",
          "soft watercolor", "bold risograph print", "cinematic film still"]
REF_SIZES = [(1024, 768), (800, 1000), (1536, 1024), (1000, 1000), (1200, 900), (768, 1152)]
CORNERS = ["top-left", "top-right", "bottom-left", "bottom-right"]


def draw_logo(path: Path, brand: str, rng: random.Random) -> tuple[int, int]:
    w, h = rng.choice([(220, 64), (260, 72), (180, 56), (240, 80)])
    img = Image.new("RGB", (w, h), tuple(rng.randrange(0, 60) for _ in range(3)))
    d = ImageDraw.Draw(img)
    fg = tuple(rng.randrange(150, 256) for _ in range(3))
    d.rectangle([4, 4, h - 4, h - 4], outline=fg, width=3)
    d.text((h + 6, h // 2 - 6), brand, fill=fg)
    # A fine high-entropy stripe makes the mark uniquely locatable and sensitive to any resampling.
    stripe = np.array(img)
    nr = np.random.default_rng(rng.randrange(2**31))
    stripe[h - 6:h - 2, h + 6:w - 6] = nr.integers(0, 256, (4, w - h - 12, 3), dtype=np.uint8)
    Image.fromarray(stripe).save(path)
    return w, h


def draw_reference(path: Path, size: tuple[int, int], rng: random.Random) -> None:
    w, h = size
    y = np.linspace(0, 1, h)[:, None, None]
    top, bot = np.array([rng.random() for _ in range(3)]), np.array([rng.random() for _ in range(3)])
    arr = (top * (1 - y) + bot * y) * np.ones((h, w, 3))
    img = Image.fromarray((arr * 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    for _ in range(rng.randint(3, 6)):  # large distinctive shapes = "composition"
        x0, y0 = rng.randrange(0, w * 3 // 4), rng.randrange(0, h * 3 // 4)
        x1, y1 = x0 + rng.randrange(w // 8, w // 2), y0 + rng.randrange(h // 8, h // 2)
        col = tuple(rng.randrange(0, 256) for _ in range(3))
        (d.ellipse if rng.random() < 0.5 else d.rectangle)([x0, y0, x1, y1], fill=col)
    img.save(path)


def make_briefs(input_dir: Path, seed: int = 7) -> list[Brief]:
    rng = random.Random(seed)
    input_dir.mkdir(parents=True, exist_ok=True)
    briefs: list[Brief] = []
    families = ["t2i_size", "t2i_logo", "edit_ref", "edit_ref_logo"]
    for i in range(24):
        fam = families[i % 4]
        w, h = SIZES[i % len(SIZES)]
        brand, subj, style = BRANDS[i % len(BRANDS)], SUBJECTS[i % len(SUBJECTS)], STYLES[i % len(STYLES)]
        tid = f"T{i:02d}_{fam}"
        inputs, logo, ref = {}, None, None
        parts = []
        if fam.startswith("edit_ref"):
            rfile = f"{tid}_reference.png"
            draw_reference(input_dir / rfile, REF_SIZES[i % len(REF_SIZES)], rng)
            inputs["reference"] = rfile
            ref = ReferenceSpec(rfile)
            parts.append(f"Restyle the supplied reference photo ({rfile}) as {style} for {brand}. "
                         f"Keep the exact composition of the reference: every shape stays where it is.")
        else:
            parts.append(f"Create a campaign image for {brand}: {subj}, rendered as {style}.")
        if fam.endswith("logo"):
            lfile = f"{tid}_logo.png"
            draw_logo(input_dir / lfile, brand, rng)
            corner = CORNERS[i % 4]
            inputs["logo"] = lfile
            logo = LogoSpec(lfile, corner)
            parts.append(f"Place the {brand} logo from {lfile} in the {corner} corner, reproduced exactly as "
                         f"supplied: same pixels and size, not redrawn, not rescaled.")
        parts.append(f"Deliver exactly one image at exactly {w}x{h} pixels. No other text or logos.")
        briefs.append(Brief(tid, fam, " ".join(parts), Spec(w, h, 1, logo, ref), inputs))
    return briefs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--input-dir", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    briefs = make_briefs(a.input_dir, a.seed)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "briefs.jsonl").write_text("\n".join(json.dumps(asdict(b)) for b in briefs) + "\n")
    print(f"wrote {len(briefs)} briefs; non-multiple-of-8 sizes: "
          f"{sum(1 for b in briefs if b.spec.width % 8 or b.spec.height % 8)}")


if __name__ == "__main__":
    main()
