"""Brief / task model for the independent mini-benchmark.

A Brief carries the natural-language text handed to the agent plus a machine-readable `Spec`
holding only the *objectively checkable* claims. These are the categories Hyde's article calls
Delivery Format Specs and Matches Reference / Stays Unchanged (logo reproduced exactly). Every
spec field is stated explicitly in the brief text, so the spec adds no hidden information. It
is a structured copy of what the brief already says, the same role Hyde's designer-verified
claims list plays.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

Corner = Literal["top-left", "top-right", "bottom-left", "bottom-right"]


@dataclass(frozen=True)
class LogoSpec:
    file: str                    # filename in ComfyUI's input dir
    corner: Corner
    max_margin_frac: float = 0.25  # logo bbox must lie within this fraction of width/height from the corner


@dataclass(frozen=True)
class ReferenceSpec:
    file: str
    keep_composition: bool = True


@dataclass(frozen=True)
class Spec:
    width: int
    height: int
    n_outputs: int = 1
    logo: LogoSpec | None = None
    reference: ReferenceSpec | None = None

    def claims(self) -> list[str]:
        out = ["delivery_size", "single_output"]
        if self.logo:
            out += ["logo_exact", "logo_position"]
        if self.reference:
            out += ["reference_composition"]
        return out


@dataclass(frozen=True)
class Brief:
    id: str
    family: str
    text: str
    spec: Spec
    inputs: dict[str, str] = field(default_factory=dict)  # role -> filename

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_dict(d: dict) -> "Brief":
        s = d["spec"]
        spec = Spec(width=s["width"], height=s["height"], n_outputs=s.get("n_outputs", 1),
                    logo=LogoSpec(**s["logo"]) if s.get("logo") else None,
                    reference=ReferenceSpec(**s["reference"]) if s.get("reference") else None)
        return Brief(d["id"], d["family"], d["text"], spec, d.get("inputs", {}))


def load_briefs(path: Path) -> list[Brief]:
    return [Brief.from_dict(json.loads(l)) for l in path.read_text().splitlines() if l.strip()]
