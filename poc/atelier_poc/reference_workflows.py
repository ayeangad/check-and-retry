"""Hand-built workflows: a correct reference solution per brief, plus the realistic mutations
used to measure the verifier's precision and recall (experiment E3).

Each mutation copies a failure mode that passes ComfyUI validation but breaks the brief:
generating directly at a non-multiple-of-8 size, resizing after the logo is pasted, sending the
logo through the VAE, img2img at denoise 1.0, and so on.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Callable

from PIL import Image

from .briefs import Brief

CKPT = "sdxl_base_1.0.safetensors"


def _gen_size(w: int, h: int, target_px: int = 1024 * 1024) -> tuple[int, int]:
    """A multiple-of-64 generation size near ~1MP with the delivery aspect ratio."""
    s = (target_px / (w * h)) ** 0.5
    return max(64, round(w * s / 64) * 64), max(64, round(h * s / 64) * 64)


def build_correct(b: Brief, input_dir: Path) -> dict:
    W, H = b.spec.width, b.spec.height
    g: dict = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": b.text[:200]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": "blurry, watermark, text"}},
    }
    gw, gh = _gen_size(W, H)
    if b.spec.reference:
        g["10"] = {"class_type": "LoadImage", "inputs": {"image": b.spec.reference.file}}
        g["11"] = {"class_type": "ImageScale", "inputs": {"image": ["10", 0], "upscale_method": "lanczos",
                                                         "width": gw, "height": gh, "crop": "center"}}
        g["4"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["11", 0], "vae": ["1", 2]}}
        denoise = 0.6
    else:
        g["4"] = {"class_type": "EmptyLatentImage", "inputs": {"width": gw, "height": gh, "batch_size": 1}}
        denoise = 1.0
    g["5"] = {"class_type": "KSampler", "inputs": {"model": ["1", 0], "seed": 42, "steps": 25, "cfg": 6.5,
                                                    "sampler_name": "dpmpp_2m", "scheduler": "karras",
                                                    "positive": ["2", 0], "negative": ["3", 0],
                                                    "latent_image": ["4", 0], "denoise": denoise}}
    g["6"] = {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}}
    g["7"] = {"class_type": "ImageScale", "inputs": {"image": ["6", 0], "upscale_method": "lanczos",
                                                    "width": W, "height": H, "crop": "center"}}
    last = "7"
    if b.spec.logo:
        with Image.open(input_dir / b.spec.logo.file) as im:
            lw, lh = im.size
        c = b.spec.logo.corner
        x = 32 if "left" in c else W - lw - 32
        y = 32 if "top" in c else H - lh - 32
        g["20"] = {"class_type": "LoadImage", "inputs": {"image": b.spec.logo.file}}
        g["21"] = {"class_type": "ImageCompositeMasked", "inputs": {"destination": ["7", 0], "source": ["20", 0],
                                                                   "x": max(0, x), "y": max(0, y),
                                                                   "resize_source": False}}
        last = "21"
    g["9"] = {"class_type": "SaveImage", "inputs": {"images": [last, 0], "filename_prefix": b.id}}
    return g


# ----------------------------------------------------------------------------- mutations
# Each returns (mutated_graph, claims_expected_to_break) or None if not applicable.

Mutation = Callable[[dict, Brief], tuple[dict, set[str]] | None]


def m_direct_size(g, b):
    """Generate directly at delivery size and drop the final resize (the /8 trap)."""
    W, H = b.spec.width, b.spec.height
    if W % 8 == 0 and H % 8 == 0 or b.spec.reference:
        return None
    g = copy.deepcopy(g)
    g["4"]["inputs"].update(width=W, height=H)
    nxt = "21" if b.spec.logo else "9"
    key = "destination" if b.spec.logo else "images"
    g[nxt]["inputs"][key] = ["6", 0]
    del g["7"]
    return g, {"delivery_size"}


def m_no_final_resize(g, b):
    g = copy.deepcopy(g)
    nxt, key = ("21", "destination") if b.spec.logo else ("9", "images")
    g[nxt]["inputs"][key] = ["6", 0]
    del g["7"]
    gw, gh = g["4"]["inputs"].get("width"), g["4"]["inputs"].get("height")
    if b.spec.reference:
        gw, gh = g["11"]["inputs"]["width"], g["11"]["inputs"]["height"]
    if (gw, gh) == (b.spec.width, b.spec.height):
        return None
    broken = {"delivery_size"}
    if b.spec.logo:
        lx, ly = g["21"]["inputs"]["x"], g["21"]["inputs"]["y"]
        # logo placement was computed for the delivery canvas; on the smaller canvas it may overflow / move
        broken |= {"logo_position"}
        with Image.open(Path(_INPUT_DIR[0]) / b.spec.logo.file) as im:
            lw, lh = im.size
        if lx + lw > gw or ly + lh > gh:
            broken |= {"logo_exact"}
    return g, broken


def m_resize_after_logo(g, b):
    if not b.spec.logo:
        return None
    g = copy.deepcopy(g)
    W, H = b.spec.width, b.spec.height
    g["21"]["inputs"]["destination"] = ["6", 0]
    g["7"]["inputs"]["image"] = ["21", 0]
    g["9"]["inputs"]["images"] = ["7", 0]
    gw, gh = _gen_size(W, H)
    lx = 32 if "left" in b.spec.logo.corner else gw - 300
    ly = 32 if "top" in b.spec.logo.corner else gh - 120
    g["21"]["inputs"].update(x=max(0, lx), y=max(0, ly))
    return g, {"logo_exact", "logo_position"}


def m_logo_through_vae(g, b):
    """Paste logo, then run an img2img 'harmonize' pass: the logo is regenerated."""
    if not b.spec.logo:
        return None
    g = copy.deepcopy(g)
    g["30"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["21", 0], "vae": ["1", 2]}}
    g["31"] = {"class_type": "KSampler", "inputs": {**g["5"]["inputs"], "latent_image": ["30", 0], "denoise": 0.3}}
    g["32"] = {"class_type": "VAEDecode", "inputs": {"samples": ["31", 0], "vae": ["1", 2]}}
    g["9"]["inputs"]["images"] = ["32", 0]
    broken = {"logo_exact", "logo_position"}
    if b.spec.width % 8 or b.spec.height % 8:
        broken.add("delivery_size")
    return g, broken


def m_resize_source(g, b):
    if not b.spec.logo:
        return None
    g = copy.deepcopy(g)
    g["21"]["inputs"]["resize_source"] = True
    return g, {"logo_exact", "logo_position"}


def m_wrong_corner(g, b):
    if not b.spec.logo:
        return None
    g = copy.deepcopy(g)
    W, H = b.spec.width, b.spec.height
    x, y = g["21"]["inputs"]["x"], g["21"]["inputs"]["y"]
    with Image.open(Path(_INPUT_DIR[0]) / b.spec.logo.file) as im:
        lw, lh = im.size
    g["21"]["inputs"].update(x=W - lw - x if "left" in b.spec.logo.corner else 32,
                             y=H - lh - y if "top" in b.spec.logo.corner else 32)
    return g, {"logo_position"}


def m_denoise_full(g, b):
    if not b.spec.reference:
        return None
    g = copy.deepcopy(g)
    g["5"]["inputs"]["denoise"] = 1.0
    return g, {"reference_composition"}


def m_t2i_ignores_ref(g, b):
    if not b.spec.reference:
        return None
    g = copy.deepcopy(g)
    gw, gh = g["11"]["inputs"]["width"], g["11"]["inputs"]["height"]
    g["4"] = {"class_type": "EmptyLatentImage", "inputs": {"width": gw, "height": gh, "batch_size": 1}}
    g["5"]["inputs"]["denoise"] = 1.0
    del g["10"], g["11"]
    return g, {"reference_composition"}


def m_batch2(g, b):
    g = copy.deepcopy(g)
    if b.spec.reference:
        return None
    g["4"]["inputs"]["batch_size"] = 2
    return g, {"single_output"}


def m_two_saves(g, b):
    g = copy.deepcopy(g)
    g["99"] = {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": b.id + "_raw"}}
    # Every delivered image must meet every claim; the extra raw decode is at generation size
    # and carries no logo.
    broken = {"single_output", "delivery_size"}
    if b.spec.logo:
        broken |= {"logo_exact", "logo_position"}
    return g, broken


def m_benign_reorder(g, b):
    """Control: semantically identical graph with renumbered ids; nothing should break."""
    remap = {k: str(int(k) + 100) for k in g}
    out = {}
    for k, n in g.items():
        n2 = copy.deepcopy(n)
        for name, v in n2["inputs"].items():
            if isinstance(v, list) and len(v) == 2 and str(v[0]) in remap:
                n2["inputs"][name] = [remap[str(v[0])], v[1]]
        out[remap[k]] = n2
    return out, set()


def m_benign_upscale_then_scale(g, b):
    """Control: 4x model upscale then exact ImageScale (common pro pattern); nothing should break."""
    g = copy.deepcopy(g)
    g["40"] = {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "4x-UltraSharp.pth"}}
    g["41"] = {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["40", 0], "image": ["6", 0]}}
    g["7"]["inputs"]["image"] = ["41", 0]
    return g, set()


MUTATIONS: dict[str, Mutation] = {
    "direct_size": m_direct_size, "no_final_resize": m_no_final_resize,
    "resize_after_logo": m_resize_after_logo, "logo_through_vae": m_logo_through_vae,
    "resize_source": m_resize_source, "wrong_corner": m_wrong_corner, "denoise_full": m_denoise_full,
    "t2i_ignores_ref": m_t2i_ignores_ref, "batch2": m_batch2, "two_saves": m_two_saves,
    "benign_reorder": m_benign_reorder, "benign_upscale_then_scale": m_benign_upscale_then_scale,
}

_INPUT_DIR: list[str] = ["poc/comfy_base/input"]


def set_input_dir(p: Path) -> None:
    _INPUT_DIR[0] = str(p)
