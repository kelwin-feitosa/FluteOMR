"""Perfis adaptativos de duas bandas: função opcional, sem mudar o motor padrão."""

from PIL import ImageDraw

from fluteomr.notes import detect_noteheads
from fluteomr.rhythm import _adaptive_secondary_profile, detect_rhythm_evidence
from fluteomr.staff_detection import detect_staffs
from fluteomr.symbols import linked_stems
from fluteomr.transcription import transcribe_one_measure
from tests.test_eighths import _page


def _second_beam(
    image,
    notes,
    first,
    second,
    *,
    spacing=16,
    fraction=0.62,
    width=4,
    length=1.0,
):
    rx = round(0.65 * spacing)

    def tip(index):
        x, degree, _, direction = notes[index]
        assert direction == "down"
        return (
            x - rx + 1,
            138 - round(degree * spacing / 2) + round(3.3 * spacing),
        )

    x1, y1 = tip(first)
    x2, y2 = tip(second)
    offset = -round(fraction * spacing)
    ImageDraw.Draw(image).line(
        (
            x1,
            y1 + offset,
            round(x1 + length * (x2 - x1)),
            round(y1 + length * (y2 - y1)) + offset,
        ),
        fill="black",
        width=width,
    )


def _notes3():
    # Mantém os feixes abaixo da pauta: evita que uma linha de pauta
    # intercepte a segunda banda e crie falsas cabeças no teste isolado.
    return (
        (145, 5, "eighth", "down"),
        (215, 4, "eighth", "down"),
        (285, 3, "eighth", "down"),
    )


def test_adaptive_secondary_accepts_valid_two_bands_at_nonfixed_distance():
    for distance in (0.58, 0.65, 0.80):
        notes = _notes3()
        image = _page(notes, beam_groups=((0, 1, 2),))
        _second_beam(image, notes, 1, 2, fraction=distance)
        score = transcribe_one_measure(
            image,
            measure_left=110,
            measure_right=410,
            beats=1,
            adaptive_secondary=True,
        )
        events = score.parts[0].measures[0].notes
        assert [n.duration.kind for n in events] == ["eighth", "sixteenth", "sixteenth"]
        assert [dict(n.beam_levels).get(2) for n in events] == [None, "begin", "end"]
        assert score.issues() == ()


def test_adaptive_secondary_leaves_single_beams_as_eighths():
    notes = _notes3()
    image = _page(notes, beam_groups=((0, 1, 2),))
    score = transcribe_one_measure(
        image,
        measure_left=110,
        measure_right=410,
        beats=2,
        adaptive_secondary=True,
    )
    assert all(
        note.duration.kind == "eighth" for note in score.parts[0].measures[0].notes
    )


def test_adaptive_secondary_rejects_thick_merged_strokes():
    notes = _notes3()[:2]
    image = _page(notes, beam_groups=((0, 1),))
    _second_beam(image, notes, 0, 1, fraction=0.6, width=22)
    det = detect_staffs(image)
    staff = det.staffs[0]
    heads = detect_noteheads(image, staff, det.threshold, 110, 410)
    stems = linked_stems(image, staff, det.threshold, heads)
    evidence = detect_rhythm_evidence(
        image, staff, det.threshold, heads, stems, adaptive_secondary=True
    )
    assert not any(
        ev.status == "accepted" and ev.kind == "double_beam" for ev in evidence
    )


def test_adaptive_secondary_does_not_accept_partial_second_beam():
    notes = _notes3()[:2]
    image = _page(notes, beam_groups=((0, 1),))
    # Um feixe incompleto não forma continuidade entre as duas hastes.
    _second_beam(image, notes, 0, 1, fraction=0.65, length=0.52)
    det = detect_staffs(image)
    staff = det.staffs[0]
    heads = detect_noteheads(image, staff, det.threshold, 110, 410)
    stems = linked_stems(image, staff, det.threshold, heads)
    evidence = detect_rhythm_evidence(
        image, staff, det.threshold, heads, stems, adaptive_secondary=True
    )
    assert not any(
        ev.status == "accepted" and ev.kind == "double_beam" for ev in evidence
    )


def test_adaptive_profile_reports_no_two_bands_on_inkless_pixels():
    ink = bytearray(60 * 40)
    status, offset = _adaptive_secondary_profile(ink, 60, 40, (5, 18), (52, 18), 1, 12)
    assert status != "confirmed"
    assert offset is None
