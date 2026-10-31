"""Outcome evaluator: scores the files a workflow ACTUALLY produced.

Deliberately independent of brief_contract.py. It never looks at the workflow graph, only at
the PNGs ComfyUI wrote and the brief's Spec, so a verifier that is wrong about the graph cannot
make its own arm look better.

Claims (each pass/fail):
  delivery_size          every output file is exactly spec.width × spec.height
  single_output          exactly spec.n_outputs files
  logo_exact             the supplied logo's pixels appear unaltered (±1/255, the PNG 8-bit round trip)
  logo_position          ...with its bbox inside the requested corner region
  reference_composition  output correlates with the reference layout (Pearson r ≥ 0.3 on a 16×16 RGB grid,
                         each channel mean-centred so a shared colour cast alone cannot pass)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.signal import fftconvolve

from .briefs import Spec

REF_R_THRESHOLD = 0.3   # set from oracle correct vs broken workflows (E3) before any arm was compared
GRID = 16


@dataclass
class Outcome:
    executed: bool
    claims: dict[str, bool] = field(default_factory=dict)
    details: dict[str, object] = field(default_factory=dict)

    @property
    def score(self) -> float:
        return sum(self.claims.values()) / len(self.claims) if self.claims else 0.0

    @property
    def all_pass(self) -> bool:
        return bool(self.claims) and all(self.claims.values())


def _load(p: Path) -> np.ndarray:
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)


def find_exact_patch(img: np.ndarray, patch: np.ndarray, tol: float = 1.0) -> tuple[int, int] | None:
    """Top-left (x, y) where `patch` appears in `img` with max abs error ≤ tol, else None.
    Candidate positions come from an FFT sum-of-squared-differences, then are verified exactly."""
    H, W, _ = img.shape
    h, w, _ = patch.shape
    if h > H or w > W:
        return None
    ssd = np.zeros((H - h + 1, W - w + 1), dtype=np.float64)
    for c in range(3):
        I, T = img[..., c].astype(np.float64), patch[..., c].astype(np.float64)
        ones = np.ones_like(T)
        ssd += (fftconvolve(I * I, ones, mode="valid") - 2 * fftconvolve(I, T[::-1, ::-1], mode="valid")
                + (T * T).sum())
    for flat in np.argsort(ssd, axis=None)[:5]:
        y, x = np.unravel_index(flat, ssd.shape)
        if np.abs(img[y:y + h, x:x + w] - patch).max() <= tol:
            return int(x), int(y)
    return None


def _in_corner(x: int, y: int, w: int, h: int, W: int, H: int, corner: str, frac: float) -> bool:
    mx, my = W * frac, H * frac
    left_ok, right_ok = x <= mx, (W - (x + w)) <= mx
    top_ok, bottom_ok = y <= my, (H - (y + h)) <= my
    return {"top-left": left_ok and top_ok, "top-right": right_ok and top_ok,
            "bottom-left": left_ok and bottom_ok, "bottom-right": right_ok and bottom_ok}[corner]


def _layout(img: np.ndarray, aspect: float) -> np.ndarray:
    """Center-crop to `aspect`, box-downsample to GRID×GRID RGB, centre each channel."""
    H, W, _ = img.shape
    if W / H > aspect:
        nw = int(H * aspect); x0 = (W - nw) // 2; img = img[:, x0:x0 + nw]
    else:
        nh = int(W / aspect); y0 = (H - nh) // 2; img = img[y0:y0 + nh]
    pil = Image.fromarray(img.astype(np.uint8)).resize((GRID, GRID), Image.BOX)
    a = np.asarray(pil, dtype=np.float32)
    return (a - a.mean(axis=(0, 1))).ravel()


def evaluate(spec: Spec, files: list[Path], input_dir: Path, executed: bool) -> Outcome:
    claims = {c: False for c in spec.claims()}
    if not executed or not files:
        return Outcome(executed=False, claims=claims, details={"n_files": 0})
    imgs = [_load(f) for f in files]
    sizes = [(im.shape[1], im.shape[0]) for im in imgs]
    det: dict[str, object] = {"n_files": len(files), "sizes": sizes}
    claims["single_output"] = len(files) == spec.n_outputs
    claims["delivery_size"] = all(s == (spec.width, spec.height) for s in sizes)
    # Content claims must hold for EVERY delivered image: a deliverable set in which one image
    # lacks the logo is not a correct deliverable.
    if spec.logo:
        logo = _load(input_dir / spec.logo.file)
        positions = [find_exact_patch(im, logo) for im in imgs]
        det["logo_pos"] = positions
        claims["logo_exact"] = all(p is not None for p in positions)
        claims["logo_position"] = claims["logo_exact"] and all(
            _in_corner(p[0], p[1], logo.shape[1], logo.shape[0], im.shape[1], im.shape[0],
                       spec.logo.corner, spec.logo.max_margin_frac) for p, im in zip(positions, imgs))
    if spec.reference:
        ref = _load(input_dir / spec.reference.file)
        rs = []
        for im in imgs:
            aspect = im.shape[1] / im.shape[0]
            a, b = _layout(im, aspect), _layout(ref, aspect)
            rs.append(float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else 0.0)
        det["reference_r"] = [round(r, 3) for r in rs]
        claims["reference_composition"] = all(r >= REF_R_THRESHOLD for r in rs)
    return Outcome(executed=True, claims=claims, details=det)
