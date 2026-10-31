"""Agent harnesses that author ComfyUI workflows from a design brief, built to answer the question
Hyde's AtelierBench post leaves open: "What happens when models check their own output and retry?"

This is an independent re-creation of the *shape* of the AtelierBench harnesses as the article
describes them. It is not Hyde's code.

  base          one shot: brief + model catalog -> workflow JSON. No tools, no checking.
  extended      tool loop (search_nodes, node_info, validate_workflow, submit_workflow). Submission is
                checked ONLY for executability (ComfyUI's own validate_prompt), mirroring "validate its
                workflow before it runs". No brief checking. This is the no-self-check baseline.
  output_retry  same loop. A ComfyUI-valid submission is EXECUTED, the delivered image(s) are checked
                against the brief's objective claims, and any failures go back to the agent for a
                retry. "Check the output and retry": each retry pays for another generation.
  contract      same loop. A ComfyUI-valid submission is checked by the static brief-contract
                verifier on the GRAPH, before anything runs, and violations go back for a retry.
                "Check the plan and retry": no generation is spent on rejected attempts.

All tool arms share one system prompt, tool set, budget and seed, so their first submission is
identical. They diverge only in what the submit check reports. Brief-check rejections are capped
(MAX_BRIEF_REJECTIONS); after that the last submission ships, as a production loop would.
"""
from __future__ import annotations

import copy
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import brief_contract
from .briefs import Brief
from .comfy_client import ComfyClient
from .evaluator import evaluate
from .llm import OllamaChat

ARMS = ("base", "extended", "output_retry", "contract", "output_retry_rich")
MAX_BRIEF_REJECTIONS = 3

CATALOG = """Available models (exact filenames):
- checkpoints (CheckpointLoaderSimple.ckpt_name): sdxl_base_1.0.safetensors (general), juggernautXL_photoreal_v9.safetensors (photoreal), animagineXL_anime_v3.safetensors (anime/illustration)
- upscale_models (UpscaleModelLoader.model_name): 4x-UltraSharp.pth (4x upscaler)
Input files are referenced by filename in LoadImage.image."""

FORMAT = """Write the workflow in ComfyUI API format: a JSON object mapping node ids (strings) to
{"class_type": <node name>, "inputs": {...}}. A link to another node's output is [<node id>, <output index>].
Minimal example (text-to-image at 512x512):
{"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sdxl_base_1.0.safetensors"}},
 "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": "a red apple"}},
 "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": "blurry"}},
 "4": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
 "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "seed": 1, "steps": 20, "cfg": 7.0, "sampler_name": "euler", "scheduler": "normal", "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0], "denoise": 1.0}},
 "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
 "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "out"}}}"""

NODE_REFERENCE = """Core nodes you will most likely need (outputs indexed from 0):
- CheckpointLoaderSimple(ckpt_name) -> [0] MODEL, [1] CLIP, [2] VAE
- CLIPTextEncode(clip, text) -> [0] CONDITIONING
- EmptyLatentImage(width, height, batch_size) -> [0] LATENT
- LoadImage(image=<filename>) -> [0] IMAGE, [1] MASK
- VAEEncode(pixels: IMAGE, vae) -> [0] LATENT          (image -> latent, for img2img)
- KSampler(model, seed, steps, cfg, sampler_name e.g. "euler"/"dpmpp_2m", scheduler e.g. "normal"/"karras",
           positive, negative, latent_image, denoise) -> [0] LATENT   (denoise < 1.0 keeps the input latent's structure)
- VAEDecode(samples: LATENT, vae) -> [0] IMAGE
- ImageScale(image, upscale_method e.g. "lanczos", width, height, crop "disabled"/"center") -> [0] IMAGE
- ImageCrop(image, width, height, x, y) -> [0] IMAGE
- ImageCompositeMasked(destination: IMAGE, source: IMAGE, x, y, resize_source: bool) -> [0] IMAGE  (pastes source onto destination at x,y)
- UpscaleModelLoader(model_name) -> [0] UPSCALE_MODEL ; ImageUpscaleWithModel(upscale_model, image) -> [0] IMAGE
- SaveImage(images, filename_prefix) -> output"""

