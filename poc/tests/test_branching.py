"""The forked runner must behave like separate runs: shared prefix, arms diverge only at the brief check."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atelier_poc.briefs import Brief, Spec  # noqa: E402
from atelier_poc.comfy_client import RunResult, ValidationResult  # noqa: E402
from atelier_poc.harness import run_branched  # noqa: E402
from atelier_poc.llm import Usage  # noqa: E402


def wf(w, h):
    return {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x"}},
            "4": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
            "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "latent_image": ["4", 0], "denoise": 1.0}},
            "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"images": ["6", 0]}}}


def wf_fixed(w, h):
    g = wf(1024, 1280)
    g["7"] = {"class_type": "ImageScale", "inputs": {"image": ["6", 0], "width": w, "height": h,
                                                    "upscale_method": "lanczos", "crop": "center"}}
    g["9"]["inputs"]["images"] = ["7", 0]
    return g


class ScriptedLLM:
    """Replies with a fixed sequence of submissions; each fork gets the same script position."""
    def __init__(self, script):
        self.script, self.i, self.seed, self.model, self.usage = script, 0, 0, "fake", Usage()

    def chat(self, msgs, tools=None, fmt=None):
        n_assistant = sum(1 for m in msgs if m.get("role") == "assistant")
        self.usage.calls += 1
        w = self.script[min(n_assistant, len(self.script) - 1)]
        return {"role": "assistant", "content": "",
                "tool_calls": [{"function": {"name": "submit_workflow", "arguments": {"workflow": w}}}]}


class FakeComfy:
    def __init__(self, out_dir):
        self.out_dir, self.runs = out_dir, 0

    def object_info(self):
        return {}

    def validate(self, w):
        ok = "SaveImage" in str(w)
        return ValidationResult(ok, None if ok else {"type": "prompt_no_outputs", "message": "no outputs"}, {})

    def run(self, w):
        self.runs += 1
        lat = w["4"]["inputs"]
        H, W = (lat["height"] // 8) * 8, (lat["width"] // 8) * 8
        if "7" in w:
            H, W = w["7"]["inputs"]["height"], w["7"]["inputs"]["width"]
        p = self.out_dir / f"o{self.runs}.png"
        Image.fromarray(np.zeros((H, W, 3), np.uint8)).save(p)
        return RunResult(True, [p])


def test_fork_shares_prefix_and_diverges_at_brief_check(tmp_path):
    b = Brief("T", "t2i_size", "make 1080x1350", Spec(1080, 1350), {})
    invalid = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}
    script = [invalid, wf(1080, 1350), wf_fixed(1080, 1350)]   # 1350 floors to 1344; the fix adds a final ImageScale
    comfy = FakeComfy(tmp_path)
    eps = run_branched(b, ["extended", "output_retry", "contract"], ScriptedLLM(script), comfy, tmp_path)
    ext, outr, con = eps["extended"], eps["output_retry"], eps["contract"]
    # identical prefix: one ComfyUI rejection, then the first valid submission
    assert ext.exec_rejections == outr.exec_rejections == con.exec_rejections == 1
    # extended ships the off-spec workflow; the two checking arms reject it once and resubmit
    assert ext.workflow == wf(1080, 1350) and ext.brief_rejections == 0
    assert con.brief_rejections == 1 and con.executions == 0 and con.workflow == wf_fixed(1080, 1350)
    assert outr.brief_rejections == 1 and outr.executions == 2 and outr.workflow == wf_fixed(1080, 1350)
    # prefix LLM cost is charged to every arm; checking arms pay one extra call
    assert ext.usage["calls"] == 2 and con.usage["calls"] == 3 and outr.usage["calls"] == 3


def test_budget_exhaustion_ships_last_valid_not_last_broken(tmp_path):
    b = Brief("T", "t2i_size", "make 1080x1350", Spec(1080, 1350), {})
    broken = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {}}}
    script = [wf(1080, 1350)] + [broken] * 30           # first valid but off-spec, then only broken retries
    eps = run_branched(b, ["contract"], ScriptedLLM(script), FakeComfy(tmp_path), tmp_path, max_tool_calls=6)
    assert eps["contract"].workflow == wf(1080, 1350)
