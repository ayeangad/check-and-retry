"""Experiment D: output_retry_rich gets the same logo coordinates the contract gives; D-A states the logo size."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))
from atelier_poc.briefs import load_briefs  # noqa: E402
from atelier_poc.harness import ARMS, describe_output_failures  # noqa: E402
from run_e2 import with_logo_size  # noqa: E402

BRIEFS = ROOT / "tasks_long/briefs.jsonl"
INPUT = ROOT / "comfy_base/input"


def _l09():
    return next(b for b in load_briefs(BRIEFS) if b.id == "L09_t2i_logo")


def test_rich_feedback_matches_contract_coordinates():
    b = _l09()
    out = SimpleNamespace(claims={"delivery_size": True, "single_output": True, "logo_exact": True,
                                  "logo_position": False}, details={"logo_pos": [[64, 48]]})
    plain = describe_output_failures(b.spec, out)
    rich = describe_output_failures(b.spec, out, INPUT)
    assert "x=" not in plain
    # the contract told the agent "fix: set the ImageCompositeMasked x=1348, y=32" on this brief (E2 transcript)
    assert "220x64" in rich and "x=1348, y=32" in rich


def test_logo_size_stated_only_for_logo_briefs():
    bs = load_briefs(BRIEFS)
    logo = with_logo_size(_l09(), INPUT)
    assert logo.text.endswith("(The logo file L09_t2i_logo_logo.png is 220x64 pixels.)")
    nologo = next(b for b in bs if b.spec.logo is None)
    assert with_logo_size(nologo, INPUT).text == nologo.text


def test_new_arm_registered():
    assert "output_retry_rich" in ARMS
