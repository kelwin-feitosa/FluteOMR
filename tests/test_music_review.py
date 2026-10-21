"""Referências humanas são distintas de sugestões e vinculadas aos arquivos."""

import json
from pathlib import Path

import pytest
from PIL import Image

from fluteomr.music_review import confirm_review, prepare_review, verify_review
from tools.evaluate_music import evaluate_manifest

DATA = Path(__file__).parent / "data/music_lab"


def _bundle(tmp_path):
    source = tmp_path / "original.png"
    Image.new("RGB", (500, 220), "white").save(source)
    reference = DATA / "dev_down_flags.musicxml"
    manifest = prepare_review(
        source,
        tmp_path / "review",
        example_id="own-case",
        crop=(20, 30, 420, 180),
        scale=2,
        reference=reference,
        measures=(1,),
        staff_id="s0",
        system_id=None,
        configured={
            "clef": "treble",
            "time": "4/4",
            "measure_left": 10,
            "measure_right": 700,
        },
    )
    return source, manifest


def test_prepare_crop_and_reference_stay_draft_with_source_mapping(tmp_path):
    source, manifest = _bundle(tmp_path)
    row = json.loads(manifest.read_text())["examples"][0]
    review = verify_review(manifest, row)
    assert row["reference_status"] == "draft"
    assert review["status"] == "draft"
    assert review["source"]["sha256"]
    assert review["source"]["crop"] == [20, 30, 420, 180]
    assert review["image"]["size"] == [800, 300]
    assert not Path(review["source"]["path"]).is_absolute()
    assert review["scope"]["staff_id"] == "s0"
    assert review["scope"]["system_id"] is None
    assert source.exists()
    report = evaluate_manifest(manifest, manifest.parent, continue_on_error=True)[0]
    assert report["evaluation"] == "not_evaluated"
    assert report["reference_status"] == "draft"


def test_confirmation_requires_action_and_seals_candidate_hash(tmp_path):
    _, manifest = _bundle(tmp_path)
    with pytest.raises(ValueError, match="revisão"):
        confirm_review(manifest, reviewer="tester", confirm_reviewed=False)
    confirm_review(manifest, reviewer="tester", confirm_reviewed=True)
    row = json.loads(manifest.read_text())["examples"][0]
    review = verify_review(manifest, row)
    assert row["reference_status"] == review["status"] == "validated"
    assert review["reviewer"] == "tester"
    reference = manifest.parent / row["reference"]
    reference.write_bytes(
        reference.read_bytes().replace(b"<step>C</step>", b"<step>D</step>") + b"\n"
    )
    with pytest.raises(ValueError, match="hash.*referência"):
        verify_review(manifest, row)
    with pytest.raises(ValueError, match="hash.*referência"):
        evaluate_manifest(manifest, manifest.parent, continue_on_error=True)


def test_source_mutation_and_overwrite_are_rejected(tmp_path):
    source, manifest = _bundle(tmp_path)
    with pytest.raises(FileExistsError):
        _bundle(tmp_path)
    source.write_bytes(b"changed")
    row = json.loads(manifest.read_text())["examples"][0]
    with pytest.raises(ValueError, match="hash.*origem"):
        verify_review(manifest, row)


def test_missing_candidate_cannot_be_confirmed(tmp_path):
    source = tmp_path / "page.png"
    Image.new("L", (200, 150), 255).save(source)
    manifest = prepare_review(
        source,
        tmp_path / "review",
        example_id="pending",
        crop=(0, 0, 200, 150),
        scale=1,
        reference=None,
        measures=(1, 2),
        staff_id=None,
        system_id=None,
        configured={"measure_left": 0, "measure_right": 199},
    )
    with pytest.raises(ValueError, match="referência"):
        confirm_review(manifest, reviewer="tester", confirm_reviewed=True)


def test_review_rejects_changed_image_and_candidate_scope(tmp_path):
    _, manifest = _bundle(tmp_path)
    row = json.loads(manifest.read_text())["examples"][0]
    image = manifest.parent / row["image"]
    Image.new("RGB", (800, 300), "black").save(image)
    with pytest.raises(ValueError, match="hash.*imagem"):
        verify_review(manifest, row)
    with pytest.raises(ValueError, match="compassos"):
        prepare_review(
            tmp_path / "original.png",
            tmp_path / "bad",
            example_id="bad",
            crop=(0, 0, 400, 180),
            scale=1,
            reference=DATA / "dev_down_flags.musicxml",
            measures=(1, 2),
            staff_id=None,
            system_id=None,
            configured={},
        )


def test_transparent_background_is_rendered_on_white(tmp_path):
    source = tmp_path / "transparent.png"
    Image.new("RGBA", (40, 40), (0, 0, 0, 0)).save(source)
    manifest = prepare_review(
        source,
        tmp_path / "review",
        example_id="transparent",
        crop=(0, 0, 40, 40),
        scale=1,
        reference=None,
        measures=(1,),
        staff_id=None,
        system_id=None,
        configured={"measure_left": 0, "measure_right": 39},
    )
    row = json.loads(manifest.read_text())["examples"][0]
    with Image.open(manifest.parent / row["image"]) as image:
        assert image.getpixel((20, 20)) == (255, 255, 255)
    assert verify_review(manifest, row)["status"] == "draft"


def test_explicitly_reviewed_fixture_uses_existing_musical_evaluator(tmp_path):
    source = DATA / "raster/dev_down_flags-300.png"
    with Image.open(source) as image:
        crop = (0, 0, image.width, image.height)
    manifest = prepare_review(
        source,
        tmp_path / "review",
        example_id="fixture",
        crop=crop,
        scale=1,
        reference=DATA / "dev_down_flags.musicxml",
        measures=(1,),
        staff_id="s0",
        system_id=None,
        configured={"measure_left": 30, "measure_right": 350},
    )
    confirm_review(manifest, reviewer="automated-test-fixture", confirm_reviewed=True)
    row = evaluate_manifest(manifest, manifest.parent)[0]
    assert row["evaluation"]["matches"] == row["evaluation"]["reference_events"] == 4


def test_invalid_candidate_xml_is_reported_without_promoting_draft(tmp_path):
    _, manifest = _bundle(tmp_path)
    row = json.loads(manifest.read_text())["examples"][0]
    (manifest.parent / row["reference"]).write_text("<score-partwise>")
    with pytest.raises(ValueError, match="MusicXML"):
        verify_review(manifest, row)
    assert (
        json.loads(manifest.read_text())["examples"][0]["reference_status"] == "draft"
    )