SYS_BASE = ("You are a senior designer who builds ComfyUI workflows that meet client briefs exactly.\n"
            f"{CATALOG}\n\n{NODE_REFERENCE}\n\n{FORMAT}\n\nReply with ONLY the workflow JSON, no prose.")

SYS_TOOLS = ("You are a senior designer who builds ComfyUI workflows that meet client briefs exactly.\n"
             f"{CATALOG}\n\n{NODE_REFERENCE}\n\n{FORMAT}\n\n"
             "You have tools: search_nodes (find node types), node_info (a node's inputs/outputs), "
             "validate_workflow (optional pre-check) and submit_workflow (deliver the workflow). "
             "Work efficiently: write a complete workflow and call submit_workflow with it early. "
             "Submissions are checked; if submit_workflow reports problems, fix them and submit again. "
             "Only use search_nodes/node_info for node types you are unsure about. "
             "Pass workflows as JSON objects.")

TOOLS = [
    {"type": "function", "function": {"name": "search_nodes", "description": "Search ComfyUI node types by keyword.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "node_info", "description": "Show the inputs and outputs of a ComfyUI node type.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "validate_workflow", "description": "Validate an API-format workflow without running it.",
     "parameters": {"type": "object", "properties": {"workflow": {"type": "object"}}, "required": ["workflow"]}}},
    {"type": "function", "function": {"name": "submit_workflow", "description": "Submit the API-format workflow for delivery. It is checked; if problems are reported, fix them and submit again.",
     "parameters": {"type": "object", "properties": {"workflow": {"type": "object"}}, "required": ["workflow"]}}},
]


@dataclass
class Episode:
    brief_id: str
    arm: str
    seed: int
    model: str
    workflow: dict | None = None
    submitted: bool = False
    tool_calls: int = 0
    tool_counts: dict = field(default_factory=dict)
    validate_calls: int = 0
    submit_calls: int = 0
    brief_rejections: int = 0       # submissions sent back by the brief check (output_retry / contract)
    exec_rejections: int = 0        # submissions sent back by ComfyUI validation
    executions: int = 0             # workflow executions inside the loop (each = a paid generation in production)
    check_ms: float = 0.0           # time spent in the brief check (static verifier or execute+inspect)
    parse_errors: int = 0
    transcript: list = field(default_factory=list)
    error: str | None = None
    wall_s: float = 0.0
    usage: dict = field(default_factory=dict)       # LLM calls/tokens/seconds charged to this arm (incl. shared prefix)


def extract_json(text: str) -> dict | None:
    """Pull the first JSON object out of a model reply (tolerates ``` fences and prose)."""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    cands = [m.group(1)] if m else []
    start = text.find("{")
    if start >= 0:
        cands.append(text[start:text.rfind("}") + 1])
    for c in cands:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _coerce_workflow(arg) -> dict | None:
    if isinstance(arg, dict):
        inner = arg.get("workflow")
        if isinstance(inner, (dict, str)):          # tolerate double-wrapped {"workflow": {...}}
            return _coerce_workflow(inner)
        return arg or None
    if isinstance(arg, str):
        return extract_json(arg)
    return None


def _user_prompt(b: Brief) -> str:
    files = ", ".join(f"{role}: {fn}" for role, fn in b.inputs.items()) or "none"
    return f"Client brief:\n{b.text}\n\nInput files: {files}"


_STOP = {"or", "and", "for", "the", "a", "an", "to", "of", "on", "in", "with", "node", "nodes", "comfyui", "image", "images"}


