"""Detecção geométrica em PDF: somente contagem de pautas, sem precisão falsa."""

import json

import pytest
from PIL import Image

from fluteomr.staff_detection import DetectionResult, Region, Staff, StaffLine
from tools import real_staff_baseline


def _detected():
    lines = tuple(StaffLine(10, 140, y, 1) for y in (25, 35, 45, 55, 65))
    staff = Staff(lines, 10.0, Region(10, 25, 140, 65))
    return DetectionResult(160, 120, "detected", (staff,), lines, 125, ())


def test_staff_baseline_has_no_music_accuracy_without_ground_truth(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(real_staff_baseline, "pdf_page_count", lambda _: 5)
    monkeypatch.setattr(
        real_staff_baseline,
        "load_pdf_page",
        lambda *_a, **_kw: Image.new("RGB", (160, 120), "white"),
    )
    monkeypatch.setattr(real_staff_baseline, "detect_staffs", lambda _: _detected())
    report = tmp_path / "baseline.json"
    preview = tmp_path / "previews"
    result = real_staff_baseline.benchmark_pdf_staffs(
        tmp_path / "source.pdf",
        page_numbers=[1, 3],
        resolutions=[150, 200],
        report=report,
        preview_dir=preview,
    )
    assert json.loads(report.read_text()) == result
    assert result["total_pdf_pages"] == 5
    assert len(result["samples"]) == 4
    assert all(row["staff_count_detected"] == 1 for row in result["samples"])
    assert all(row["reference_staff_count"] is None for row in result["samples"])
    assert all(row["musical_event_accuracy"] == "not_evaluated" for row in result["samples"])
    assert len(list(preview.glob("*.png"))) == 4
    with pytest.raises(FileExistsError):
        real_staff_baseline.benchmark_pdf_staffs(
            tmp_path / "source.pdf",
            page_numbers=[1, 3],
            resolutions=[150, 200],
            report=report,
        )


@pytest.mark.parametrize(
    ("pages", "dpis"),
    [
        ([], [150]),
        ([1], []),
        ([0], [150]),
        ([6], [150]),
        ([1, 1], [150]),
        ([1], [150, 150]),
        ([1], [40]),
        ([1], [500]),
        ([1], [True]),
    ],
)
def test_invalid_scoped_benchmark_fails_before_rendering(
    tmp_path, monkeypatch, pages, dpis
):
    monkeypatch.setattr(real_staff_baseline, "pdf_page_count", lambda _: 5)
    monkeypatch.setattr(
        real_staff_baseline,
        "load_pdf_page",
        lambda *_a, **_kw: pytest.fail("nunca rasterizar parâmetros inválidos"),
    )
    with pytest.raises(ValueError):
        real_staff_baseline.benchmark_pdf_staffs(
            tmp_path / "source.pdf", page_numbers=pages, resolutions=dpis
        )
