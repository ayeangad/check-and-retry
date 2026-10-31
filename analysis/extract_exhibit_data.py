"""Extract the data Hyde embedded in the interactive exhibits of https://hyde.ai/blog/atelier.

The article's charts are iframes whose `srcdoc` carries JSON literals (`const D = {...}`,
`const SCORESETS = {...}`, `const GDSETS = {...}`) built from "Benchmark data - all scoring
methods.xlsx". This script pulls those literals out verbatim; it does not alter any value.

Usage: python analysis/extract_exhibit_data.py data/raw/hyde-atelier-2026-10-30.html data/derived/atelier_data.json
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

LITERALS = ("D", "SCORESETS", "GDSETS", "DUMMY")


def _decode_literal(src: str, name: str):
    m = re.search(r"(?:const|let|var)\s+" + re.escape(name) + r"\s*=\s*", src)
    if not m or src[m.end()] not in "[{":
        return None
    obj, _ = json.JSONDecoder().raw_decode(src[m.end():])
    return obj


def _scoring_methods(src: str) -> list[dict]:
    """SCORING_METHODS is a JS (not JSON) literal; pull key/name/rule with a regex."""
    block = re.search(r"SCORING_METHODS\s*=\s*\[(.*?)\];", src, flags=re.S)
    if not block:
        return []
    fields = ("key", "name", "rule")
    out = []
    for entry in re.findall(r"\{(.*?)\}", block.group(1), flags=re.S):
        rec = {f: (re.search(f + r':"(.*?)"', entry) or [None, None])[1] for f in fields}
        out.append(rec)
    return out


def extract(page_html: str) -> dict:
    docs = [html.unescape(d) for d in re.findall(r'srcdoc="(.*?)"\s+sandbox', page_html, flags=re.S)]
    if not docs:
        raise ValueError("no exhibit iframes found")
    out: dict = {"n_iframes": len(docs)}
    for doc in docs:
        for name in LITERALS:
            if name not in out:
                val = _decode_literal(doc, name)
                if val is not None:
                    out[name] = val
        if "SCORING_METHODS" not in out:
            sm = _scoring_methods(doc)
            if sm:
                out["SCORING_METHODS"] = sm
    missing = [n for n in ("D", "SCORESETS", "GDSETS") if n not in out]
    if missing:
        raise ValueError(f"missing literals: {missing}")
    return out


def main(argv: list[str]) -> None:
    src, dst = Path(argv[1]), Path(argv[2])
    data = extract(src.read_text(encoding="utf-8"))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(data, indent=1))
    d = data["D"]
    print(f"wrote {dst}: nTasks={d['nTasks']} attempts={d['attempts']} models={len(d['models'])} "
          f"methods={[m['key'] for m in data.get('SCORING_METHODS', [])]}")


if __name__ == "__main__":
    main(sys.argv)
