"""Pipeline experimental de um compasso: PNG -> notas inferidas -> modelo musical."""

from dataclasses import dataclass

from PIL import Image

from fluteomr.music import Clef, Measure, MusicPart, MusicScore, TimeSignature
from fluteomr.notes import (
    NoteheadObservation,
    detect_noteheads,
    notes_from_observations,
)
from fluteomr.staff_detection import Region, detect_staffs
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


def transcribe_one_measure(
    image: Image.Image,
    *,
    measure_left: int,
    measure_right: int,
    beats: int = 4,
    part_name: str | None = None,
) -> MusicScore:
    """Clave de sol, fórmula e limites são configuração, nunca visão inferida."""
    if beats < 1:
        raise ValueError("beats deve ser positivo")
    result = detect_staffs(image)
    if result.status != "detected" or result.staff_count != 1:
        raise ValueError("a transcrição inicial exige exatamente uma pauta válida")
    staff = result.staffs[0]
    heads = detect_noteheads(
        image, staff, result.threshold, measure_left, measure_right
    )
    notes = notes_from_observations(heads, staff, 0)
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
    )
    return MusicScore((part,))


def transcribe_measures(
    image: Image.Image,
    *,
    content_left: int,
    content_right: int,
    beats: int = 4,
    part_name: str | None = None,
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
    heads = detect_noteheads(
        image, staff, result.threshold, content_left, content_right
    )
    bars = detect_barlines(
        image, staff, result.threshold, content_left, content_right, heads
    )
    accepted = [bar for bar in bars if bar.status == "accepted"]
    if not accepted:
        raise ValueError("nenhuma barra interna confiável encontrada")
    if any(
        right.x - left.x < 1.5 * staff.spacing
        for left, right in zip(accepted, accepted[1:], strict=False)
    ):
        raise ValueError("barras internas próximas ou ambíguas")
    boundaries = [content_left, *(bar.x for bar in accepted), content_right]
    notes = notes_from_observations(heads, staff, 0)
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
    )
    return TranscriptionResult(
        MusicScore((part,)),
        heads,
        linked_stems(image, staff, result.threshold, heads),
        bars,
    )
