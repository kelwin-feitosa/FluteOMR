"""Testa sonda musical sem ler fontes externas ou gerar MusicXML."""

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
from tools import real_music_probe


def _score_with_uncertain_duration():
    note = Note(
        Pitch("G", 4),
        None,
        Region(20, 20, 28, 26),
        0,
        "filled",
        diagnostics=("double_beam", "parallel_beam_unsupported"),
    )
    measure = Measure(
        1,
        (note,),
        TimeSignature(4, 4, "configuration"),
        "configuration",
    )
    return MusicScore(
        (
            MusicPart(
                "P1",
                "Flute",
                "configuration",
                (0,),
                Clef("treble", "configuration"),
                (measure,),
            ),
        )
    )


def test_real_probe_counts_unresolved_events_and_never_tries_xml(tmp_path, monkeypatch):
    monkeypatch.setattr(
        real_music_probe,
        "load_pdf_page",
        lambda *_a, **_kw: Image.new("RGB", (160, 120), "white"),
    )
    monkeypatch.setattr(
        real_music_probe,
        "transcribe_page",
        lambda *_a, **_kw: SimpleNamespace(
            score=_score_with_uncertain_duration(),
            staff_results=({"status": "incomplete"},),
        ),
    )
    report = tmp_path / "probe.json"
    result = real_music_probe.probe_pdf(
        tmp_path / "published.pdf", page_number=1, dpi=150, report=report
    )
    assert json.loads(report.read_text()) == result
    assert result["predicted_events"] == 1
    assert result["resolved_pitch_events"] == 1
    assert result["resolved_duration_events"] == 0
    assert result["unresolved_duration_events"] == 1
    assert result["unresolved_duration_diagnostic_counts"] == {
        "double_beam": 1,
        "parallel_beam_unsupported": 1,
    }
    assert result["issue_count"] > 0
    assert result["musical_accuracy"] == "not_evaluated"
    assert result["xml_export"] == "not_attempted"
    with pytest.raises(FileExistsError):
        real_music_probe.probe_pdf(tmp_path / "published.pdf", report=report)


def test_real_probe_records_transcription_failure_without_fabricating_accuracy(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        real_music_probe,
        "load_pdf_page",
        lambda *_a, **_kw: Image.new("RGB", (160, 120), "white"),
    )

    def no_music(*_args, **_kwargs):
        raise ValueError("clave incerta")

    monkeypatch.setattr(real_music_probe, "transcribe_page", no_music)
    result = real_music_probe.probe_pdf(tmp_path / "published.pdf")
    assert result["status"] == "processing_failed"
    assert result["error"] == "clave incerta"
    assert result["musical_accuracy"] == "not_evaluated"
    assert result["xml_export"] == "not_attempted"
