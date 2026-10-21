"""Página PNG/JPEG solo experimental; não infere identidade entre instrumentos."""

from dataclasses import asdict, dataclass, replace
from math import ceil, floor, isfinite

from PIL import Image

from fluteomr.clefs import detect_treble_clefs
from fluteomr.image_io import normalize_image
from fluteomr.music import Clef, Instrument, MusicPart, MusicScore
from fluteomr.staff_detection import Region, detect_staffs
from fluteomr.transcription import transcribe_staff_measures


@dataclass(frozen=True)
class PageTranscription:
    score: MusicScore
    page_number: int
    image_size: tuple[int, int]
    staff_results: tuple[dict, ...]

    def to_dict(self) -> dict:
        return {
            "format_version": 1,
            **self.score.to_dict(),
            "page_number": self.page_number,
            "image_size": self.image_size,
            "staff_results": self.staff_results,
            "coordinate_frame": "exif_oriented_source",
            "layout": "solo",
            "layout_origin": "configuration",
            "warnings": [
                "unsupported_symbol_detection_not_exhaustive",
                "staff_edges_are_provisional_measure_boundaries",
            ],
        }


def transcribe_page(
    image: Image.Image,
    *,
    layout: str,
    page_number: int = 1,
    allow_clefless: bool = False,
    instrument: Instrument | None = None,
    leading_spaces: float = 0,
) -> PageTranscription:
    """Junta pautas em ordem somente sob a hipótese solo fornecida pelo usuário.

    Clave de sol e 4/4 são configuração. Uma clave visual aceita delimita o
    conteúdo inicial; não há reconhecimento de fórmula, armadura ou texto.
    Cada pauta é processada isoladamente, sem modificar a imagem original.
    """
    if layout != "solo":
        raise ValueError("forneça layout solo; conjuntos ainda não são suportados")
    if type(page_number) is not int or page_number < 1:
        raise ValueError("página deve ser um inteiro positivo")
    if not isfinite(leading_spaces) or leading_spaces < 0:
        raise ValueError("margem inicial relativa inválida")
    image = normalize_image(image)
    detection = detect_staffs(image)
    if not detection.staffs or detection.status != "detected":
        raise ValueError("nenhuma pauta confiável para transcrever na página")
    clefs = detect_treble_clefs(image, detection).observations
    measures, records, failures = [], [], []
    for index, staff in enumerate(detection.staffs):
        spacing = staff.spacing
        y0 = max(0, floor(staff.lines[0].y - 7 * spacing))
        y1 = min(image.height, ceil(staff.lines[-1].y + 7 * spacing) + 1)
        if index:
            y0 = max(
                y0,
                ceil(
                    (detection.staffs[index - 1].region.bottom + staff.region.top) / 2
                ),
            )
        if index + 1 < len(detection.staffs):
            y1 = min(
                y1,
                ceil(
                    (staff.region.bottom + detection.staffs[index + 1].region.top) / 2
                ),
            )
        record = {
            "staff_index": index,
            "system_id": f"solo-{index}",
            "system_origin": "configuration",
            "source_region": asdict(staff.region),
            "processing_region": asdict(Region(0, y0, image.width - 1, y1 - 1)),
            "clef_status": clefs[index].status,
            "outer_boundary_origin": "staff_extent_convention",
        }
        try:
            if clefs[index].clef is None and not allow_clefless:
                raise ValueError(
                    "clave visual não resolvida; revise ou declare "
                    "pauta sem clave impressa"
                )
            left = round(staff.region.left)
            if clefs[index].clef is not None:
                left = max(left, ceil(clefs[index].clef.region.right))
            left += round(leading_spaces * spacing)
            right = min(image.width - 1, round(staff.region.right - 0.6 * spacing))
            local = replace(
                staff,
                lines=tuple(replace(line, y=line.y - y0) for line in staff.lines),
                region=replace(
                    staff.region,
                    top=staff.region.top - y0,
                    bottom=staff.region.bottom - y0,
                ),
            )
            analysis = transcribe_staff_measures(
                image.crop((0, y0, image.width, y1)),
                local,
                detection.threshold,
                content_left=left,
                content_right=right,
            )

            numbers = []
            for measure in analysis.score.parts[0].measures:
                number = len(measures) + 1
                numbers.append(number)
                notes = tuple(
                    replace(
                        n,
                        staff_index=index,
                        source_page=page_number,
                        source_region=_lift(n.source_region, y0),
                        candidate_id=_candidate_id(n.candidate_id, index),
                    )
                    for n in measure.notes
                )
                measures.append(
                    replace(
                        measure,
                        number=number,
                        notes=notes,
                        source_region=_lift(measure.source_region, y0),
                        boundary_candidate_ids=tuple(
                            _candidate_id(i, index)
                            for i in measure.boundary_candidate_ids
                        ),
                    )
                )
            issues = analysis.score.issues()
            records.append(
                {
                    **record,
                    "content_left": left,
                    "content_right": right,
                    "measure_numbers": numbers,
                    "events": len(analysis.heads),
                    "issues": issues,
                    "status": "incomplete" if issues else "ready_not_validated",
                }
            )
            if issues:
                failures.append(f"staff={index}:incomplete")
        except ValueError as exc:
            records.append(
                {
                    **record,
                    "status": "failed",
                    "error": str(exc),
                    "measure_numbers": [],
                    "events": None,
                }
            )
            failures.append(f"staff={index}:processing_failed")
    part = MusicPart(
        "P1",
        instrument.name if instrument else "Parte solo",
        "configuration",
        tuple(range(len(detection.staffs))),
        Clef("treble", "configuration"),
        tuple(measures),
        instrument=instrument,
    )
    return PageTranscription(
        MusicScore((part,), tuple(failures)), page_number, image.size, tuple(records)
    )


def _lift(region: Region, y0: int) -> Region:
    return replace(region, top=region.top + y0, bottom=region.bottom + y0)


def _candidate_id(value: str | None, index: int) -> str | None:
    return value.replace("s0-", f"s{index}-", 1) if value else None
