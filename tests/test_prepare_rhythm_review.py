"""O material de revisão não finge validação musical ou ground truth."""

import csv
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from fluteomr.music import (
    Clef,
    Measure,
    MusicPart,
    MusicScore,
    Note,
    Pitch,
    TimeSignature,
)
from fluteomr.staff_detection import Region
from tools import prepare_rhythm_review


def _fake_score():
    diagnostics = (
        ("double_beam", "secondary_stripe_ambiguous"),
        ("double_beam", "secondary_stripe_ambiguous"),
        ("double_beam", "weak_secondary_stripe"),
        ("stem_not_confirmed",),
    )
    notes = tuple(
        Note(
            Pitch("E", 5),
            None,
            Region(60 + 25 * i, 70, 70 + 25 * i, 80),
            i // 2,
            "filled",
            diagnostics=diag,
            candidate_id=f"candidate-{i}",
        )
        for i, diag in enumerate(diagnostics)
    )
    measure = Measure(1, notes, TimeSignature(4, 4, "configuration"), "user")
    return MusicScore(
        (
            MusicPart(
                "P1", "Flute", "configuration", (0, 1),
                Clef("treble", "user"), (measure,),
            ),
        )
    )


def _prepare(tmp_path, monkeypatch):
    pdf = tmp_path / "published.pdf"
    pdf.write_bytes(b"%PDF-1.4\n1 0 obj\nendobj\n%%EOF\n")
    monkeypatch.setattr(
        prepare_rhythm_review,
        "load_pdf_page",
        lambda *_args, **_kwargs: Image.new("RGB", (300, 200), "white"),
    )
    monkeypatch.setattr(
        prepare_rhythm_review,
        "transcribe_page",
        lambda *_args, **_kwargs: SimpleNamespace(score=_fake_score()),
    )
    return pdf, tmp_path / "review"


def test_review_has_reproducible_public_image_crops_and_no_fake_accuracy(
    tmp_path, monkeypatch
):
    pdf, destination = _prepare(tmp_path, monkeypatch)
    result = prepare_rhythm_review.build_review_packet(
        pdf, destination, max_cases=3, dpi=120
    )
    assert result == json.loads((destination / "review-manifest.json").read_text())
    assert result["status"] == "review_packet_unreviewed"
    assert result["reference_quality"] == "none"
    assert result["case_count"] == 3
    assert result["total_proposed_events"] == 4
    assert result["unresolved_diagnostics"] == {
        "secondary_stripe_ambiguous": 2,
        "stem_not_confirmed": 1,
        "weak_secondary_stripe": 1,
    }
    for item in result["cases"]:
        assert (destination / item["crop_file"]).is_file()
        assert item["human_review_status"] == "unreviewed"
        assert item["ground_truth"] is None
        assert item["candidate_id"].startswith("candidate-")
        assert item["crop_bounds"][0] >= 0
        assert item["crop_bounds"][2] <= 300
    with (destination / "review-template.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 3
    assert all(row["status"] == "unreviewed" for row in rows)
    assert all(row["correct_duration"] == "" for row in rows)
    before = (destination / "review-manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        prepare_rhythm_review.build_review_packet(pdf, destination)
    assert (destination / "review-manifest.json").read_bytes() == before


@pytest.mark.parametrize("kwargs", [
    {"dpi": 50},
    {"dpi": 500},
    {"page": 0},
    {"max_cases": 0},
    {"max_cases": 60},
    {"max_cases": True},
])
def test_invalid_review_settings_never_publish_data(tmp_path, monkeypatch, kwargs):
    pdf, destination = _prepare(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        prepare_rhythm_review.build_review_packet(pdf, destination, **kwargs)
    assert not destination.exists()


def test_pdf_must_exist(tmp_path):
    with pytest.raises(ValueError, match="PDF local"):
        prepare_rhythm_review.build_review_packet(
            tmp_path / "missing.pdf", tmp_path / "review"
        )
