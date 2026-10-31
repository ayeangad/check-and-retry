"""Shape-faithful stand-ins for ComfyUI's model-dependent operations.

Why this exists: this experiment runs on a 4 GB laptop GPU with no image-model weights. We need
ComfyUI to *really* execute LLM-authored workflows so that delivery properties (pixel size,
number of outputs, whether supplied pixels survive untouched) are measured on real output files.

What is real: every node class, the graph executor, input validation, and every image-space
node (LoadImage, ImageScale, ImageCrop, ImageCompositeMasked, SaveImage, ...). Those run
unmodified ComfyUI code.

What is stubbed: the internals of model objects only. The stubs keep the tensor geometry of
the real ops:
  * VAE.encode crops to a multiple of 8 and downsamples by 8; VAE.decode upsamples by 8.
  * The KSampler keeps the latent shape. With denoise < 1 it blends the input latent with
    seeded noise, so img2img output still resembles its reference. With denoise = 1 it
    returns pure seeded noise.
  * The upscale model multiplies the size by its scale (4x).
So any graph that would produce W×H pixels in real ComfyUI produces W×H pixels here. Image
*content* is not realistic, so no content claim (style, text glyphs, anatomy) is evaluated
anywhere in this project.

It also registers POST /atelier/validate, which runs ComfyUI's own `validate_prompt` without
queueing anything. This is the "validate before it runs" tool of an Extended-style harness.
"""
from __future__ import annotations

import logging

import torch
from aiohttp import web

import execution
import nodes
import server
from comfy_api.latest import io

log = logging.getLogger("atelier_stub")


class StubModel:
    def __init__(self, name: str):
        self.name = name


class StubClip:
    def tokenize(self, text, **kw):
        return {"text": text}

    def encode_from_tokens_scheduled(self, tokens, **kw):
        return [[torch.zeros(1, 77, 8), {"pooled_output": torch.zeros(1, 8), "stub_text": tokens["text"]}]]

    def clone(self):
        return self


class StubVAE:
    def encode(self, pixels: torch.Tensor) -> torch.Tensor:
        b, h, w, _ = pixels.shape
        h8, w8 = (h // 8) * 8, (w // 8) * 8          # real VAEEncode also drops the remainder
        p = pixels[:, :h8, :w8, :3].movedim(-1, 1)
        small = torch.nn.functional.avg_pool2d(p, 8)  # [b,3,h/8,w/8]
        return torch.cat([small * 2 - 1, torch.zeros(b, 1, h8 // 8, w8 // 8)], dim=1)

    def decode(self, latent: torch.Tensor) -> torch.Tensor:
        rgb = ((latent[:, :3].clamp(-1, 1) + 1) / 2)
        big = torch.nn.functional.interpolate(rgb, scale_factor=8, mode="nearest")
        return big.movedim(1, -1).contiguous()


class StubUpscaler:
    scale = 4


def _stub_ksampler(model, seed, steps, cfg, sampler_name, scheduler, positive, negative, latent,
                   denoise=1.0, disable_noise=False, start_step=None, last_step=None,
                   force_full_denoise=False):
    x = latent["samples"]
    if x.shape[1] != 4:
        x = torch.zeros(x.shape[0], 4, *x.shape[2:])
    g = torch.Generator().manual_seed(int(seed) % (2**63))
    noise = torch.rand(x.shape, generator=g) * 2 - 1
    d = 1.0 if disable_noise is False and denoise is None else float(denoise)
    out = latent.copy()
    out["samples"] = (1 - d) * x + d * noise
    return (out,)


def _install():
    nodes.CheckpointLoaderSimple.load_checkpoint = lambda self, ckpt_name: (StubModel(ckpt_name), StubClip(), StubVAE())
    nodes.VAELoader.load_vae = lambda self, vae_name: (StubVAE(),)
    nodes.UNETLoader.load_unet = lambda self, unet_name, weight_dtype="default": (StubModel(unet_name),)
    nodes.CLIPLoader.load_clip = lambda self, clip_name, type="stable_diffusion", device="default": (StubClip(),)
    nodes.DualCLIPLoader.load_clip = lambda self, clip_name1, clip_name2, type, device="default": (StubClip(),)
    nodes.LoraLoader.load_lora = lambda self, model, clip, *a, **k: (model, clip)
    nodes.common_ksampler = _stub_ksampler

    def _upscale(cls, upscale_model, image):
        s = upscale_model.scale
        out = torch.nn.functional.interpolate(image.movedim(-1, 1), scale_factor=s, mode="nearest")
        return io.NodeOutput(out.movedim(1, -1))

    # V3 (io.ComfyNode) nodes are registered as their own class objects, so patch the classes
    # that are actually in the live registry, not just the module attributes.
    loader = nodes.NODE_CLASS_MAPPINGS.get("UpscaleModelLoader")
    upscaler = nodes.NODE_CLASS_MAPPINGS.get("ImageUpscaleWithModel")
    if loader is None or upscaler is None:
        log.warning("upscale nodes not registered yet; upscale stub not installed")
    else:
        loader.execute = classmethod(lambda cls, model_name: io.NodeOutput(StubUpscaler()))
        upscaler.execute = classmethod(_upscale)
    log.info("atelier_stub: model internals stubbed (geometry-faithful)")


_install()


@server.PromptServer.instance.routes.post("/atelier/validate")
async def _validate(request):
    prompt = (await request.json())["prompt"]
    valid, error, outputs, node_errors = await execution.validate_prompt("validate-only", prompt, None)
    return web.json_response({"valid": bool(valid), "error": error, "node_errors": node_errors,
                              "outputs": list(outputs) if outputs else []})


NODE_CLASS_MAPPINGS: dict = {}
