"""Página solo composta de rasters próprios; coordenadas sempre voltam à origem."""

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from PIL import Image, ImageDraw

from fluteomr.document import transcribe_page
from fluteomr.music import Instrument
from fluteomr.musicxml import to_musicxml

FIXTURE = Path(__file__).parent / "data/music_lab/raster/dev_down_flags-300.png"


def _page(empty_second=False):
    with Image.open(FIXTURE) as image:
        staff = image.convert("RGB")
    page = Image.new("RGB", (460, 730), "white")
    page.paste(staff, (40, 0))
    if not empty_second:
        page.paste(staff, (40, 360))
    else:
        draw = ImageDraw.Draw(page)
        for y in (468, 489, 510, 530, 551):
            draw.line((40, y, 366, y), fill="black", width=2)
    return page


def test_multiple_solo_staves_preserve_events_and_original_coordinates():
    result = transcribe_page(
        _page(),
        layout="solo",
        allow_clefless=True,
        instrument=Instrument.flute(),
        page_number=2,
    )
    measures = result.score.parts[0].measures
    assert [m.number for m in measures] == [1, 2]
    assert [len(m.notes) for m in measures] == [4, 4]
    assert result.score.issues() == ()
    for index, m in enumerate(measures):
        assert [(n.pitch.step, n.pitch.octave, n.duration.kind) for n in m.notes] == [
            ("E", 5, "eighth"),
            ("D", 5, "quarter"),
            ("F", 5, "eighth"),
            ("C", 5, "half"),
        ]
        assert all(n.staff_index == index and n.source_page == 2 for n in m.notes)
        assert all(n.candidate_id.startswith(f"s{index}-") for n in m.notes)
    for a, b in zip(measures[0].notes, measures[1].notes, strict=True):
        assert b.source_region.top - a.source_region.top == 360
        assert b.source_region.left == a.source_region.left
    assert [r["status"] for r in result.staff_results] == ["ready_not_validated"] * 2
    xml = ET.fromstring(to_musicxml(result.score))
    assert len(xml.findall("./part/measure/note")) == 8
    assert xml.findtext("./part-list/score-part/midi-instrument/midi-program") == "74"


def test_partial_page_keeps_recognized_notes_and_blocks_final_export():
    result = transcribe_page(
        _page(empty_second=True), layout="solo", allow_clefless=True
    )
    assert len(result.staff_results) == 2
    assert result.staff_results[0]["status"] == "ready_not_validated"
    assert result.staff_results[1]["status"] == "incomplete"
    assert len(result.score.parts[0].measures[0].notes) == 4
    assert result.score.issues()
    with pytest.raises(ValueError, match="incompleta"):
        to_musicxml(result.score)


def test_layout_is_explicit_and_missing_clef_is_not_silently_accepted():
    with pytest.raises(ValueError, match="solo"):
        transcribe_page(_page(), layout="duet")
    result = transcribe_page(_page(), layout="solo")
    assert all(r["status"] == "failed" for r in result.staff_results)
    assert result.score.issues()


def test_cli_exports_complete_page_and_refuses_overwrite(tmp_path):
    import json
    import subprocess
    import sys

    source, report, output = (
        tmp_path / name for name in ("page.png", "report.json", "score.musicxml")
    )
    _page().save(source)
    before = source.read_bytes()
    command = [
        sys.executable,
        "-m",
        "tools.transcribe_page",
        str(source),
        "--layout",
        "solo",
        "--clef",
        "treble",
        "--time",
        "4/4",
        "--allow-clefless",
        "--instrument",
        "flute",
        "--report",
        str(report),
        "--output",
        str(output),
    ]
    run = subprocess.run(command, capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    data = json.loads(report.read_text())
    assert len(data["staff_results"]) == 2
    assert data["staff_results"][1]["processing_region"]["top"] > 0
    assert len(ET.fromstring(output.read_bytes()).findall("./part/measure")) == 2
    saved = report.read_bytes(), output.read_bytes()
    again = subprocess.run(command, capture_output=True, text=True)
    assert again.returncode == 2
    assert saved == (report.read_bytes(), output.read_bytes())
    assert source.read_bytes() == before


def test_cli_preserves_partial_report_when_export_is_blocked(tmp_path):
    import json
    import subprocess
    import sys

    source, report, output = (
        tmp_path / name for name in ("page.png", "partial.json", "none.musicxml")
    )
    _page(empty_second=True).save(source)
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.transcribe_page",
            str(source),
            "--layout",
            "solo",
            "--clef",
            "treble",
            "--time",
            "4/4",
            "--allow-clefless",
            "--report",
            str(report),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 1, run.stderr
    assert (
        json.loads(report.read_text())["xml_export"] == "blocked_by_prediction_issues"
    )
    assert not output.exists()
