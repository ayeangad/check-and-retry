"""Generate the long-brief set: Exhibit-1-style professional briefs.

Why: AtelierBench briefs are long (Exhibit 1 has 19 claims, mostly subjective), with the objective
delivery spec buried among style, lighting and composition requirements. Hyde's second hypothesis
for the harness regression is that "a longer loop gives more chances to lose track of exact
requirements such as size and wording". Short briefs understate that risk, so this set makes the
objective specs a small part of a long brief, as in real client work.

Contents:
  * X00_exhibit1: Hyde's own illustrative Exhibit 1 brief, verbatim, with synthetic stand-ins for
    the dancer photo and the SILVERSIDE logo (no third-party image is used).
  * 72 generated briefs, 18 per family (t2i_size, t2i_logo, edit_ref, edit_ref_logo).
Delivery sizes are standard published platform formats (labels below); several are not multiples of 8.

Usage: python poc/tasks/generate_long_tasks.py --out poc/tasks_long --input-dir poc/comfy_base/input
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
from tasks.generate_tasks import draw_logo, draw_reference  # noqa: E402

# (width, height, label): commonly published platform/ad-unit formats.
FORMATS = [
    (1080, 1080, "Instagram/Facebook square feed post"), (1080, 1350, "Instagram/Facebook 4:5 portrait feed post"),
    (1080, 1920, "Instagram/TikTok 9:16 story"), (1200, 627, "LinkedIn single-image ad"),
    (1200, 628, "Facebook link ad"), (1600, 900, "X/Twitter 16:9 in-stream image"),
    (1280, 720, "YouTube thumbnail"), (1000, 1500, "Pinterest 2:3 standard pin"),
    (1920, 1080, "16:9 digital out-of-home screen"), (970, 250, "IAB billboard ad unit"),
    (300, 600, "IAB half-page ad unit"), (728, 90, "IAB leaderboard ad unit"),
    (300, 250, "IAB medium rectangle ad unit"), (1200, 1500, "4:5 print-ready social key visual"),
]
BRANDS = ["Northwind Coffee", "Kestrel Outdoor", "Alder & Co", "Meridian Skincare", "Osprey Cycles", "Lumen Audio",
          "Halcyon Hotels", "Tidewater Seafood", "Corvid Studio", "Fenwick Tea", "Marlow Denim", "Sable Fragrance",
          "Juniper Bakery", "Atlas Running", "Cobalt Bank", "Wren Ceramics", "Quill Stationery", "Basalt Watches"]
SUBJECTS = [
    ("a ceramic pour-over coffee set on a marble counter", ["steam curls rising from the cup", "a scatter of roasted beans"]),
    ("a trail runner cresting a misty ridge at dawn", ["breath visible in the cold air", "pine trees falling away below"]),
    ("a frosted glass perfume bottle on wet black slate", ["a single drop running down the glass", "soft reflections in the slate"]),
    ("a steaming bowl of tonkotsu ramen with a soft egg", ["chopsticks resting on the rim", "spring onions scattered on top"]),
    ("a vintage steel road bike leaning on a pastel wall", ["a canvas bag hanging from the bars", "a long afternoon shadow"]),
    ("over-ear headphones floating above a gradient backdrop", ["a faint motion trail", "the cable curling gently below"]),
    ("a lighthouse on a rocky headland at golden hour", ["gulls circling the lamp", "spray breaking on the rocks"]),
    ("a stack of buttermilk pancakes with fresh berries", ["maple syrup mid-pour", "a dusting of icing sugar"]),
    ("a sneaker caught mid-air above a city rooftop", ["laces lifting in the wind", "the skyline soft in the background"]),
    ("a tall glass of iced tea with lemon wheels", ["condensation beading on the glass", "mint leaves at the rim"]),
    ("a hotel suite balcony overlooking a calm sea", ["white linen curtains billowing", "a breakfast tray on a small table"]),
    ("a hand-thrown ceramic vase on an oak shelf", ["a single dried stem", "morning light raking across the glaze"]),
]
STYLES = [
    ("clean commercial product photography", "crisp focus, true-to-life color, no visible retouching artifacts"),
    ("flat vector illustration", "solid color fills, no gradients or texture, consistent 2px line weight"),
    ("traditional 1990s cel animation", "clean ink outlines, flat cel shading with one shadow and one highlight tone"),
    ("loose watercolor illustration", "visible paper texture and soft bleeding edges, no hard digital lines"),
    ("bold two-color risograph print", "visible grain and slight misregistration, limited to two inks"),
    ("cinematic film still", "anamorphic framing, gentle film grain, shallow depth of field"),
]
MOODS = ["calm and premium", "energetic and optimistic", "warm and nostalgic", "minimal and confident",
         "playful and bright", "quiet and luxurious"]
LIGHTS = ["soft window light from the left with long gentle shadows", "low golden-hour sun from behind the subject",
          "overcast diffuse daylight with no hard shadows", "a single warm key light and deep falloff",
          "bright high-key studio light on a pale backdrop", "blue-hour ambient light with warm practical highlights"]
PALETTES = ["a muted sage, cream and terracotta palette", "deep navy with a single coral accent",
            "warm neutrals with brass highlights", "a teal-to-peach gradient sky palette",
            "monochrome charcoal with one red accent", "pastel mint, butter yellow and lilac"]
TAGLINES = ["Made slowly.", "Go further.", "Every detail, considered.", "Taste the morning.", "Built to last.",
            "Quiet luxury.", "Find your pace.", "Small batch. Big character."]
CORNERS = ["top-left", "top-right", "bottom-left", "bottom-right"]
CORNER_WORDS = {"top-left": "upper-left", "top-right": "upper-right", "bottom-left": "lower-left", "bottom-right": "lower-right"}

EXHIBIT1 = ("Redraw this photo of the dancer in the windswept coastal field as a hand-painted anime key visual for "
            "SILVERSIDE, a creative design studio, to open its 2026 studio reel. Keep the exact composition of the input: "
            "her pose, with the right arm arched over her head, the left arm extended down and back, and a wide lunge with "
            "both bare feet planted in the grass; her position just right of centre; the wind-bent cypress behind her; the "
            "small white cottage with its terracotta roof; and the sea horizon at the same height. Render everything in a "
            "traditional 1990s cel-animation look: clean, consistent ink outlines, flat cel shading with one shadow tone and "
            "one highlight per surface, and painterly watercolor backgrounds with visible brush texture. No 3D-render or "
            "photographic textures anywhere. Keep her outfit to the same pieces, a white long-sleeve cropped wrap top and "
            "high-waisted wide-leg white trousers, but add motion: the sleeves and trouser hems ripple in the same wind "
            "direction as the tree (blowing left to right), and her dark curly hair streams with them. Shift the light to "
            "golden hour: a low warm sun from the left, long shadows falling to the right across the grass, and a "
            "teal-to-peach gradient sky. Add three or four small white petals drifting on the wind. Place the SILVERSIDE "
            "logo from Input 2 in the upper-left sky, reproduced exactly as supplied: same letterforms, proportions and "
            "silver-to-black gradient, not redrawn in the anime style. Beneath it, add “Studio Reel 2026” in small "
            "caps; keep all text clear of the dancer and the tree. Deliver at 16:9, 1920×1080. No other text, logos or "
            "watermarks.")


def draw_silverside_logo(path: Path) -> None:
    """Synthetic stand-in for the SILVERSIDE wordmark: silver-to-black gradient plate with lettering."""
    w, h = 300, 70
    grad = np.linspace(200, 20, w)[None, :, None] * np.ones((h, w, 3))
    img = Image.fromarray(grad.astype(np.uint8))
    d = ImageDraw.Draw(img)
    d.text((18, 26), "S I L V E R S I D E", fill=(250, 250, 250))
    arr = np.array(img)
    arr[h - 6:h - 3, 18:w - 18] = np.random.default_rng(11).integers(0, 256, (3, w - 36, 3), dtype=np.uint8)
    Image.fromarray(arr).save(path)


def long_text(rng: random.Random, fam: str, brand: str, fmt, ref_file, logo_file, corner) -> str:
    w, h, label = fmt
    subj, details = rng.choice(SUBJECTS)
    style, style_rules = rng.choice(STYLES)
    parts = []
    if ref_file:
        parts.append(f"Restyle the supplied reference photo ({ref_file}) as a {style} key visual for {brand}'s new "
                     f"campaign. Keep the exact composition of the reference: every shape, its position and its scale "
                     f"must stay where it is, and the horizon must sit at the same height.")
    else:
        parts.append(f"Create a {style} key visual for {brand}'s new campaign showing {subj}.")
    parts.append(f"Include {details[0]} and {details[1]}.")
    parts.append(f"Render it as {style}: {style_rules}.")
    parts.append(f"The mood is {rng.choice(MOODS)}. Use {rng.choice(LIGHTS)}, in {rng.choice(PALETTES)}.")
    parts.append("Keep the subject clearly readable at thumbnail size and leave calm negative space around it.")
    if logo_file:
        parts.append(f"Place the {brand} logo from {logo_file} in the {CORNER_WORDS[corner]} corner, reproduced exactly "
                     f"as supplied: same pixels, same size and proportions, not redrawn, recolored or restyled.")
        if rng.random() < 0.5:
            parts.append(f"Do not add any tagline; the campaign line “{rng.choice(TAGLINES)}” is set later by "
                         f"the media team.")
    parts.append("No watermarks, no extra logos, no borders or frames, no 3D-render look.")
    parts.append(f"Deliver exactly one image for the {label}, at exactly {w}×{h} pixels.")
    return " ".join(parts)


def make(input_dir: Path, seed: int = 23, n_per_family: int = 18) -> list[Brief]:
    rng = random.Random(seed)
    input_dir.mkdir(parents=True, exist_ok=True)
    out: list[Brief] = []
    # Exhibit 1 (verbatim brief, synthetic stand-in inputs)
    ref, logo = "X00_exhibit1_input1_photo.png", "X00_exhibit1_input2_logo.png"
    draw_reference(input_dir / ref, (1536, 1024), rng)
    draw_silverside_logo(input_dir / logo)
    out.append(Brief("X00_exhibit1", "edit_ref_logo",
                     EXHIBIT1.replace("this photo", f"this photo (Input 1: {ref})").replace("from Input 2", f"from Input 2 ({logo})"),
                     Spec(1920, 1080, 1, LogoSpec(logo, "top-left"), ReferenceSpec(ref)), {"reference": ref, "logo": logo}))
    fams = ["t2i_size", "t2i_logo", "edit_ref", "edit_ref_logo"]
    i = 0
    for k in range(n_per_family):
        for fam in fams:
            fmt = FORMATS[(k + fams.index(fam) * 3) % len(FORMATS)]
            brand = BRANDS[(i * 7) % len(BRANDS)]
            tid = f"L{i:02d}_{fam}"
            ref_file = logo_file = corner = None
            inputs = {}
            if fam.startswith("edit_ref"):
                ref_file = f"{tid}_reference.png"
                draw_reference(input_dir / ref_file, rng.choice([(1024, 768), (800, 1000), (1536, 1024), (1000, 1000),
                                                                  (1200, 900), (768, 1152)]), rng)
                inputs["reference"] = ref_file
            if fam.endswith("logo"):
                logo_file = f"{tid}_logo.png"
                lw, lh = draw_logo(input_dir / logo_file, brand.upper(), rng)
                corner = CORNERS[i % 4]
                # small ad units cannot fit a large logo: keep every logo strictly smaller than the canvas
                if lw >= fmt[0] or lh >= fmt[1] // 2:
                    fmt = (1080, 1080, "Instagram/Facebook square feed post")
                inputs["logo"] = logo_file
            text = long_text(rng, fam, brand, fmt, ref_file, logo_file, corner)
            spec = Spec(fmt[0], fmt[1], 1, LogoSpec(logo_file, corner) if logo_file else None,
                        ReferenceSpec(ref_file) if ref_file else None)
            out.append(Brief(tid, fam, text, spec, inputs))
            i += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--input-dir", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=23)
    a = ap.parse_args()
    briefs = make(a.input_dir, a.seed)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "briefs.jsonl").write_text("\n".join(json.dumps(asdict(b)) for b in briefs) + "\n")
    words = [len(b.text.split()) for b in briefs]
    print(f"wrote {len(briefs)} briefs; words per brief min/median/max = {min(words)}/{sorted(words)[len(words)//2]}/{max(words)}; "
          f"non-multiple-of-8 sizes: {sum(1 for b in briefs if b.spec.width % 8 or b.spec.height % 8)}")


if __name__ == "__main__":
    main()
