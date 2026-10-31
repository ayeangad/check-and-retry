import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atelier_poc.briefs import LogoSpec, ReferenceSpec, Spec  # noqa: E402
from atelier_poc.evaluator import evaluate, find_exact_patch  # noqa: E402
from atelier_poc.harness import _coerce_workflow, extract_json  # noqa: E402

rng = np.random.default_rng(0)


def _save(p, arr):
    Image.fromarray(arr.astype(np.uint8)).save(p)
    return p


def test_find_exact_patch_locates_and_rejects_resampled():
    img = rng.integers(0, 256, (300, 400, 3)).astype(np.float32)
    patch = img[50:90, 120:220].copy()
    assert find_exact_patch(img, patch) == (120, 50)
    blurred = (patch + np.roll(patch, 1, axis=1)) / 2
    assert find_exact_patch(img, blurred) is None


def test_evaluate_logo_corner_and_size(tmp_path):
    logo = rng.integers(0, 256, (20, 50, 3))
    _save(tmp_path / "logo.png", logo)
    canvas = rng.integers(0, 256, (200, 300, 3))
    canvas[10:30, 240:290] = logo                       # top-right
    out = _save(tmp_path / "out.png", canvas)
    o = evaluate(Spec(300, 200, 1, LogoSpec("logo.png", "top-right")), [out], tmp_path, True)
    assert o.all_pass, o.claims
    o2 = evaluate(Spec(300, 200, 1, LogoSpec("logo.png", "bottom-left")), [out], tmp_path, True)
    assert o2.claims["logo_exact"] and not o2.claims["logo_position"]
    o3 = evaluate(Spec(310, 200, 1, LogoSpec("logo.png", "top-right")), [out], tmp_path, True)
    assert not o3.claims["delivery_size"]


def test_evaluate_reference_composition(tmp_path):
    ref = np.zeros((100, 100, 3)); ref[:, :50] = 255
    _save(tmp_path / "ref.png", ref)
    same = _save(tmp_path / "same.png", np.kron(ref, np.ones((2, 2, 1))))
    noise = _save(tmp_path / "noise.png", rng.integers(0, 256, (200, 200, 3)))
    spec = Spec(200, 200, 1, None, ReferenceSpec("ref.png"))
    assert evaluate(spec, [same], tmp_path, True).claims["reference_composition"]
    assert not evaluate(spec, [noise], tmp_path, True).claims["reference_composition"]


def test_not_executed_fails_all_claims(tmp_path):
    o = evaluate(Spec(10, 10), [], tmp_path, False)
    assert o.score == 0 and not o.all_pass


def test_extract_json_variants():
    assert extract_json('```json\n{"1": {"class_type": "X", "inputs": {}}}\n```') == {"1": {"class_type": "X", "inputs": {}}}
    assert extract_json('Here you go: {"a": 1} hope it helps') == {"a": 1}
    assert extract_json("no json") is None


def test_coerce_workflow_unwraps():
    wf = {"1": {"class_type": "X", "inputs": {}}}
    assert _coerce_workflow(wf) == wf
    assert _coerce_workflow({"workflow": wf}) == wf
    assert _coerce_workflow({"workflow": '{"1": {"class_type": "X", "inputs": {}}}'}) == wf
    assert _coerce_workflow("garbage") is None
