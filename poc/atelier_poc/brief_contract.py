"""Brief-contract verifier: static, pre-execution checks that a ComfyUI workflow satisfies the
objectively checkable claims in a design brief.

ComfyUI's validator answers "will this graph run?" (node exists, inputs typed and in range,
edges wired). This module answers a different question: "if it runs, will the output meet
the brief's delivery spec?" It does that by abstract interpretation over the graph. Every
IMAGE/LATENT edge carries an abstract value:

    Img(w, h, batch, logo, ref)    Lat(w, h, batch, ref)     (sizes in PIXELS for both)

`logo` tracks whether the supplied logo's pixels survive untouched, and where they sit. `ref`
tracks whether the reference image's layout reaches the output. Transfer functions mirror
ComfyUI's own implementations, cited inline. A node we have no model for yields UNKNOWN; any
check depending on it abstains ("unverified") rather than raising a false alarm.

Output: a list of Violations with node-level causes and a concrete fix, written so an LLM agent
can act on them inside its tool loop. The checks are deterministic, make no model calls, and
take well under a millisecond on these graphs.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from PIL import Image

from .briefs import Spec

# ----------------------------------------------------------------------------- abstract values

EXACT, ALTERED = "exact", "altered"


@dataclass(frozen=True)
class LogoState:
    status: str                 # EXACT | ALTERED
    x: int = 0                  # top-left in the current canvas (EXACT only)
    y: int = 0
    w: int = 0
    h: int = 0
    why: str = ""               # ALTERED: which node broke it and how
    is_canvas: bool = False     # True while the value *is* the bare logo image (not yet composited)


@dataclass(frozen=True)
class Img:
    w: int
    h: int
    batch: int = 1
    logo: LogoState | None = None
    ref: str | None = None      # None | "raw" (reference pixels) | "kept" | "destroyed:<why>"


@dataclass(frozen=True)
class Lat:
    w: int                      # pixel-space width this latent decodes to
    h: int
    batch: int = 1
    ref: str | None = None
    logo: LogoState | None = None


class Unknown:
    def __init__(self, why: str):
        self.why = why


Value = Img | Lat | Unknown | None


@dataclass
class Violation:
    claim: str                  # delivery_size | single_output | logo_exact | logo_position | reference_composition | inputs
    node: str | None
    message: str
    fix: str

    def render(self) -> str:
        loc = f"[node {self.node}] " if self.node else ""
        return f"- {self.claim}: {loc}{self.message}\n  fix: {self.fix}"


@dataclass
class ContractReport:
    violations: list[Violation] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    predicted_outputs: list[tuple[str, int, int, int]] = field(default_factory=list)  # (node, w, h, batch)

    @property
    def ok(self) -> bool:
        return not self.violations

    def verdicts(self, spec: Spec) -> dict[str, bool | None]:
        """Per-claim prediction: True=pass, False=violation, None=could not verify."""
        bad = {v.claim for v in self.violations}
        unv = {u.split(":", 1)[0] for u in self.unverified}
        return {c: (False if c in bad else None if c in unv else True) for c in spec.claims()}

    def render(self) -> str:
        if self.ok and not self.unverified:
            return "Brief contract: all checkable requirements satisfied."
        out = []
        if self.violations:
            out.append(f"Brief contract: {len(self.violations)} requirement(s) violated:")
            out += [v.render() for v in self.violations]
        if self.unverified:
            out.append("Could not verify: " + "; ".join(self.unverified))
        return "\n".join(out)


# ----------------------------------------------------------------------------- interpreter

RESAMPLERS = {"ImageScale", "ImageScaleBy", "ImageScaleToTotalPixels", "ImageUpscaleWithModel"}


class _Interp:
    def __init__(self, graph: dict, spec: Spec, input_dir: Path):
        self.g, self.spec, self.input_dir = graph, spec, input_dir
        self.memo: dict[tuple[str, int], Value] = {}
        self.violations: list[Violation] = []
        self.unverified: list[str] = []
        self._visiting: set[str] = set()

    # -- helpers
    def inp(self, nid: str, name: str, default=None):
        return self.g[nid].get("inputs", {}).get(name, default)

    def val(self, nid: str, name: str) -> Value:
        ref = self.inp(nid, name)
        if isinstance(ref, list) and len(ref) == 2:
            return self.out(str(ref[0]), int(ref[1]))
        return None

    def out(self, nid: str, idx: int = 0) -> Value:
        key = (nid, idx)
        if key in self.memo:
            return self.memo[key]
        if nid not in self.g or nid in self._visiting:
            return Unknown(f"dangling or cyclic reference to node {nid}")
        self._visiting.add(nid)
        ct = self.g[nid].get("class_type", "?")
        fn = TRANSFER.get(ct)
        try:
            v = fn(self, nid, idx) if fn else Unknown(f"no model for {ct} (node {nid})")
        except (TypeError, ValueError, KeyError, ZeroDivisionError) as e:
            v = Unknown(f"{ct} (node {nid}) has malformed inputs: {e}")
        except RecursionError:
            v = Unknown(f"graph too deep to analyse at node {nid}")
        self._visiting.discard(nid)
        self.memo[key] = v
        return v

    def warm(self) -> None:
        """Evaluate nodes in dependency order (iteratively) so that the recursive `out` calls made
        later always hit the memo. Keeps recursion depth O(1) on very deep graphs."""
        order, seen, stack = [], set(), [(n, False) for n in self.g]
        while stack:
            n, done = stack.pop()
            if done:
                order.append(n)
                continue
            if n in seen or not isinstance(self.g.get(n), dict):
                continue
            seen.add(n)
            stack.append((n, True))
            for v in (self.g[n].get("inputs") or {}).values():
                if isinstance(v, list) and len(v) == 2 and str(v[0]) in self.g and str(v[0]) not in seen:
                    stack.append((str(v[0]), False))
        for n in order:
            if self.g[n].get("class_type") in TRANSFER:
                self.out(n, 0)

    def image_file_size(self, fname: str) -> tuple[int, int] | None:
        p = self.input_dir / str(fname)
        if not p.is_file():
            return None
        with Image.open(p) as im:
            return im.size


# ----------------------------------------------------------------------------- transfer functions
# Each returns the abstract value of output slot `idx` of node `nid`.

def _int(x) -> int:
    return int(x)


def t_load_image(I: _Interp, nid: str, idx: int) -> Value:
    fname = I.inp(nid, "image")
    if idx == 1:
        return Unknown("mask from LoadImage")
    sz = I.image_file_size(fname)
    if sz is None:
        return Unknown(f"input file {fname!r} not found")
    w, h = sz
    spec = I.spec
    logo = LogoState(EXACT, 0, 0, w, h, is_canvas=True) if spec.logo and fname == spec.logo.file else None
    ref = "raw" if spec.reference and fname == spec.reference.file else None
    return Img(w, h, 1, logo, ref)


def t_empty_latent(I, nid, idx):
    w, h, b = _int(I.inp(nid, "width")), _int(I.inp(nid, "height")), _int(I.inp(nid, "batch_size", 1))
    return Lat((w // 8) * 8, (h // 8) * 8, b)          # nodes.py EmptyLatentImage: torch.zeros(.., h // 8, w // 8)


def t_empty_image(I, nid, idx):
    return Img(_int(I.inp(nid, "width")), _int(I.inp(nid, "height")), _int(I.inp(nid, "batch_size", 1)))


def _logo_destroyed(v: Img | Lat, why: str) -> LogoState | None:
    if v.logo is None:
        return None
    return LogoState(ALTERED, why=why)


def t_vae_encode(I, nid, idx):
    v = I.val(nid, "pixels")
    if not isinstance(v, Img):
        return v if isinstance(v, Unknown) else Unknown(f"VAEEncode {nid} has no pixels")
    w8, h8 = (v.w // 8) * 8, (v.h // 8) * 8          # VAE encode drops the non-multiple-of-8 remainder
    logo = _logo_destroyed(v, f"VAEEncode (node {nid}) sends the logo through the VAE, so its pixels are re-generated")
    return Lat(w8, h8, v.batch, v.ref, logo)


def t_ksampler(I, nid, idx):
    v = I.val(nid, "latent_image")
    if not isinstance(v, Lat):
        return v if isinstance(v, Unknown) else Unknown(f"KSampler {nid} has no latent")
    denoise = float(I.inp(nid, "denoise", 1.0))
    if I.g[nid]["class_type"] == "KSamplerAdvanced":
        add_noise = I.inp(nid, "add_noise", "enable") == "enable"
        start = int(I.inp(nid, "start_at_step", 0))
        denoise = 1.0 if (add_noise and start == 0) else 0.6   # partial schedule ≈ img2img
    ref = v.ref
    if ref in ("raw", "kept"):
        ref = "kept" if denoise < 1.0 else f"destroyed:KSampler node {nid} has denoise={denoise:g} (1.0 discards the input latent)"
    logo = _logo_destroyed(v, f"KSampler (node {nid}) re-generates the logo") if v.logo else None
    return replace(v, ref=ref, logo=logo)


def t_vae_decode(I, nid, idx):
    v = I.val(nid, "samples")
    if not isinstance(v, Lat):
        return v if isinstance(v, Unknown) else Unknown(f"VAEDecode {nid} has no latent")
    return Img(v.w, v.h, v.batch, v.logo, v.ref)


def t_latent_upscale(I, nid, idx):
    v = I.val(nid, "samples")
    if not isinstance(v, Lat):
        return v if isinstance(v, Unknown) else Unknown("LatentUpscale input")
    w, h = _int(I.inp(nid, "width")), _int(I.inp(nid, "height"))
    if w == 0 and h == 0:
        return v
    if w == 0:
        h = max(64, h); w = max(64, round(v.w * h / v.h))
    elif h == 0:
        w = max(64, w); h = max(64, round(v.h * w / v.w))
    return replace(v, w=(w // 8) * 8, h=(h // 8) * 8)


def t_latent_upscale_by(I, nid, idx):
    v = I.val(nid, "samples")
    if not isinstance(v, Lat):
        return v if isinstance(v, Unknown) else Unknown("LatentUpscaleBy input")
    s = float(I.inp(nid, "scale_by"))
    return replace(v, w=round(v.w / 8 * s) * 8, h=round(v.h / 8 * s) * 8)


def _resample(v: Img, w: int, h: int, nid: str, ct: str) -> Img:
    logo = v.logo
    if logo is not None and logo.status == EXACT and (w, h) != (v.w, v.h):
        logo = LogoState(ALTERED, why=f"{ct} (node {nid}) resamples the image from {v.w}x{v.h} to {w}x{h}, "
                                       f"which rescales the logo's pixels")
    return Img(w, h, v.batch, logo, v.ref)


def t_image_scale(I, nid, idx):
    v = I.val(nid, "image")
    if not isinstance(v, Img):
        return v if isinstance(v, Unknown) else Unknown("ImageScale input")
    w, h = _int(I.inp(nid, "width")), _int(I.inp(nid, "height"))
    if w == 0 and h == 0:
        return v
    if w == 0:
        w = max(1, round(v.w * h / v.h))
    elif h == 0:
        h = max(1, round(v.h * w / v.w))
    return _resample(v, w, h, nid, "ImageScale")


def t_image_scale_by(I, nid, idx):
    v = I.val(nid, "image")
    if not isinstance(v, Img):
        return v if isinstance(v, Unknown) else Unknown("ImageScaleBy input")
    s = float(I.inp(nid, "scale_by"))
    return _resample(v, round(v.w * s), round(v.h * s), nid, "ImageScaleBy")


def t_scale_total_pixels(I, nid, idx):
    v = I.val(nid, "image")
    if not isinstance(v, Img):
        return v if isinstance(v, Unknown) else Unknown("ImageScaleToTotalPixels input")
    total = float(I.inp(nid, "megapixels", 1.0)) * 1024 * 1024
    step = int(I.inp(nid, "resolution_steps", 1))
    s = (total / (v.w * v.h)) ** 0.5
    return _resample(v, round(v.w * s / step) * step, round(v.h * s / step) * step, nid, "ImageScaleToTotalPixels")


def t_upscale_with_model(I, nid, idx):
    v = I.val(nid, "image")
    if not isinstance(v, Img):
        return v if isinstance(v, Unknown) else Unknown("ImageUpscaleWithModel input")
    return _resample(v, v.w * 4, v.h * 4, nid, "ImageUpscaleWithModel")  # catalog upscaler is 4x


def t_image_crop(I, nid, idx):
    v = I.val(nid, "image")
    if not isinstance(v, Img):
        return v if isinstance(v, Unknown) else Unknown("ImageCrop input")
    w, h = _int(I.inp(nid, "width")), _int(I.inp(nid, "height"))
    x, y = min(_int(I.inp(nid, "x", 0)), v.w - 1), min(_int(I.inp(nid, "y", 0)), v.h - 1)  # nodes_images.ImageCrop
    nw, nh = min(w, v.w - x), min(h, v.h - y)
    logo = v.logo
    if logo is not None and logo.status == EXACT and not logo.is_canvas:
        inside = x <= logo.x and y <= logo.y and logo.x + logo.w <= x + nw and logo.y + logo.h <= y + nh
        logo = replace(logo, x=logo.x - x, y=logo.y - y) if inside else \
            LogoState(ALTERED, why=f"ImageCrop (node {nid}) cuts into or removes the logo")
    return Img(nw, nh, v.batch, logo, v.ref)


def t_pad_outpaint(I, nid, idx):
    if idx == 1:
        return Unknown("outpaint mask")
    v = I.val(nid, "image")
    if not isinstance(v, Img):
        return v if isinstance(v, Unknown) else Unknown("ImagePadForOutpaint input")
    l, t, r, b = (_int(I.inp(nid, k, 0)) for k in ("left", "top", "right", "bottom"))
    logo = v.logo
    if logo is not None and logo.status == EXACT and not logo.is_canvas:
        logo = replace(logo, x=logo.x + l, y=logo.y + t)
    return Img(v.w + l + r, v.h + t + b, v.batch, logo, v.ref)


def t_composite(I, nid, idx):
    dst, src = I.val(nid, "destination"), I.val(nid, "source")
    if not isinstance(dst, Img):
        return dst if isinstance(dst, Unknown) else Unknown("ImageCompositeMasked destination")
    x, y = _int(I.inp(nid, "x", 0)), _int(I.inp(nid, "y", 0))
    resize = bool(I.inp(nid, "resize_source", False))
    has_mask = I.inp(nid, "mask") is not None
    logo = dst.logo
    if dst.logo is not None and dst.logo.is_canvas:
        logo = LogoState(ALTERED, why=f"ImageCompositeMasked (node {nid}) uses the logo as the DESTINATION "
                                      f"(background); the logo must be the SOURCE pasted onto the artwork")
    if isinstance(src, Img) and src.logo is not None:
        if src.logo.status != EXACT:
            logo = src.logo
        elif resize and (src.w, src.h) != (dst.w, dst.h):
            logo = LogoState(ALTERED, why=f"ImageCompositeMasked (node {nid}) has resize_source=true, "
                                          f"which stretches the logo to the canvas size")
        elif has_mask:
            I.unverified.append(f"logo_exact: mask on ImageCompositeMasked node {nid} may blend logo pixels")
            logo = None
        elif x + src.w > dst.w or y + src.h > dst.h:
            logo = LogoState(ALTERED, why=f"ImageCompositeMasked (node {nid}) places the {src.w}x{src.h} logo at "
                                          f"({x},{y}) on a {dst.w}x{dst.h} canvas, so part of it falls outside")
        else:
            logo = LogoState(EXACT, x, y, src.w, src.h)
    elif isinstance(src, Unknown) and I.spec.logo:
        I.unverified.append(f"logo_exact: composite source of node {nid} unknown ({src.why})")
    ref = dst.ref if dst.ref else (src.ref if isinstance(src, Img) else None)
    if resize and not has_mask and isinstance(src, Img) and dst.ref and not src.ref:
        # resize_source stretches the source to the canvas size and pastes it at (x, y): at (0, 0) it
        # hides the destination entirely; elsewhere coverage is partial, and whether the layout
        # "survives" is a judgement call, so abstain.
        if x == 0 and y == 0:
            ref = f"destroyed:ImageCompositeMasked node {nid} has resize_source=true at (0,0), so the pasted image covers the whole canvas"
        else:
            I.unverified.append(f"reference_composition: resize_source on node {nid} partially covers the canvas")
    return Img(dst.w, dst.h, dst.batch, logo, ref)


def t_image_batch(I, nid, idx):
    a, b = I.val(nid, "image1"), I.val(nid, "image2")
    if not (isinstance(a, Img) and isinstance(b, Img)):
        return Unknown("ImageBatch input")
    return Img(a.w, a.h, a.batch + b.batch, a.logo, a.ref)


def t_text_overlay(I, nid, idx):
    """TextOverlay draws a text band at the top or bottom; the size is unchanged. Whether the band
    covers a corner logo depends on font metrics we do not model, so logo claims abstain."""
    v = I.val(nid, "images")
    if not isinstance(v, Img):
        return v if isinstance(v, Unknown) else Unknown("TextOverlay input")
    if v.logo is not None and v.logo.status == EXACT and not v.logo.is_canvas:
        I.unverified.append(f"logo_exact: TextOverlay node {nid} draws text after the logo; overlap not modelled")
        I.unverified.append(f"logo_position: TextOverlay node {nid} draws text after the logo; overlap not modelled")
        return replace(v, logo=None)
    return v


def t_passthrough(field_name: str) -> Callable:
    def f(I, nid, idx):
        return I.val(nid, field_name)
    return f


TRANSFER: dict[str, Callable[[_Interp, str, int], Value]] = {
    "LoadImage": t_load_image, "EmptyLatentImage": t_empty_latent, "EmptySD3LatentImage": t_empty_latent,
    "EmptyImage": t_empty_image, "VAEEncode": t_vae_encode, "VAEEncodeTiled": t_vae_encode,
    "KSampler": t_ksampler, "KSamplerAdvanced": t_ksampler, "VAEDecode": t_vae_decode,
    "VAEDecodeTiled": t_vae_decode, "LatentUpscale": t_latent_upscale, "LatentUpscaleBy": t_latent_upscale_by,
    "ImageScale": t_image_scale, "ImageScaleBy": t_image_scale_by,
    "ImageScaleToTotalPixels": t_scale_total_pixels, "ImageUpscaleWithModel": t_upscale_with_model,
    "ImageCrop": t_image_crop, "ImagePadForOutpaint": t_pad_outpaint,
    "ImageCompositeMasked": t_composite, "ImageBatch": t_image_batch,
    "TextOverlay": t_text_overlay, "ImageInvert": t_passthrough("image"), "ImageSharpen": t_passthrough("image"),
}

# ----------------------------------------------------------------------------- checks

def _corner_ok(lg: LogoState, W: int, H: int, corner: str, frac: float) -> bool:
    mx, my = W * frac, H * frac
    l, r = lg.x <= mx, (W - (lg.x + lg.w)) <= mx
    t, b = lg.y <= my, (H - (lg.y + lg.h)) <= my
    return {"top-left": l and t, "top-right": r and t, "bottom-left": l and b, "bottom-right": r and b}[corner]


def _corner_xy(corner: str, W: int, H: int, w: int, h: int, pad: int = 32) -> tuple[int, int]:
    x = pad if "left" in corner else W - w - pad
    y = pad if "top" in corner else H - h - pad
    return max(0, x), max(0, y)


def _size_cause(I: _Interp, save_id: str) -> str:
    """Walk upstream from a SaveImage to find the node that fixed the final size."""
    for nid, node in I.g.items():
        if node.get("class_type") == "EmptyLatentImage":
            w, h = node["inputs"].get("width"), node["inputs"].get("height")
            if isinstance(w, int) and isinstance(h, int) and (w % 8 or h % 8):
                return (f" Cause: EmptyLatentImage (node {nid}) is {w}x{h}, but latents are 1/8 scale, so "
                        f"ComfyUI floors it to {(w // 8) * 8}x{(h // 8) * 8}.")
    return ""


def check(graph: dict, spec: Spec, input_dir: Path) -> ContractReport:
    I = _Interp(graph, spec, input_dir)
    I.warm()
    rep = ContractReport()
    saves = [nid for nid, n in graph.items() if isinstance(n, dict) and n.get("class_type") == "SaveImage"]
    if not saves:
        rep.violations.append(Violation("single_output", None, "the workflow has no SaveImage node, so nothing is delivered",
                                        "end the pipeline in exactly one SaveImage node"))
        return rep
    W, H = spec.width, spec.height
    total = 0
    outs: list[tuple[str, Value]] = []
    for sid in saves:
        v = I.val(sid, "images")
        outs.append((sid, v))
        if isinstance(v, Img):
            rep.predicted_outputs.append((sid, v.w, v.h, v.batch))
            total += v.batch
        else:
            why = v.why if isinstance(v, Unknown) else "no image input"
            rep.unverified.append(f"delivery_size: SaveImage {sid}: {why}")
            total += 1
    if total != spec.n_outputs:
        rep.violations.append(Violation(
            "single_output", saves[0] if len(saves) == 1 else None,
            f"the workflow saves {total} images ({len(saves)} SaveImage node(s)); the brief asks for exactly {spec.n_outputs}",
            "keep a single SaveImage and set every batch_size to 1"))
    for sid, v in outs:
        if isinstance(v, Img) and (v.w, v.h) != (W, H):
            rep.violations.append(Violation(
                "delivery_size", sid,
                f"SaveImage will write {v.w}x{v.h}; the brief requires exactly {W}x{H}.{_size_cause(I, sid)}",
                f"generate at a size that is a multiple of 8 near the target aspect ratio, then insert ImageScale "
                f"(width={W}, height={H}, crop=\"center\") as the LAST resize before SaveImage"
                + (" and BEFORE compositing the logo" if spec.logo else "")))
    # logo
    if spec.logo:
        used = any(n.get("class_type") == "LoadImage" and n.get("inputs", {}).get("image") == spec.logo.file
                   for n in graph.values() if isinstance(n, dict))
        if not used:
            rep.violations.append(Violation("logo_exact", None, f"the logo file {spec.logo.file} is never loaded",
                                            f"add LoadImage(image=\"{spec.logo.file}\") and paste it with ImageCompositeMasked as the source"))
            rep.violations.append(Violation("logo_position", None, "logo absent, so it cannot be positioned", "see logo_exact"))
        for sid, v in (outs if used else []):
            _check_logo(I, rep, spec, sid, v)
    # reference
    if spec.reference:
        used = any(n.get("class_type") == "LoadImage" and n.get("inputs", {}).get("image") == spec.reference.file
                   for n in graph.values() if isinstance(n, dict))
        if not used:
            rep.violations.append(Violation(
                "reference_composition", None, f"the reference photo {spec.reference.file} is never loaded, so its composition cannot carry over",
                f"LoadImage(image=\"{spec.reference.file}\") -> (ImageScale to a multiple of 8) -> VAEEncode -> KSampler.latent_image with denoise 0.5-0.75"))
        for sid, v in (outs if used else []):
            _check_reference(rep, sid, v)
    rep.violations.sort(key=lambda x: x.claim)
    rep.violations = list({(v.claim, v.message): v for v in rep.violations}.values())
    # abstentions raised inside transfer functions live on the interpreter
    rep.unverified = list(dict.fromkeys(I.unverified + rep.unverified))
    return rep


def _check_logo(I: _Interp, rep: ContractReport, spec: Spec, sid: str, v: Value) -> None:
    if isinstance(v, Img):
        lg = v.logo
        if lg is None and not any(u.startswith("logo_exact") for u in I.unverified):
            rep.violations.append(Violation(
                "logo_exact", sid, "the loaded logo never reaches the delivered image",
                "paste it with ImageCompositeMasked(destination=<final artwork>, source=<logo LoadImage>, resize_source=false)"))
            rep.violations.append(Violation("logo_position", sid, "logo absent from output", "see logo_exact"))
        elif lg is not None and lg.status == ALTERED:
            rep.violations.append(Violation(
                "logo_exact", sid, lg.why,
                "load the logo with LoadImage and paste it with ImageCompositeMasked (resize_source=false, no mask) "
                "AFTER all generation and resizing, directly before SaveImage"))
            rep.violations.append(Violation("logo_position", sid, "logo not reproduced exactly, so its position cannot be checked", "see logo_exact"))
        elif lg is not None and lg.status == EXACT and lg.is_canvas:
            rep.violations.append(Violation(
                "logo_exact", sid, "the delivered image IS the bare logo, with no artwork",
                "composite the logo onto the generated artwork instead of saving it directly"))
            rep.violations.append(Violation("logo_position", sid, "see logo_exact", "see logo_exact"))
        elif lg is not None and not _corner_ok(lg, v.w, v.h, spec.logo.corner, spec.logo.max_margin_frac):
            x, y = _corner_xy(spec.logo.corner, v.w, v.h, lg.w, lg.h)
            rep.violations.append(Violation(
                "logo_position", sid,
                f"logo sits at ({lg.x},{lg.y}) size {lg.w}x{lg.h} on a {v.w}x{v.h} canvas, which is not the {spec.logo.corner} corner",
                f"set the ImageCompositeMasked x={x}, y={y}"))
    else:
        rep.unverified.append(f"logo_exact: output of SaveImage {sid} unknown")
        rep.unverified.append(f"logo_position: output of SaveImage {sid} unknown")


def _check_reference(rep: ContractReport, sid: str, v: Value) -> None:
    if isinstance(v, Img):
        if v.ref is None:
            rep.violations.append(Violation(
                "reference_composition", sid, "the reference is loaded but never feeds this output image",
                "route it through VAEEncode into the KSampler's latent_image (img2img) with denoise 0.5-0.75"))
        elif v.ref.startswith("destroyed"):
            rep.violations.append(Violation(
                "reference_composition", sid, v.ref.split(":", 1)[1] + ", so the reference composition is lost",
                "lower that KSampler's denoise to 0.5-0.75"))
    else:
        rep.unverified.append(f"reference_composition: output of SaveImage {sid} unknown")
