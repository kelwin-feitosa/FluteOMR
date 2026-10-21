"""Orquestração do laboratório sem renderizador externo nem dados privados."""

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import tools.evaluate_music as lab

DATA = Path(__file__).parent / "data" / "music_lab"


def _manifest(tmp_path, examples):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"format_version": 1, "examples": examples}))
    return path


def _example(**changes):
    row = {
        "id": "example",
        "image": "page.png",
        "reference": "reference.musicxml",
        "origin": "own_exercise",
        "split": "development",
        "reference_status": "draft",
        "work_id": "work-a",
        "configured": {"measure_left": 110, "measure_right": 410},
    }
    return {**row, **changes}


def test_missing_human_reference_is_explicit_without_inventing_ground_truth(tmp_path):
    image = DATA / "raster" / "dev_down_flags-300.png"
    row = _example(
        image=image.name,
        reference=None,
        reference_status="missing",
        configured={"measure_left": 30, "measure_right": 350},
    )
    report = lab.evaluate_manifest(_manifest(tmp_path, [row]), image.parent)[0]
    assert report["evaluation"] == "not_evaluated"
    assert report["evaluation_reason"] == "missing_human_reference"
    assert report["predicted_events"] == 4
    assert "reference_events" not in report


def test_batch_preserves_failed_image_and_its_known_reference_denominator(tmp_path):
    (tmp_path / "reference.musicxml").write_bytes(
        (DATA / "dev_down_flags.musicxml").read_bytes()
    )
    examples = [_example(reference_status="source_authored"), _example(id="second")]
    rows = lab.evaluate_manifest(
        _manifest(tmp_path, examples), tmp_path, continue_on_error=True
    )
    assert len(rows) == 2
    assert all(row["processing_error"] for row in rows)
    assert rows[0]["reference_events"] == 4
    assert rows[0]["reference_measures"] == 1
    assert rows[0]["evaluation"] == rows[1]["evaluation"] == "not_evaluated"
    summary = lab.summarize_results(rows)
    assert summary["processing_failures"] == 2
    assert summary["reference_events"] == 4
    assert summary["complete_matches"] == 0
    assert summary["unevaluated_reference_events"] == 4
    assert summary["measures"]["total"] == 1
    assert summary["measures"]["unevaluable"] == 1


def test_variants_are_not_counted_as_independent_musical_works():
    rows = [
        {
            "id": str(i),
            "work_id": "same-work",
            "split": "development",
            "reference_status": "missing",
            "evaluation": "not_evaluated",
        }
        for i in range(3)
    ]
    summary = lab.summarize_results(rows)
    assert summary["images"] == 3
    assert summary["musical_works"] == 1
    assert summary["match_fraction"] == "not_evaluated"


def test_perfect_and_failed_images_keep_both_measure_denominators(tmp_path):
    source = DATA / "raster" / "dev_down_flags-300.png"
    (tmp_path / "page.png").write_bytes(source.read_bytes())
    (tmp_path / "reference.musicxml").write_bytes(
        (DATA / "dev_down_flags.musicxml").read_bytes()
    )
    configured = {"measure_left": 30, "measure_right": 350}
    examples = [
        _example(reference_status="source_authored", configured=configured),
        _example(
            id="failed",
            image="missing.png",
            reference_status="source_authored",
            configured=configured,
        ),
    ]
    rows = lab.evaluate_manifest(
        _manifest(tmp_path, examples), tmp_path, continue_on_error=True
    )
    summary = lab.summarize_results(rows)
    assert summary["match_fraction"] == {"matched": 4, "expected": 8}
    assert summary["reference_measures"] == 2
    assert summary["measures"] == {
        "correct": 1,
        "incorrect": 0,
        "unevaluable": 1,
        "total": 2,
    }


def test_cli_records_failed_batch_and_returns_nonzero(tmp_path):
    (tmp_path / "reference.musicxml").write_bytes(
        (DATA / "dev_down_flags.musicxml").read_bytes()
    )
    manifest = _manifest(tmp_path, [_example(reference_status="source_authored")])
    report = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.evaluate_music",
            "--manifest",
            str(manifest),
            "--images-dir",
            str(tmp_path),
            "--continue-on-error",
            "--summary",
            "--report",
            str(report),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    data = json.loads(report.read_text())
    assert data["summary"]["processing_failures"] == 1
    assert data["summary"]["reference_events"] == 4
    assert data["summary"]["measures"]["unevaluable"] == 1


def test_split_filter_does_not_open_reserved_images(tmp_path):
    path = _manifest(
        tmp_path, [_example(split="test", reference_status="source_authored")]
    )
    assert lab.evaluate_manifest(path, tmp_path, splits={"development"}) == []


def test_lab_dispatches_actual_two_measure_image_without_reading_draft_reference(
    tmp_path,
):
    image = Image.new("RGB", (760, 215), "white")
    draw = ImageDraw.Draw(image)
    for y in (74, 90, 106, 122, 138):
        draw.line((25, y, 735, y), fill="black", width=2)
    draw.line((380, 74, 380, 138), fill="black", width=2)
    for x, degree, hollow in (
        (140, 0, False),
        (210, 1, False),
        (280, 2, True),
        (460, 3, False),
        (530, 4, False),
        (625, 5, True),
    ):
        y = 138 - degree * 8
        draw.ellipse(
            (x - 10, y - 7, x + 10, y + 7),
            fill="white" if hollow else "black",
            outline="black",
            width=2,
        )
        sx = x + 9 if degree <= 4 else x - 9
        draw.line((sx, y, sx, y - 54 if degree <= 4 else y + 54), fill="black", width=2)
    image.save(tmp_path / "page.png")
    example = _example(
        configured={"measure_left": 110, "measure_right": 700, "auto_bars": True}
    )
    row = lab.evaluate_manifest(_manifest(tmp_path, [example]), tmp_path)[0]
    assert row["predicted_measures"] == 2
    assert row["predicted_events"] == 6
    assert row["evaluation"] == "not_evaluated"
    assert row["xml_export"] == "well_formed_not_schema_validated"