class ToolEnv:
    def __init__(self, comfy: ComfyClient, brief: Brief, arm: str, input_dir: Path):
        self.comfy, self.brief, self.arm, self.input_dir = comfy, brief, arm, input_dir
        self.info = comfy.object_info()

    def search_nodes(self, query: str) -> str:
        """Keyword search over node names, display names, ComfyUI search_aliases, category and
        description. Name and alias hits dominate, stopwords are ignored, and deprecated or
        dev-only nodes are skipped (similar in spirit to `comfy nodes search`)."""
        query = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(query))     # CamelCase -> words
        q = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in _STOP and len(w) > 1]
        scored = []
        for name, d in self.info.items():
            if d.get("deprecated") or d.get("dev_only") or d.get("api_node"):
                continue
            nm = f"{name} {d.get('display_name', '')}".lower()
            al = " ".join(d.get("search_aliases") or []).lower()
            rest = f"{d.get('category', '')} {d.get('description', '')}".lower()
            s = sum(6 * (w in nm) + 4 * (w in al) + 1 * (w in rest) for w in q)
            if s:
                scored.append((s, -len(name), name, (d.get("description") or d.get("category", ""))[:80]))
        scored.sort(reverse=True)
        return "\n".join(f"{n}: {desc}" for _, _, n, desc in scored[:8]) or "no matching nodes"

    def node_info(self, name: str) -> str:
        d = self.info.get(str(name))
        if not d:
            return f"unknown node type {name!r}; use search_nodes"
        def fmt(sect):
            out = []
            for k, spec in (d.get("input", {}).get(sect) or {}).items():
                t = spec[0]
                t = f"one of {t[:6]}{'...' if len(t) > 6 else ''}" if isinstance(t, list) else t
                extra = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
                rng = {k2: extra[k2] for k2 in ("default", "min", "max") if k2 in extra}
                out.append(f"  {k}: {t} {rng if rng else ''}".rstrip())
            return out
        outs = ", ".join(f"[{i}] {t}" for i, t in enumerate(d.get("output", [])))
        return "\n".join([f"{name} — {d.get('description', '')[:120]}", "required inputs:", *fmt("required"),
                          "optional inputs:", *fmt("optional"), f"outputs: {outs}"])

    def validate(self, wf: dict, ep: Episode) -> str:
        """Optional pre-check tool: executability only, identical in every arm."""
        return self.comfy.validate(wf).summary()

    def exec_check(self, wf: dict, ep: Episode) -> tuple[bool, str]:
        """Stage 1 of every submission, identical in all tool arms: does it pass ComfyUI validation?"""
        ep.submit_calls += 1
        v = self.comfy.validate(wf)
        if not v.valid:
            ep.exec_rejections += 1
            return False, v.summary() + "\nNot delivered. Fix the workflow and submit again."
        return True, ""

    def brief_check(self, wf: dict, ep: Episode) -> tuple[bool, str]:
        """Stage 2, arm-specific: the self-check whose effect we are measuring."""
        if self.arm == "extended" or ep.brief_rejections >= MAX_BRIEF_REJECTIONS:
            return True, "Accepted."
        t0 = time.perf_counter()
        if self.arm == "contract":
            rep = brief_contract.check(wf, self.brief.spec, self.input_dir)
            ep.check_ms += (time.perf_counter() - t0) * 1000
            if rep.ok:
                return True, "Accepted."
            ep.brief_rejections += 1
            return False, ("ComfyUI validation: OK, but the workflow does not meet the brief:\n" + rep.render() +
                           "\nNot delivered. Fix these and submit again.")
        # output_retry: run it, look at what came out, report what is wrong with the delivered image(s)
        run = self.comfy.run(wf)
        ep.executions += 1
        out = evaluate(self.brief.spec, run.output_files if run.ok else [], self.input_dir, run.ok)
        ep.check_ms += (time.perf_counter() - t0) * 1000
        if not run.ok:
            ep.brief_rejections += 1
            return False, f"The workflow failed while running: {run.error}\nNot delivered. Fix it and submit again."
        if out.all_pass:
            return True, "Accepted."
        ep.brief_rejections += 1
        rich_dir = self.input_dir if self.arm == "output_retry_rich" else None
        return False, ("The workflow ran. Checking the delivered image(s) against the brief:\n" +
                       describe_output_failures(self.brief.spec, out, rich_dir) + "\nNot delivered. Fix these and submit again.")


