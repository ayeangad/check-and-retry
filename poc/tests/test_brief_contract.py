import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atelier_poc.brief_contract import check  # noqa: E402
from atelier_poc.briefs import Brief, LogoSpec, ReferenceSpec, Spec  # noqa: E402
from atelier_poc.reference_workflows import MUTATIONS, build_correct, set_input_dir  # noqa: E402


@pytest.fixture
def inp(tmp_path):
    Image.fromarray(np.full((60, 200, 3), 200, np.uint8)).save(tmp_path / "logo.png")
    Image.fromarray(np.full((768, 1024, 3), 90, np.uint8)).save(tmp_path / "ref.png")
    set_input_dir(tmp_path)
    return tmp_path


def t2i(w, h, extra=None, save_from="6"):
    g = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "x"}},
         "4": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
         "5": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "latent_image": ["4", 0], "denoise": 1.0}},
         "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
         "9": {"class_type": "SaveImage", "inputs": {"images": [save_from, 0]}}}
    g.update(extra or {})
    return g


def bad(rep):
    return {v.claim for v in rep.violations}


def test_latent_floors_non_multiple_of_8(inp):
    rep = check(t2i(1080, 1350), Spec(1080, 1350), inp)
    assert rep.predicted_outputs == [("9", 1080, 1344, 1)]
    assert bad(rep) == {"delivery_size"}
    assert "floors it to 1080x1344" in rep.render()


def test_final_image_scale_fixes_size(inp):
    g = t2i(896, 1152, {"7": {"class_type": "ImageScale", "inputs": {"image": ["6", 0], "width": 1080, "height": 1350,
                                                                      "upscale_method": "lanczos", "crop": "center"}}}, "7")
    assert check(g, Spec(1080, 1350), inp).ok


def test_image_scale_zero_keeps_aspect(inp):
    g = t2i(1024, 512, {"7": {"class_type": "ImageScale", "inputs": {"image": ["6", 0], "width": 0, "height": 300,
                                                                      "upscale_method": "nearest-exact", "crop": "disabled"}}}, "7")
    assert check(g, Spec(600, 300), inp).ok


def test_batch_counts_as_multiple_outputs(inp):
    g = t2i(1024, 1024)
    g["4"]["inputs"]["batch_size"] = 3
    assert bad(check(g, Spec(1024, 1024), inp)) == {"single_output"}


def test_no_save_image(inp):
    g = t2i(1024, 1024)
    del g["9"]
    assert bad(check(g, Spec(1024, 1024), inp)) == {"single_output"}


def test_unknown_node_abstains_not_false_alarm(inp):
    g = t2i(1024, 1024, {"7": {"class_type": "SomeCustomNodeWeHaveNoModelFor", "inputs": {"image": ["6", 0]}}}, "7")
    rep = check(g, Spec(1080, 1350), inp)
    assert rep.violations == []
    assert any("SomeCustomNodeWeHaveNoModelFor" in u for u in rep.unverified)
    assert rep.verdicts(Spec(1080, 1350))["delivery_size"] is None


def logo_brief(corner="top-left", ref=False):
    return Brief("t", "fam", "", Spec(1080, 1350, 1, LogoSpec("logo.png", corner),
                                     ReferenceSpec("ref.png") if ref else None),
                 {"logo": "logo.png", **({"reference": "ref.png"} if ref else {})})


@pytest.mark.parametrize("ref", [False, True])
def test_reference_solution_passes(inp, ref):
    b = logo_brief(ref=ref)
    assert check(build_correct(b, inp), b.spec, inp).ok


@pytest.mark.parametrize("name", sorted(MUTATIONS))
@pytest.mark.parametrize("ref", [False, True])
def test_mutations_flag_exactly_expected_claims(inp, name, ref):
    b = logo_brief(corner="bottom-right", ref=ref)
    r = MUTATIONS[name](build_correct(b, inp), b)
    if r is None:
        pytest.skip("mutation not applicable")
    g, expected = r
    assert bad(check(g, b.spec, inp)) == expected


def test_logo_as_destination_is_flagged(inp):
    b = logo_brief()
    g = build_correct(b, inp)
    g["21"]["inputs"]["destination"], g["21"]["inputs"]["source"] = ["20", 0], ["7", 0]
    assert "logo_exact" in bad(check(g, b.spec, inp))


def test_crop_that_keeps_logo_shifts_position(inp):
    b = Brief("t", "f", "", Spec(1000, 1300, 1, LogoSpec("logo.png", "top-left")), {})
    g = build_correct(logo_brief(), inp)                 # logo at (32,32) on 1080x1350
    g["8"] = {"class_type": "ImageCrop", "inputs": {"image": ["21", 0], "width": 1000, "height": 1300, "x": 10, "y": 10}}
    g["9"]["inputs"]["images"] = ["8", 0]
    rep = check(g, b.spec, inp)
    assert rep.ok, rep.render()


def test_crop_through_logo_is_flagged(inp):
    g = build_correct(logo_brief(), inp)
    g["8"] = {"class_type": "ImageCrop", "inputs": {"image": ["21", 0], "width": 1000, "height": 1300, "x": 100, "y": 0}}
    g["9"]["inputs"]["images"] = ["8", 0]
    assert "logo_exact" in bad(check(g, Spec(1000, 1300, 1, LogoSpec("logo.png", "top-left")), inp))


def test_malformed_inputs_do_not_crash(inp):
    g = t2i("wide", None)
    rep = check(g, Spec(1024, 1024), inp)
    assert rep.violations == [] and rep.unverified


def test_cycle_does_not_hang(inp):
    g = t2i(1024, 1024)
    g["5"]["inputs"]["latent_image"] = ["5", 0]
    rep = check(g, Spec(1024, 1024), inp)
    assert rep.unverified


def test_interpreter_abstentions_reach_report(inp):
    b = logo_brief(corner="bottom-right", ref=True)
    g = build_correct(b, inp)
    g["21"]["inputs"]["mask"] = ["20", 1]               # masked paste: pixels may be blended
    rep = check(g, b.spec, inp)
    assert any(u.startswith("logo_exact: mask") for u in rep.unverified)
    assert rep.verdicts(b.spec)["logo_exact"] is None
