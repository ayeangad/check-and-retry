"""Minimal HTTP client for a local ComfyUI server (validate, run, collect outputs)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ValidationResult:
    valid: bool
    error: dict | None
    node_errors: dict

    def summary(self, limit: int = 6) -> str:
        if self.valid:
            return "ComfyUI validation: OK"
        lines = []
        if self.error:
            lines.append(f"{self.error.get('type')}: {self.error.get('message')} {self.error.get('details', '')}".strip())
        for nid, ne in list(self.node_errors.items())[:limit]:
            for e in ne.get("errors", [])[:3]:
                lines.append(f"node {nid} ({ne.get('class_type')}): {e.get('message')} — {e.get('details', '')}".strip())
        return "ComfyUI validation FAILED:\n" + "\n".join(f"- {l}" for l in lines)


@dataclass
class RunResult:
    ok: bool
    output_files: list[Path] = field(default_factory=list)
    error: str | None = None
    seconds: float = 0.0


class ComfyClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188", output_dir: Path | None = None):
        self.base = base_url.rstrip("/")
        self.output_dir = output_dir
        self._object_info: dict | None = None

    def _req(self, path: str, payload: dict | None = None, timeout: float = 60):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:  # ComfyUI returns 400 with a JSON body on invalid prompts
            body = e.read()
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                raise RuntimeError(f"HTTP {e.code} from {path}: {body[:300]!r}") from e

    def object_info(self) -> dict:
        if self._object_info is None:
            self._object_info = self._req("/object_info")
        return self._object_info

    def validate(self, prompt: dict) -> ValidationResult:
        r = self._req("/atelier/validate", {"prompt": prompt})
        return ValidationResult(r.get("valid", False), r.get("error"), r.get("node_errors") or {})

    def run(self, prompt: dict, timeout: float = 180) -> RunResult:
        t0 = time.monotonic()
        client_id = uuid.uuid4().hex
        r = self._req("/prompt", {"prompt": prompt, "client_id": client_id})
        if "prompt_id" not in r:
            err = r.get("error", {})
            return RunResult(False, error=f"rejected: {err.get('type')}: {err.get('message')}",
                             seconds=time.monotonic() - t0)
        pid = r["prompt_id"]
        while time.monotonic() - t0 < timeout:
            h = self._req(f"/history/{pid}")
            if pid in h:
                rec = h[pid]
                status = rec.get("status", {})
                if status.get("status_str") == "error":
                    msg = next((m[1].get("exception_message") for m in status.get("messages", [])
                                if m[0] == "execution_error"), "execution error")
                    return RunResult(False, error=f"execution_error: {str(msg).strip()[:300]}",
                                     seconds=time.monotonic() - t0)
                files = []
                for out in rec.get("outputs", {}).values():
                    for img in out.get("images", []):
                        if img.get("type") == "output" and self.output_dir is not None:
                            files.append(self.output_dir / img.get("subfolder", "") / img["filename"])
                return RunResult(True, files, seconds=time.monotonic() - t0)
            time.sleep(0.2)
        return RunResult(False, error="timeout", seconds=time.monotonic() - t0)