def describe_output_failures(spec, out, rich_input_dir: Path | None = None) -> str:
    """Output-level feedback: says WHAT is wrong with the delivered image, not WHERE in the graph.

    With `rich_input_dir` (arm `output_retry_rich`, experiment D), logo feedback also carries the
    logo's pixel size and the target paste position, computed with the same formula the contract
    uses (`brief_contract._corner_xy`). This equalises the information content of the two checks,
    so that output_retry_rich vs contract isolates check-before vs check-after execution."""
    d, lines = out.details, []
    logo_hint = ""
    if rich_input_dir is not None and spec.logo:
        from PIL import Image
        from .brief_contract import _corner_xy
        with Image.open(rich_input_dir / spec.logo.file) as im:
            lw, lh = im.size
        x, y = _corner_xy(spec.logo.corner, spec.width, spec.height, lw, lh)
        logo_hint = (f" The supplied logo is {lw}x{lh} pixels; on the required {spec.width}x{spec.height} canvas,"
                     f" paste it unscaled with its top-left at x={x}, y={y}.")
    if not out.claims.get("single_output", True):
        lines.append(f"- single_output: {d.get('n_files')} images were delivered; the brief asks for exactly {spec.n_outputs}.")
    if not out.claims.get("delivery_size", True):
        lines.append(f"- delivery_size: delivered size(s) {d.get('sizes')}; the brief requires exactly {spec.width}x{spec.height}.")
    if spec.logo and not out.claims.get("logo_exact", True):
        lines.append(f"- logo_exact: the supplied logo {spec.logo.file} does not appear unaltered (same pixels, same size) in the delivered image." + logo_hint)
    elif spec.logo and not out.claims.get("logo_position", True):
        lines.append(f"- logo_position: the logo was found at {d.get('logo_pos')}, not in the {spec.logo.corner} corner." + logo_hint)
    if spec.reference and not out.claims.get("reference_composition", True):
        lines.append(f"- reference_composition: the delivered image does not keep the composition of {spec.reference.file} "
                     f"(layout correlation {d.get('reference_r')}).")
    return "\n".join(lines)


def run_episode(brief: Brief, arm: str, llm: OllamaChat, comfy: ComfyClient, input_dir: Path,
                max_tool_calls: int = 15, max_turns: int = 20) -> Episode:
    """Run one arm on its own (used for `base`, and available for single-arm tool runs)."""
    t0 = time.monotonic()
    if arm == "base":
        ep = Episode(brief.id, arm, llm.seed, llm.model)
        try:
            msgs = [{"role": "system", "content": SYS_BASE}, {"role": "user", "content": _user_prompt(brief)}]
            reply = llm.chat(msgs)
            ep.transcript = msgs + [reply]
            ep.workflow = extract_json(reply.get("content", ""))
            ep.parse_errors += ep.workflow is None
            ep.submitted = ep.workflow is not None
        except Exception as e:  # recorded, never silently dropped
            ep.error = f"{type(e).__name__}: {e}"
        ep.wall_s = time.monotonic() - t0
        ep.usage = asdict(llm.usage)
        return ep
    loop = AgentLoop(brief, arm, llm, comfy, input_dir, max_tool_calls, max_turns)
    loop.run()
    return loop.finish(t0)


def run_branched(brief: Brief, arms: list[str], llm: OllamaChat, comfy: ComfyClient, input_dir: Path,
                 max_tool_calls: int = 15, max_turns: int = 20) -> dict[str, Episode]:
    """Run the shared prefix ONCE, fork at the first ComfyUI-valid submission, continue each arm.

    The tool arms are identical (prompt, tools, seed, executability check) up to that point, so
    this is exactly equivalent to running them separately, minus the duplicated compute and any
    decoding nondeterminism. Prefix cost is charged to every arm's usage, so per-arm cost figures
    are what a standalone run would have paid."""
    t0 = time.monotonic()
    prefix = AgentLoop(brief, "extended", llm, comfy, input_dir, max_tool_calls, max_turns)
    status = prefix.run(branch_on_valid=True)
    prefix_wall = time.monotonic() - t0
    out: dict[str, Episode] = {}
    for arm in arms:
        t1 = time.monotonic()
        loop = prefix.fork(arm)
        if status == "branch":
            if loop.resolve_pending() == "continue":
                loop.run()
        ep = loop.finish(t1)
        ep.wall_s += prefix_wall
        out[arm] = ep
    return out


