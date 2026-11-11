"""Pipeline experimental de um compasso: PNG -> notas inferidas -> modelo musical."""

from dataclasses import dataclass, replace

from PIL import Image

from fluteomr.music import (
    Clef,
    Duration,
    Instrument,
    Measure,
    MusicPart,
    MusicScore,
    TimeSignature,
)
from fluteomr.notes import (
    NoteheadObservation,
    detect_noteheads,
    notes_from_observations,
)
from fluteomr.rhythm import RhythmEvidence, detect_rhythm_evidence
from fluteomr.staff_detection import Region, Staff, detect_staffs
from fluteomr.symbols import (
    BarlineCandidate,
    StemCandidate,
    detect_barlines,
    linked_stems,
)


@dataclass(frozen=True)
class TranscriptionResult:
    score: MusicScore
    heads: tuple[NoteheadObservation, ...]
    stems: tuple[StemCandidate, ...]
    barlines: tuple[BarlineCandidate, ...]
    rhythm_evidence: tuple[RhythmEvidence, ...] = ()


def _interpret_notes(
    image, staff, threshold, heads, barlines=(), *, adaptive_secondary=False
):
    stems = linked_stems(image, staff, threshold, heads)
    rhythm_kwargs = {"barlines": barlines}
    if adaptive_secondary:
        rhythm_kwargs["adaptive_secondary"] = True
    marks = detect_rhythm_evidence(
        image, staff, threshold, heads, stems, **rhythm_kwargs
    )
    by_head = {mark.head_id: mark for mark in marks}
    notes = []
    for note in notes_from_observations(heads, staff, 0):
        mark = by_head.get(note.candidate_id)
        if mark is None:
            notes.append(note)
        elif mark.status == "inconclusive":
            notes.append(
                replace(
                    note,
                    duration=None,
                    duration_origin="unknown",
                    diagnostics=(*note.diagnostics, mark.kind, mark.reason),
                )
            )
        else:
            notes.append(
                replace(
                    note,
                    duration=Duration(
                        "sixteenth" if mark.kind == "double_beam" else "eighth"
                    ),
                    beam=mark.beam_position,
                    beam_levels=mark.beam_levels,
                    diagnostics=(
                        *note.diagnostics,
                        mark.kind,
                        *((mark.reason,) if mark.beam_levels else ()),
                    ),
                )
            )
    return tuple(notes), stems, marks


def transcribe_one_measure(
    image: Image.Image,
    *,
    measure_left: int,
    measure_right: int,
    beats: int = 4,
    part_name: str | None = None,
    instrument: Instrument | None = None,
    normalize_heads: bool = True,
    adaptive_secondary: bool = False,
) -> MusicScore:
    """Clave de sol, fórmula e limites são configuração, nunca visão inferida."""
    if beats < 1:
        raise ValueError("beats deve ser positivo")
    result = detect_staffs(image)
    if result.status != "detected" or result.staff_count != 1:
        raise ValueError("a transcrição inicial exige exatamente uma pauta válida")
    staff = result.staffs[0]
    heads = detect_noteheads(
        image,
        staff,
        result.threshold,
        measure_left,
        measure_right,
        normalize=normalize_heads,
    )
    notes, _, _ = _interpret_notes(
        image,
        staff,
        result.threshold,
        heads,
        adaptive_secondary=adaptive_secondary,
    )
    measure = Measure(
        1, notes, TimeSignature(beats, 4, "configuration"), "configuration"
    )
    part = MusicPart(
        "P1",
        part_name or "Parte 1",
        "configuration" if part_name else "unknown",
        (0,),
        Clef("treble", "configuration"),
        (measure,),
        instrument=instrument,
    )
    return MusicScore((part,))


def transcribe_measures(
    image: Image.Image,
    *,
    content_left: int,
    content_right: int,
    beats: int = 4,
    part_name: str | None = None,
    instrument: Instrument | None = None,
    normalize_heads: bool = True,
    adaptive_secondary: bool = False,
) -> TranscriptionResult:
    """Divide uma pauta pelos traços verticais inferidos dentro de limites dados.

    Os limites externos, clave de sol e fórmula são configuração. Apenas barras
    internas e eventos são inferidos dos pixels. Não preenche lacunas rítmicas.
    """
    if beats < 1:
        raise ValueError("beats deve ser positivo")
    result = detect_staffs(image)
    if result.status != "detected" or result.staff_count != 1:
        raise ValueError("a transcrição exige exatamente uma pauta válida")
    staff = result.staffs[0]
    return transcribe_staff_measures(
        image,
        staff,
        result.threshold,
        content_left=content_left,
        content_right=content_right,
        beats=beats,
        part_name=part_name,
        instrument=instrument,
        normalize_heads=normalize_heads,
        adaptive_secondary=adaptive_secondary,
        require_internal_bar=True,
    )


def transcribe_staff_measures(
    image: Image.Image,
    staff: Staff,
    threshold: int,
    *,
    content_left: int,
    content_right: int,
    beats: int = 4,
    part_name: str | None = None,
    instrument: Instrument | None = None,
    normalize_heads: bool = True,
    adaptive_secondary: bool = False,
    require_internal_bar: bool = False,
) -> TranscriptionResult:
    """Consome geometria já detectada; bordas externas continuam provisórias.

    Sem barra interna, assume um único intervalo entre as bordas fornecidas.
    O chamador legado exige uma barra para preservar seu contrato anterior.
    """
    if beats < 1:
        raise ValueError("beats deve ser positivo")
    heads = detect_noteheads(
        image,
        staff,
        threshold,
        content_left,
        content_right,
        normalize=normalize_heads,
    )
    bars = detect_barlines(image, staff, threshold, content_left, content_right, heads)
    accepted = [bar for bar in bars if bar.status == "accepted"]
    if not accepted and require_internal_bar:
        raise ValueError("nenhuma barra interna confiável encontrada")
    if any(
        right.x - left.x < 1.5 * staff.spacing
        for left, right in zip(accepted, accepted[1:], strict=False)
    ):
        raise ValueError("barras internas próximas ou ambíguas")
    boundaries = [content_left, *(bar.x for bar in accepted), content_right]
    notes, stems, marks = _interpret_notes(
        image,
        staff,
        threshold,
        heads,
        bars,
        adaptive_secondary=adaptive_secondary,
    )
    measures = []
    for index, (left, right) in enumerate(
        zip(boundaries, boundaries[1:], strict=False), 1
    ):
        included = tuple(
            note
            for note in notes
            if left < (note.source_region.left + note.source_region.right) / 2 < right
        )
        boundary_ids = tuple(
            bar.id for bar in accepted if bar.x == left or bar.x == right
        )
        measures.append(
            Measure(
                index,
                included,
                TimeSignature(beats, 4, "configuration"),
                "image" if boundary_ids else "configuration",
                Region(left, staff.region.top, right, staff.region.bottom),
                boundary_ids,
                (
                    "image" if index > 1 else "configuration",
                    "image" if index < len(boundaries) - 1 else "configuration",
                ),
            )
        )
    part = MusicPart(
        "P1",
        part_name or "Parte 1",
        "configuration" if part_name else "unknown",
        (0,),
        Clef("treble", "configuration"),
        tuple(measures),
        instrument=instrument,
    )
    return TranscriptionResult(
        MusicScore(
            (part,),
            tuple(
                f"inconclusive_barline:{bar.id}"
                for bar in bars
                if bar.status == "inconclusive"
            ),
        ),
        heads,
        stems,
        bars,
        marks,
    )
