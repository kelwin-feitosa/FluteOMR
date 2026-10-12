"""Fluxo de sugestões e confirmação, com imagem sintética independente."""

import json
import subprocess
import sys

from PIL import Image, ImageDraw

from fluteomr.annotations import image_sha256


def command(*args):
    return subprocess.run(
        [sys.executable, "-m", "tools.evaluate_annotations", *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def make_image(path):
    image = Image.new("L", (400, 160), 255)
    draw = ImageDraw.Draw(image)
    for y in (40, 50, 60, 70, 80):
        draw.line((20, y, 380, y), fill=0)
    image.save(path)


def test_suggestions_remain_unvalidated_until_manual_confirmation(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    image_path = images / "controlled.png"
    make_image(image_path)
    suggestions = tmp_path / "suggestions"
    run = command(
        "suggest",
        "--images-dir",
        images,
        "--image",
        image_path.name,
        "--output-dir",
        suggestions,
    )
    assert run.returncode == 0, run.stderr
    proposal = json.loads((suggestions / "controlled.png.suggestions.json").read_text())
    draft_path = suggestions / "controlled.png.reference-draft.json"
    draft = json.loads(draft_path.read_text())
    assert proposal["kind"] == "suggestions_not_ground_truth"
    assert proposal["image"]["sha256"] == image_sha256(image_path)
    assert proposal["detections"]["staffs"]
    assert draft["review"]["status"] == "draft"
    assert draft["staffs"][0]["review_state"] == "unknown"
    assert (suggestions / "controlled.png.review.png").is_file()
    assert (
        command("check", "--annotation", draft_path, "--images-dir", images).returncode
        == 0
    )

    empty_report = tmp_path / "empty-report.json"
    run = command(
        "evaluate",
        "--annotations-dir",
        suggestions,
        "--images-dir",
        images,
        "--report",
        empty_report,
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(empty_report.read_text())["status"] == "not_evaluable"

    confirmed = tmp_path / "controlled.reference.json"
    run = command(
        "confirm",
        "--annotation",
        draft_path,
        "--images-dir",
        images,
        "--output",
        confirmed,
        "--reviewer",
        "test-reviewer",
        "--confirm-reviewed",
    )
    assert run.returncode == 2
    assert not confirmed.exists()

    # Coordenadas anotadas do desenho controlado, sem copiar a predição.
    draft["split"] = "test"
    draft["coverage"] = {
        "staffs": "complete",
        "systems": "complete",
        "clefs": "complete",
    }
    draft["staffs"] = [
        {
            "id": "known-staff",
            "order": 0,
            "review_state": "confirmed",
            "region": {"left": 20, "top": 40, "right": 380, "bottom": 80},
            "lines": [
                {"x_start": 20, "x_end": 380, "y": y} for y in (40, 50, 60, 70, 80)
            ],
        }
    ]
    draft["systems"] = [
        {
            "id": "known-system",
            "order": 0,
            "staff_ids": ["known-staff"],
            "review_state": "confirmed",
            "partial_visible": False,
        }
    ]
    draft["clefs"] = [
        {"staff_id": "known-staff", "state": "absent", "kind": None, "region": None}
    ]
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    run = command(
        "confirm",
        "--annotation",
        draft_path,
        "--images-dir",
        images,
        "--output",
        confirmed,
        "--reviewer",
        "test-reviewer",
        "--confirm-reviewed",
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(confirmed.read_text())["review"]["status"] == "validated"
    report_path = tmp_path / "report.json"
    errors = tmp_path / "errors"
    run = command(
        "evaluate",
        "--annotation",
        confirmed,
        "--images-dir",
        images,
        "--report",
        report_path,
        "--errors-dir",
        errors,
    )
    assert run.returncode == 0, run.stderr
    report = json.loads(report_path.read_text())
    assert report["references_evaluated"] == 1
    assert report["images"][0]["staffs"]["tp"] == 1
    assert report["by_split"]["test"]["staffs"]["tp"] == 1
    assert report["by_split"]["development"]["staffs"]["precision"] == "not_evaluable"
    assert (errors / "controlled.png.errors.png").is_file()


def test_cli_rejects_missing_image_hash_mismatch_and_invalid_json(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    run = command(
        "evaluate",
        "--annotations-dir",
        tmp_path / "absent-references",
        "--images-dir",
        images,
    )
    assert run.returncode == 3
    suggestions = tmp_path / "suggestions"
    run = command(
        "suggest",
        "--images-dir",
        images,
        "--image",
        "missing.png",
        "--output-dir",
        suggestions,
    )
    assert run.returncode == 3
    assert not suggestions.exists()
    image_path = images / "controlled.png"
    make_image(image_path)
    run = command(
        "suggest",
        "--images-dir",
        images,
        "--image",
        image_path.name,
        "--output-dir",
        suggestions,
    )
    assert run.returncode == 0
    draft = suggestions / "controlled.png.reference-draft.json"
    Image.new("L", (400, 160), 100).save(image_path)
    run = command("check", "--annotation", draft, "--images-dir", images)
    assert run.returncode == 2
    assert "hash SHA-256 diferente" in run.stderr
    malformed = tmp_path / "invalid.reference.json"
    malformed.write_text("{bad json", encoding="utf-8")
    assert (
        command("check", "--annotation", malformed, "--images-dir", images).returncode
        == 2
    )