class AgentLoop:
    def __init__(self, brief, arm, llm: OllamaChat, comfy, input_dir, max_tool_calls, max_turns):
        self.brief, self.arm, self.llm, self.comfy, self.input_dir = brief, arm, llm, comfy, input_dir
        self.max_tool_calls, self.max_turns = max_tool_calls, max_turns
        self.env = ToolEnv(comfy, brief, arm, input_dir)
        self.ep = Episode(brief.id, arm, llm.seed, llm.model)
        self.msgs = [{"role": "system", "content": SYS_TOOLS}, {"role": "user", "content": _user_prompt(brief)}]
        self.last_wf: dict | None = None
        self.last_valid_wf: dict | None = None   # last submission that passed ComfyUI validation
        self.turns = 0
        self.pending: dict | None = None
        self.done = False

    def fork(self, arm: str) -> "AgentLoop":
        twin = copy.copy(self)
        twin.arm = arm
        twin.env = ToolEnv(self.comfy, self.brief, arm, self.input_dir)
        twin.ep = copy.deepcopy(self.ep)
        twin.ep.arm = arm
        twin.msgs = copy.deepcopy(self.msgs)
        twin.llm = copy.copy(self.llm)
        twin.llm.usage = copy.deepcopy(self.llm.usage)
        return twin

    def _submit(self, wf: dict, branch_on_valid: bool) -> str:
        self.last_wf = wf
        ok, msg = self.env.exec_check(wf, self.ep)
        if not ok:
            self.msgs.append({"role": "tool", "content": msg, "tool_name": "submit_workflow"})
            return "continue"
        self.last_valid_wf = wf
        if branch_on_valid:
            self.pending = wf
            return "branch"
        return self._apply_brief_check(wf)

    def _apply_brief_check(self, wf: dict) -> str:
        accepted, msg = self.env.brief_check(wf, self.ep)
        self.msgs.append({"role": "tool", "content": msg, "tool_name": "submit_workflow"})
        if accepted:
            self.ep.workflow, self.ep.submitted, self.done = wf, True, True
            return "done"
        return "continue"

    def resolve_pending(self) -> str:
        wf, self.pending = self.pending, None
        return self._apply_brief_check(wf)

    def run(self, branch_on_valid: bool = False) -> str:
        try:
            while not self.done and self.turns < self.max_turns and self.ep.tool_calls < self.max_tool_calls:
                self.turns += 1
                reply = self.llm.chat(self.msgs, tools=TOOLS)
                self.msgs.append(reply)
                calls = reply.get("tool_calls") or []
                if not calls:
                    wf = extract_json(reply.get("content", ""))   # answered in prose/JSON instead of a tool call
                    if wf:
                        self.last_wf = wf
                    self.msgs.append({"role": "user", "content": "Use the tools: call submit_workflow with your complete workflow."})
                    continue
                for c in calls:
                    if self.ep.tool_calls >= self.max_tool_calls:
                        break
                    fn = c.get("function", {})
                    name, args = fn.get("name"), fn.get("arguments") or {}
                    if isinstance(args, str):
                        args = extract_json(args) or {}
                    self.ep.tool_calls += 1
                    self.ep.tool_counts[name] = self.ep.tool_counts.get(name, 0) + 1
                    if name in ("validate_workflow", "submit_workflow"):
                        wf = _coerce_workflow(args.get("workflow", args))
                        if wf is None:
                            self.ep.parse_errors += 1
                            self.msgs.append({"role": "tool", "tool_name": name, "content":
                                              "Could not parse the workflow argument. Pass the API-format workflow as a JSON object."})
                            continue
                        if name == "validate_workflow":
                            self.last_wf = wf
                            self.ep.validate_calls += 1
                            self.msgs.append({"role": "tool", "content": self.env.validate(wf, self.ep), "tool_name": name})
                            continue
                        status = self._submit(wf, branch_on_valid)
                        if status in ("branch", "done"):
                            return status
                        break        # after a rejected submission, let the model respond to the feedback
                    out = (self.env.search_nodes(args.get("query", "")) if name == "search_nodes" else
                           self.env.node_info(args.get("name", "")) if name == "node_info" else f"unknown tool {name}")
                    self.msgs.append({"role": "tool", "content": out, "tool_name": name})
        except Exception as e:  # recorded, never silently dropped
            self.ep.error = f"{type(e).__name__}: {e}"
        return "done" if self.done else "exhausted"

    def finish(self, t0: float) -> Episode:
        ep = self.ep
        ep.transcript = self.msgs
        if not ep.submitted:
            # Budget exhausted. Ship the last submission that passed ComfyUI validation, as a production
            # loop would, so a retry that breaks the graph never costs the arm its earlier runnable attempt.
            # Fall back to the last workflow seen.
            ep.workflow = self.last_valid_wf or self.last_wf
        ep.wall_s = time.monotonic() - t0
        ep.usage = asdict(self.llm.usage)
        return ep
