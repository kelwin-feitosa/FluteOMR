"""Cabeças de nota em uma pauta horizontal limpa, sem motor OMR externo."""

from dataclasses import dataclass
from math import ceil, floor

from PIL import Image

from fluteomr.image_io import normalize_image
from fluteomr.music import Duration, Note, Pitch
from fluteomr.staff_detection import Region, Staff


@dataclass(frozen=True)
class NoteheadObservation:
    center_x: int
    center_y: int
    region: Region
    visual_kind: str
    stem_present: bool
    shape_score: float  # fração geométrica heurística, não probabilidade
    diagnostics: tuple[str, ...]


def pitch_from_y(y: float, staff: Staff) -> Pitch | None:
    """Mi4 na linha inferior; cada meio espaçamento avança um grau diatônico."""
    half_gap = staff.spacing / 2
    displacement = (staff.lines[-1].y - y) / half_gap
    step_index = round(displacement)
    if abs(displacement - step_index) > 0.25 or not -4 <= step_index <= 12:
        return None
    diatonic = 2 + step_index  # C4=0, D4=1, E4=2
    octave_offset, position = divmod(diatonic, 7)
    return Pitch("CDEFGAB"[position], 4 + octave_offset)


def _ink_without_staff(image: Image.Image, staff: Staff, threshold: int) -> bytearray:
    gray = normalize_image(image).convert("L")
    pixels = gray.tobytes()
    ink = bytearray(value <= threshold for value in pixels)
    original = ink.copy()
    width = gray.width
    for line in staff.lines:
        start = max(0, floor(line.y - line.thickness / 2))
        end = min(gray.height - 1, ceil(line.y + line.thickness / 2))
        if start == 0 or end == gray.height - 1:
            continue
        for x in range(max(0, line.x_start), min(width - 1, line.x_end) + 1):
            above = any(
                original[(start - 1) * width + nx]
                for nx in range(max(0, x - 1), min(width, x + 2))
            )
            below = any(
                original[(end + 1) * width + nx]
                for nx in range(max(0, x - 1), min(width, x + 2))
            )
            if not (above and below):
                for y in range(start, end + 1):
                    ink[y * width + x] = 0
    return ink


def _shape(
    ink: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    rx: int,
    ry: int,
    core_offsets: tuple[tuple[int, int], ...],
    rim_offsets: tuple[tuple[int, int], ...],
) -> tuple[str, float] | None:
    if x - rx < 0 or x + rx >= width or y - ry < 0 or y + ry >= height:
        return None
    core = sum(ink[(y + dy) * width + x + dx] for dx, dy in core_offsets) / len(
        core_offsets
    )
    rim = sum(ink[(y + dy) * width + x + dx] for dx, dy in rim_offsets) / len(
        rim_offsets
    )
    if core >= 0.58 and rim >= 0.34:
        return "filled", min(core, rim)
    if core <= 0.34 and rim >= 0.40:
        return "hollow", rim - core / 2
    return None


def _has_stem(
    ink: bytearray,
    width: int,
    height: int,
    x: int,
    y: int,
    rx: int,
    ry: int,
    spacing: float,
) -> bool:
    reach = round(3.4 * spacing)
    for edge in (-1, 1):
        for offset in range(-1, 2):
            px = x + edge * rx + offset
            if px < 0 or px >= width:
                continue
            for direction in (-1, 1):
                start = y + direction * (ry + 1)
                stop = y + direction * reach
                positions = range(start, stop + direction, direction)
                positions = [py for py in positions if 0 <= py < height]
                if len(positions) < 1.8 * spacing:
                    continue
                count = sum(ink[py * width + px] for py in positions)
                if count >= 1.45 * spacing and count / len(positions) >= 0.38:
                    return True
    return False


def detect_noteheads(
    image: Image.Image,
    staff: Staff,
    threshold: int,
    measure_left: int,
    measure_right: int,
) -> tuple[NoteheadObservation, ...]:
    """Compara preenchimento central e anel, após suprimir as cinco linhas.

    Busca somente posições diatônicas próximas à pauta e dentro dos limites de
    compasso informados; não usa conteúdo ou referência musical como entrada.
    """
    if not 0 <= measure_left < measure_right < image.width:
        raise ValueError("limites de compasso fora da imagem")
    ink = _ink_without_staff(image, staff, threshold)
    spacing = staff.spacing
    rx = max(3, round(0.65 * spacing))
    ry = max(2, round(0.42 * spacing))
    core_offsets = tuple(
        (dx, dy)
        for dy in range(-ry, ry + 1)
        for dx in range(-rx, rx + 1)
        if (dx / rx) ** 2 + (dy / ry) ** 2 <= 0.30
    )
    rim_offsets = tuple(
        (dx, dy)
        for dy in range(-ry, ry + 1)
        for dx in range(-rx, rx + 1)
        if 0.55 <= (dx / rx) ** 2 + (dy / ry) ** 2 <= 1.15
    )
    candidates = []
    for degree in range(-4, 13):
        center = staff.lines[-1].y - degree * spacing / 2
        for y in range(
            round(center - 0.12 * spacing), round(center + 0.12 * spacing) + 1
        ):
            for x in range(measure_left + rx, measure_right - rx + 1):
                match = _shape(
                    ink,
                    image.width,
                    image.height,
                    x,
                    y,
                    rx,
                    ry,
                    core_offsets,
                    rim_offsets,
                )
                if match is None:
                    continue
                visual_kind, score = match
                stem = _has_stem(ink, image.width, image.height, x, y, rx, ry, spacing)
                candidates.append(
                    NoteheadObservation(
                        x,
                        y,
                        Region(x - rx, y - ry, x + rx, y + ry),
                        visual_kind,
                        stem,
                        score,
                        () if stem else ("stem_not_confirmed",),
                    )
                )
    return _deduplicate_candidates(candidates, spacing)


def _deduplicate_candidates(
    candidates: list[NoteheadObservation], spacing: float
) -> tuple[NoteheadObservation, ...]:
    """Une sondas da mesma cabeça; mantém eventos próximos em `x` e grau distinto."""
    chosen = []
    for candidate in sorted(
        candidates, key=lambda c: (c.shape_score, c.stem_present), reverse=True
    ):
        if any(
            abs(candidate.center_x - previous.center_x) < 0.9 * spacing
            and (
                abs(candidate.center_y - previous.center_y) < 0.65 * spacing
                or (
                    abs(candidate.center_x - previous.center_x) < 0.35 * spacing
                    and abs(candidate.center_y - previous.center_y) < 1.1 * spacing
                )
            )
            for previous in chosen
        ):
            continue
        chosen.append(candidate)
    return tuple(sorted(chosen, key=lambda c: c.center_x))


def notes_from_observations(
    observations: tuple[NoteheadObservation, ...], staff: Staff, staff_index: int
) -> tuple[Note, ...]:
    notes = []
    for head in observations:
        pitch = pitch_from_y(head.center_y, staff)
        duration = (
            Duration("quarter" if head.visual_kind == "filled" else "half")
            if head.stem_present
            else None
        )
        notes.append(
            Note(
                pitch,
                duration,
                head.region,
                staff_index,
                head.visual_kind,
                head.diagnostics,
                "image" if pitch else "unknown",
                "image" if duration else "unknown",
                f"s{staff_index}-h{head.center_x}-{head.center_y}",
            )
        )
    return tuple(notes)
