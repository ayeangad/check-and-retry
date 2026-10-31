"""Adversarial cases written during the self-audit (research/05). Each documents a known
behaviour, including the ones that are limitations rather than successes."""
import copy
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atelier_poc.brief_contract import check  # noqa: E402
from atelier_poc.briefs import Brief, LogoSpec, ReferenceSpec, Spec  # noqa: E402
from atelier_poc.reference_workflows import build_correct, set_input_dir  # noqa: E402


@pytest.fixture
def inp(tmp_path):
    Image.fromarray(np.full((60, 200, 3), 200, np.uint8)).save(tmp_path / "logo.png")
    Image.fromarray(np.full((768, 1024, 3), 90, np.uint8)).save(tmp_path / "ref.png")
    set_input_dir(tmp_path)
    return tmp_path


def brief(ref=False, corner="top-left", w=1080, h=1350):
    return Brief("t", "f", "", Spec(w, h, 1, LogoSpec("logo.png", corner), ReferenceSpec("ref.png") if ref else None),
                 {})


def claims(rep):
    return {v.claim for v in rep.violations}


def test_letterbox_onto_larger_canvas_is_understood(inp):
    """Generate 1024x1024, paste onto an exact-size EmptyImage canvas, then paste the logo: valid."""
    b = brief()
    g = build_correct(b, inp)
    g["7"] = {"class_type": "EmptyImage", "inputs": {"width": 1080, "height": 1350, "batch_size": 1, "color": 0}}
    g["8"] = {"class_type": "ImageCompositeMasked", "inputs": {"destination": ["7", 0], "source": ["6", 0],
                                                               "x": 28, "y": 163, "resize_source": False}}
    g["21"]["inputs"]["destination"] = ["8", 0]
    assert check(g, b.spec, inp).ok


def test_denoise_from_linked_primitive_abstains(inp):
    """denoise fed by a link instead of a literal: we cannot read it, so we must not guess."""
    b = brief(ref=True)
    g = build_correct(b, inp)
    g["50"] = {"class_type": "PrimitiveFloat", "inputs": {"value": 0.6}}
    g["5"]["inputs"]["denoise"] = ["50", 0]
    rep = check(g, b.spec, inp)
    assert "reference_composition" not in claims(rep)
    assert rep.verdicts(b.spec)["reference_composition"] is None


def test_unmodelled_geometry_node_abstains(inp):
    b = brief()
    g = build_correct(b, inp)
    g["8"] = {"class_type": "ImageFlip", "inputs": {"image": ["21", 0], "flip_method": "x-axis"}}
    g["9"]["inputs"]["images"] = ["8", 0]
    rep = check(g, b.spec, inp)
    assert rep.violations == []
    assert rep.verdicts(b.spec)["delivery_size"] is None


def test_known_limitation_logo_copy_under_other_filename(inp):
    """LIMITATION: the same logo pixels under another filename are reported as 'never loaded'.
    The contract binds to the supplied file, as a brief does ("the logo from Input 2"), but a
    pixel-identical copy is a false alarm. Kept as a documented limitation."""
    shutil.copy(inp / "logo.png", inp / "logo_copy.png")
    b = brief()
    g = build_correct(b, inp)
    g["20"]["inputs"]["image"] = "logo_copy.png"
    assert "logo_exact" in claims(check(g, b.spec, inp))


def test_known_limitation_composite_overlap_not_tracked(inp):
    """LIMITATION: a later composite that paints OVER the logo is not detected (only geometry of
    the destination is tracked, not occlusion by later sources)."""
    b = brief()
    g = build_correct(b, inp)
    g["30"] = {"class_type": "EmptyImage", "inputs": {"width": 400, "height": 200, "batch_size": 1, "color": 0}}
    g["31"] = {"class_type": "ImageCompositeMasked", "inputs": {"destination": ["21", 0], "source": ["30", 0],
                                                                "x": 0, "y": 0, "resize_source": False}}
    g["9"]["inputs"]["images"] = ["31", 0]
    assert check(g, b.spec, inp).ok          # documents the false negative


def test_string_numbers_are_tolerated(inp):
    b = brief()
    g = build_correct(b, inp)
    g["7"]["inputs"]["width"], g["7"]["inputs"]["height"] = "1080", "1350"
    assert check(g, b.spec, inp).ok


def test_garbage_graph_does_not_crash(inp):
    for g in [{}, {"1": "notanode"}, {"1": {"class_type": "SaveImage", "inputs": {"images": ["404", 0]}}},
              {"1": {"class_type": "SaveImage", "inputs": {}}}]:
        rep = check(g, brief().spec, inp)
        assert rep is not None


def test_large_graph_latency(inp):
    """500-node chain of no-op resizes: verifier must stay fast (memoised traversal)."""
    import time
    b = brief()
    g = build_correct(b, inp)
    prev = "6"
    for i in range(500):
        nid = str(1000 + i)
        g[nid] = {"class_type": "ImageScale", "inputs": {"image": [prev, 0], "width": 1024, "height": 1024,
                                                          "upscale_method": "nearest-exact", "crop": "disabled"}}
        prev = nid
    g["7"]["inputs"]["image"] = [prev, 0]
    t0 = time.perf_counter()
    rep = check(copy.deepcopy(g), b.spec, inp)
    assert rep.ok and time.perf_counter() - t0 < 0.5
