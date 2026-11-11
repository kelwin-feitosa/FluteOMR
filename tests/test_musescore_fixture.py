"""MuseScore adapter tests use a fake executable; no external editor required."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import musescore_fixture
from tools.musescore_fixture import MuseScoreRenderError, render_fixture


def _inputs(tmp_path):
    binary = tmp_path / "fake-musescore"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    score = tmp_path / "known.musicxml"
    score.write_text("<score-partwise version='4.0'/>")
    return score, binary


def _fake_run(commands, *, produce=True, fail=None, **kwargs):
    command = list(commands)
    if command[-1] == "--version":
        return SimpleNamespace(returncode=0, stdout="Fake MuseScore 4", stderr="")
    fmt = Path(command[command.index("-o") + 1]).suffix.lstrip(".")
    if fail == fmt:
        return SimpleNamespace(returncode=3, stdout="", stderr="invalid score")
    if produce:
        output = Path(command[command.index("-o") + 1])
        if fmt == "png":
            (output.parent / "score-1.png").write_bytes(b"fake-png-page-one")
            (output.parent / "score-2.png").write_bytes(b"fake-png-page-two")
        elif fmt in ("mpos", "spos"):
            output.write_text(
                '<score><elements><element id="0" page="0" '
                'x="10" y="20" sx="5" sy="10"/></elements></score>'
            )
        else:
            output.write_bytes(b"%PDF-1.4\n%%EOF\n")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_generates_separate_png_pages_position_maps_and_provenance(
    tmp_path, monkeypatch
):
    score, binary = _inputs(tmp_path)
    calls = []

    def fake(*a, **kw):
        calls.append((a[0], kw))
        return _fake_run(*a, **kw)

    monkeypatch.setattr(musescore_fixture.subprocess, "run", fake)
    destination = tmp_path / "rendered"
    result = render_fixture(score, destination, binary=binary, dpi=200)
    assert json.loads((destination / "manifest.json").read_text()) == result
    assert result["provenance"] == "source_authored_engraved_by_musescore"
    assert not result["human_ground_truth_reviewed"]
    assert not result["independent_printed_score"]
    assert [o["format"] for o in result["outputs"]] == ["pdf", "png", "mpos", "spos"]
    assert len(result["outputs"][1]["files"]) == 2
    assert result["outputs"][2]["files"][0]["position_elements"] == 1
    assert [call[0][-1] for call in calls[1:]] == [str(score.resolve())] * 4
    assert all(call[1]["env"]["QT_QPA_PLATFORM"] == "offscreen" for call in calls)
    assert all("-r" in call[0] for call in calls[1:])
    before = (destination / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        render_fixture(score, destination, binary=binary)
    assert (destination / "manifest.json").read_bytes() == before


@pytest.mark.parametrize(
    ("formats", "dpi"),
    [
        ((), 200),
        (("pdf", "pdf"), 200),
        (("invalid",), 200),
        (("png",), 60),
        (("pdf",), 401),
        (("pdf",), True),
    ],
)
def test_rejects_invalid_configuration_before_running(tmp_path, formats, dpi):
    score, binary = _inputs(tmp_path)
    with pytest.raises(MuseScoreRenderError):
        render_fixture(
            score,
            tmp_path / "rendered",
            binary=binary,
            formats=formats,
            dpi=dpi,
        )
    assert not (tmp_path / "rendered").exists()


def test_refuses_incomplete_export_and_leaves_no_final_directory(tmp_path, monkeypatch):
    score, binary = _inputs(tmp_path)
    monkeypatch.setattr(
        musescore_fixture.subprocess,
        "run",
        lambda *a, **kw: _fake_run(*a, produce=False, **kw),
    )
    destination = tmp_path / "rendered"
    with pytest.raises(MuseScoreRenderError, match="não criou"):
        render_fixture(score, destination, binary=binary, formats=("pdf",))
    assert not destination.exists()
    assert not list(tmp_path.glob(".musescore-fixture-*"))


def test_refuses_nonzero_exit_code_without_publishing(tmp_path, monkeypatch):
    score, binary = _inputs(tmp_path)
    monkeypatch.setattr(
        musescore_fixture.subprocess,
        "run",
        lambda *a, **kw: _fake_run(*a, fail="pdf", **kw),
    )
    with pytest.raises(MuseScoreRenderError, match="erro ao gerar pdf"):
        render_fixture(score, tmp_path / "rendered", binary=binary, formats=("pdf",))
    assert not (tmp_path / "rendered").exists()


def test_refuses_invalid_positions_xml(tmp_path, monkeypatch):
    score, binary = _inputs(tmp_path)

    def fake(*a, **kw):
        cmd = a[0]
        if cmd[-1] == "--version":
            return _fake_run(*a, **kw)
        Path(cmd[cmd.index("-o") + 1]).write_text("<not valid")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(musescore_fixture.subprocess, "run", fake)
    with pytest.raises(MuseScoreRenderError, match="XML de posições inválido"):
        render_fixture(score, tmp_path / "rendered", binary=binary, formats=("mpos",))


def test_refuses_musicxml_as_binary_and_unavailable_executable(tmp_path):
    score, binary = _inputs(tmp_path)
    with pytest.raises(MuseScoreRenderError, match="executável"):
        render_fixture(score, tmp_path / "rendered", binary=score)
    with pytest.raises(MuseScoreRenderError, match="MusicXML"):
        render_fixture(binary, tmp_path / "rendered", binary=binary, formats=("pdf",))
