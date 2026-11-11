"""Referências musicais derivadas de LilyPond nunca viram verdade humana."""

import hashlib
import json

import pytest

from tools.inspect_lilypond_candidates import (
    CandidateReferenceError,
    inspect_source_candidates,
)

SOURCE_XML = """<score-partwise version="4.0">
<part id="P1"><measure number="1">
  <attributes><divisions>4</divisions><time><beats>1</beats>
  <beat-type>4</beat-type></time></attributes>
  <note><rest/><duration>1</duration><type>16th</type></note>
  <note><pitch><step>E</step><octave>5</octave></pitch>
    <duration>1</duration><type>16th</type></note>
  <note><pitch><step>G</step><alter>1</alter><octave>5</octave></pitch>
    <duration>1</duration><type>16th</type></note>
</measure></part></score-partwise>"""


def _inputs(tmp_path, content=SOURCE_XML):
    source = tmp_path / "published.ly"
    source.write_text(r"\version \"2.18.2\"")
    folder = tmp_path / "candidate"
    folder.mkdir()
    (folder / "movement.musicxml").write_text(content)
    return source, folder, tmp_path / "manifest.json"


def test_source_derived_candidate_must_be_unreviewed_and_traceable(tmp_path):
    source, folder, report = _inputs(tmp_path)
    result = inspect_source_candidates(source, folder, report)
    assert json.loads(report.read_text()) == result
    assert result["reference_quality"] == "source_derived_unreviewed"
    assert result["human_reviewed"] is False
    assert result["score_alignment_verified"] is False
    assert result["same_engraving_as_pdf_verified"] is False
    assert result["music_accuracy"] == "not_evaluated"
    candidate = result["candidates"][0]
    assert candidate["events"] == 3
    assert candidate["rests"] == 1
    assert candidate["pitched_events"] == 2
    assert candidate["types"] == {"16th": 3}
    assert candidate["first_measure_preview"][2]["alter"] == "1"
    with pytest.raises(FileExistsError):
        inspect_source_candidates(source, folder, report)


@pytest.mark.parametrize(
    ("xml", "message"),
    [
        ("<html></html>", "score-partwise"),
        ("<score-partwise/>", "parte musical"),
        ("<score-partwise><part id='P1'/></score-partwise>", "sem compassos"),
        (
            "<score-partwise><part id='P1'><measure number='1'>"
            "<note><rest/></note></measure></part></score-partwise>",
            "sem notas com altura",
        ),
        ("<score", "parseável"),
        (
            SOURCE_XML.replace(
                "<duration>1</duration>", "<duration>-1</duration>", 1
            ),
            "duração numérica inválida",
        ),
    ],
)
def test_invalid_source_candidate_is_rejected_without_reporting(tmp_path, xml, message):
    source, folder, report = _inputs(tmp_path, content=xml)
    with pytest.raises(CandidateReferenceError, match=message):
        inspect_source_candidates(source, folder, report)
    assert not report.exists()


def test_inspector_collects_extra_movement_files(tmp_path):
    source, folder, report = _inputs(tmp_path)
    extra = folder / "movement.exports"
    extra.mkdir()
    (extra / "book-01-score-02.musicxml").write_text(SOURCE_XML)
    result = inspect_source_candidates(source, folder, report)
    assert result["candidate_count"] == 2
    assert {
        row["file"] for row in result["candidates"]
    } == {"movement.musicxml", "movement.exports/book-01-score-02.musicxml"}


def test_empty_directory_does_not_produce_fake_ground_truth(tmp_path):
    source, folder, report = _inputs(tmp_path)
    (folder / "movement.musicxml").unlink()
    with pytest.raises(CandidateReferenceError, match="nenhum"):
        inspect_source_candidates(source, folder, report)
    assert not report.exists()


def _prefix_file(source, tmp_path):
    literal = r'\\version \\"2.18.2\\"'
    manifest = {
        "format_version": 1,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_literal": literal,
        "expected_events": [
            {
                "rest": True,
                "type": "16th",
                "step": None,
                "alter": None,
                "octave": None,
            },
            {
                "rest": False,
                "type": "16th",
                "step": "E",
                "alter": None,
                "octave": "5",
            },
            {
                "rest": False,
                "type": "16th",
                "step": "G",
                "alter": "1",
                "octave": "5",
            },
        ],
    }
    path = tmp_path / "prefix.json"
    path.write_text(json.dumps(manifest))
    return path


def test_verified_prefix_is_not_mistaken_for_full_score_alignment(tmp_path):
    source, folder, report = _inputs(tmp_path)
    guard = _prefix_file(source, tmp_path)
    result = inspect_source_candidates(
        source, folder, report, expected_prefix=guard
    )
    assert result["reference_quality"] == "source_derived_unreviewed"
    assert result["source_prefix_alignment"] == "prefix_only"
    assert result["usable_as_music_ground_truth"] is False
    assert result["score_alignment_verified"] is False
    assert result["candidates"][0]["source_prefix_check"]["mismatches"] == []


def test_missing_source_rest_rejects_candidate_even_if_xml_valid(tmp_path):
    bad_xml = SOURCE_XML.replace(
        "<note><rest/><duration>1</duration><type>16th</type></note>", ""
    )
    source, folder, report = _inputs(tmp_path, bad_xml)
    guard = _prefix_file(source, tmp_path)
    result = inspect_source_candidates(
        source, folder, report, expected_prefix=guard
    )
    assert result["reference_quality"] == "rejected_source_prefix_mismatch"
    assert result["source_prefix_alignment"] == "mismatch"
    problems = result["candidates"][0]["source_prefix_check"]["mismatches"]
    assert problems[0]["expected"]["rest"] is True
    assert problems[0]["observed"]["rest"] is False
    assert result["human_reviewed"] is False


@pytest.mark.parametrize("tamper", ["wrong-hash", "absent-literal", "invalid-rest"])
def test_prefix_guard_must_be_same_source(tmp_path, tamper):
    source, folder, report = _inputs(tmp_path)
    guard = _prefix_file(source, tmp_path)
    data = json.loads(guard.read_text())
    if tamper == "wrong-hash":
        data["source_sha256"] = "0" * 64
    elif tamper == "absent-literal":
        data["source_literal"] = "not a fragment of source"
    else:
        data["expected_events"][0]["step"] = "E"
    guard.write_text(json.dumps(data))
    with pytest.raises(CandidateReferenceError):
        inspect_source_candidates(source, folder, report, expected_prefix=guard)
    assert not report.exists()
