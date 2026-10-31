"""LLM clients with token/latency/cost accounting.

OllamaChat    local models (qwen3.5:4b), $0.
DeepSeekChat  DeepSeek API, model `deepseek-flash` = DeepSeek-V4.1-Flash-1017, the same model AtelierBench
              lists as `deepseek-v4.1-flash`. Spend is charged at PEAK list prices (conservative), persisted across
              processes, and hard-capped: a call that would start past the cap raises BudgetExceeded.
The key is read from ~/.deepseek_key (or $DEEPSEEK_API_KEY) and is never logged or stored elsewhere.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0
    cached_prompt_tokens: int = 0
    usd: float = 0.0

    def add(self, r: dict, secs: float) -> None:
        self.calls += 1
        self.prompt_tokens += int(r.get("prompt_eval_count", 0))
        self.completion_tokens += int(r.get("eval_count", 0))
        self.seconds += secs


@dataclass
class OllamaChat:
    model: str
    seed: int = 0
    temperature: float = 0.6
    num_ctx: int = 8192
    num_predict: int = 2048
    url: str = "http://127.0.0.1:11434/api/chat"
    usage: Usage = field(default_factory=Usage)

    def chat(self, messages: list[dict], tools: list[dict] | None = None, fmt: str | None = None) -> dict:
        body = {"model": self.model, "messages": messages, "stream": False, "think": False,
                "keep_alive": "60m",
                "options": {"seed": self.seed, "temperature": self.temperature,
                            "num_ctx": self.num_ctx, "num_predict": self.num_predict}}
        if tools:
            body["tools"] = tools
        if fmt:
            body["format"] = fmt
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=900) as r:
            resp = json.loads(r.read())
        self.usage.add(resp, time.monotonic() - t0)
        return resp["message"]


# ----------------------------------------------------------------------------- DeepSeek

# USD per 1M tokens, peak list price for deepseek-flash (api-docs.deepseek.com/quick_start/pricing, read 2026-10-30).
# Off-peak is half; charging peak keeps the cap conservative.
DS_PRICE = {"hit": 0.006, "miss": 0.30, "out": 1.20}


class BudgetExceeded(RuntimeError):
    pass


class SpendLedger:
    """Cumulative spend in a small JSON file, so the cap holds across runs and processes."""
    def __init__(self, path: Path, cap_usd: float):
        self.path, self.cap = path, cap_usd

    def spent(self) -> float:
        try:
            return float(json.loads(self.path.read_text())["usd"])
        except (FileNotFoundError, ValueError, KeyError):
            return 0.0

    def check(self) -> None:
        if self.spent() >= self.cap:
            raise BudgetExceeded(f"BudgetExceeded: spent ${self.spent():.4f} >= cap ${self.cap:.2f}")

    def add(self, usd: float) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"usd": self.spent() + usd, "updated": time.time()}))
        tmp.replace(self.path)


def _load_key() -> str:
    k = os.environ.get("DEEPSEEK_API_KEY") or (Path.home() / ".deepseek_key").read_text()
    return k.strip()


def _to_openai(messages: list[dict]) -> list[dict]:
    """Translate the harness's Ollama-style transcript to OpenAI chat format.

    Tool results carry no ids in the harness, so they are matched to the preceding assistant's
    tool calls in order. Calls the harness never answered (it stops processing a turn after a
    rejected submission or when the budget runs out) get a synthetic 'not executed' result,
    because the API requires every tool call to be answered."""
    out: list[dict] = []
    pending: list[str] = []

    def flush():
        while pending:
            out.append({"role": "tool", "tool_call_id": pending.pop(0),
                        "content": "Not executed: an earlier call in this turn ended the turn."})

    for i, m in enumerate(messages):
        role = m.get("role")
        if role == "assistant":
            flush()
            msg = {"role": "assistant", "content": m.get("content") or ""}
            calls = m.get("tool_calls") or []
            if calls:
                msg["tool_calls"] = []
                for j, c in enumerate(calls):
                    cid = c.get("id") or f"call_{i}_{j}"
                    fn = c.get("function", {})
                    args = fn.get("arguments", {})
                    msg["tool_calls"].append({"id": cid, "type": "function", "function": {
                        "name": fn.get("name"), "arguments": args if isinstance(args, str) else json.dumps(args)}})
                    pending.append(cid)
            out.append(msg)
        elif role == "tool":
            cid = pending.pop(0) if pending else "call_orphan"
            out.append({"role": "tool", "tool_call_id": cid, "content": m.get("content", "")})
        else:
            flush()
            out.append({"role": role, "content": m.get("content", "")})
    flush()
    return out


@dataclass
class DeepSeekChat:
    model: str = "deepseek-flash"
    seed: int = 0                       # recorded only: the API has no seed; repeats are independent samples
    temperature: float = 0.6
    max_tokens: int = 4096
    ledger: SpendLedger | None = None
    url: str = "https://api.deepseek.com/chat/completions"
    usage: Usage = field(default_factory=Usage)

    def chat(self, messages: list[dict], tools: list[dict] | None = None, fmt: str | None = None) -> dict:
        if self.ledger:
            self.ledger.check()
        body = {"model": self.model, "messages": _to_openai(messages), "temperature": self.temperature,
                "max_tokens": self.max_tokens, "thinking": {"type": "disabled"}, "stream": False}
        if tools:
            body["tools"] = tools
        data = json.dumps(body).encode()
        key = _load_key()
        t0 = time.monotonic()
        for attempt in range(6):
            req = urllib.request.Request(self.url, data=data, headers={
                "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    resp = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code == 402:
                    raise BudgetExceeded("BudgetExceeded: DeepSeek reports insufficient balance (402)") from e
                if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"DeepSeek HTTP {e.code}: {e.read()[:300]!r}") from e
        u = resp.get("usage", {})
        hit, miss = int(u.get("prompt_cache_hit_tokens", 0)), int(u.get("prompt_cache_miss_tokens", 0))
        out_t = int(u.get("completion_tokens", 0))
        usd = (hit * DS_PRICE["hit"] + miss * DS_PRICE["miss"] + out_t * DS_PRICE["out"]) / 1e6
        self.usage.calls += 1
        self.usage.prompt_tokens += hit + miss
        self.usage.cached_prompt_tokens += hit
        self.usage.completion_tokens += out_t
        self.usage.seconds += time.monotonic() - t0
        self.usage.usd += usd
        if self.ledger:
            self.ledger.add(usd)
        m = resp["choices"][0]["message"]
        calls = []
        for c in m.get("tool_calls") or []:
            fn = c.get("function", {})
            args = fn.get("arguments") or "{}"
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, TypeError):
                pass                      # harness tolerates string arguments
            calls.append({"id": c.get("id"), "function": {"name": fn.get("name"), "arguments": args}})
        return {"role": "assistant", "content": m.get("content") or "", **({"tool_calls": calls} if calls else {})}
