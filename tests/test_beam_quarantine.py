"""Rejeição conservadora de feixes incompletos antes de confiar no ritmo."""

from fluteomr.music import Duration, Note, Pitch
from fluteomr.staff_detection import Region
from fluteomr.transcription import _reject_incomplete_beam_runs


def _note(kind="eighth", beam=None, beam_levels=()):
    return Note(
        Pitch("C", 5),
        Duration(kind),
        Region(20, 30, 29, 39),
        0,
        "filled",
        beam=beam,
        beam_levels=beam_levels,
    )


def test_valid_beam_group_survives_adaptive_quarantine():
    notes = (_note(beam="begin"), _note(beam="end"))
    assert _reject_incomplete_beam_runs(notes) == notes


def test_missing_intermediate_head_rejects_both_dangling_beam_ends():
    notes = (
        _note(beam="begin"),
        _note(kind="quarter"),
        _note(beam="end"),
    )
    result = _reject_incomplete_beam_runs(notes)
    assert result[0].duration is None
    assert result[2].duration is None
    assert result[0].beam is None
    assert result[2].beam is None
    assert result[0].duration_origin == "unknown"
    assert "invalid_beam_group_rejected" in result[0].diagnostics
    assert result[1] == notes[1]


def test_valid_secondary_beam_levels_are_preserved():
    notes = (
        _note(
            kind="sixteenth",
            beam="begin",
            beam_levels=((1, "begin"), (2, "begin")),
        ),
        _note(
            kind="sixteenth",
            beam="end",
            beam_levels=((1, "end"), (2, "end")),
        ),
    )
    assert _reject_incomplete_beam_runs(notes) == notes


def test_invalid_secondary_level_rejects_entire_connected_run():
    notes = (
        _note(
            kind="sixteenth",
            beam="begin",
            beam_levels=((1, "begin"), (2, "begin")),
        ),
        _note(
            kind="sixteenth",
            beam="end",
            beam_levels=((1, "end"), (2, "begin")),
        ),
    )
    result = _reject_incomplete_beam_runs(notes)
    assert all(note.duration is None for note in result)
    assert all(note.beam_levels == () for note in result)
    assert all("invalid_beam_group_rejected" in note.diagnostics for note in result)


def test_unbeamed_events_are_untouched():
    notes = (_note(kind="quarter"), _note(kind="half"))
    assert _reject_incomplete_beam_runs(notes) == notes
