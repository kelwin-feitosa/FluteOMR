"""Projeção horizontal e validação geométrica de cinco linhas.

Coordenadas em pixels na imagem normalizada: origem superior esquerda,
x para a direita, y para baixo. Extremos e bounding boxes são inclusivos.
"""

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import median
from typing import Literal

from PIL import Image

from fluteomr.image_io import load_image, normalize_image


@dataclass(frozen=True)
class StaffLine:
    x_start: int
    x_end: int
    y: float
    thickness: int


@dataclass(frozen=True)
class Region:
    left: int
    top: float
    right: int
    bottom: float


@dataclass(frozen=True)
class Staff:
    lines: tuple[StaffLine, ...]
    spacing: float
    region: Region


@dataclass(frozen=True)
class DetectionResult:
    width: int
    height: int
    status: Literal["detected", "no_staff", "ambiguous"]
    staffs: tuple[Staff, ...]
    candidates: tuple[StaffLine, ...]
    threshold: int
    diagnostics: tuple[str, ...]
    analysis_threshold: int | None = None

    @property
    def staff_count(self) -> int:
        return len(self.staffs)

    def to_dict(self) -> dict:
        return {**asdict(self), "staff_count": self.staff_count}


def _otsu_threshold(histogram: list[int]) -> int:
    """Maximiza variância entre classes; pixels <= limiar são escuros."""
    total = sum(histogram)
    intensity_sum = sum(i * count for i, count in enumerate(histogram))
    weight = partial = 0
    best_score = -1.0
    threshold = 0
    for value, count in enumerate(histogram):
        weight += count
        partial += value * count
        if weight == 0 or weight == total:
            continue
        difference = partial / weight - (intensity_sum - partial) / (total - weight)
        score = weight * (total - weight) * difference**2
        if score > best_score:
            best_score, threshold = score, value
    return threshold


def _horizontal_span(row: bytes) -> tuple[int, int] | None:
    """Maior segmento escuro, unindo lacunas de até 2% da largura."""
    spans = _horizontal_spans(row)
    return max(spans, key=lambda span: span[1] - span[0], default=None)


def _horizontal_spans(row: bytes) -> list[tuple[int, int]]:
    """Trechos horizontais separados por lacunas maiores que 2% da largura."""
    positions = [x for x, pixel in enumerate(row) if pixel]
    if not positions:
        return []
    max_gap = max(1, round(len(row) * 0.02))
    start = previous = positions[0]
    spans = []
    for x in positions[1:]:
        if x - previous - 1 > max_gap:
            spans.append((start, previous))
            start = x
        previous = x
    spans.append((start, previous))
    return spans


def _line_candidates(binary: bytes, width: int, height: int) -> tuple[StaffLine, ...]:
    projection = [binary[y * width : (y + 1) * width].count(1) for y in range(height)]
    minimum = max(width * 0.25, max(projection, default=0) * 0.6)
    bands: list[list[tuple[int, int, tuple[int, int]]]] = []
    for y, count in enumerate(projection):
        if count < minimum:
            continue
        span = _horizontal_span(binary[y * width : (y + 1) * width])
        if span is None or span[1] - span[0] + 1 < width * 0.25:
            continue
        if not bands or y != bands[-1][-1][0] + 1:
            bands.append([])
        bands[-1].append((y, count, span))
    lines = []
    for band in bands:
        y = sum(row * count for row, count, _ in band) / sum(
            count for _, count, _ in band
        )
        lines.append(
            StaffLine(
                round(median(span[0] for _, _, span in band)),
                round(median(span[1] for _, _, span in band)),
                y,
                len(band),
            )
        )
    return tuple(lines)


def _make_staff(lines: tuple[StaffLine, ...]) -> Staff | None:
    gaps = [second.y - first.y for first, second in zip(lines, lines[1:], strict=False)]
    spacing = median(gaps)
    if any(abs(gap - spacing) > 0.20 * spacing for gap in gaps):
        return None
    if any(line.thickness > 0.50 * spacing for line in lines):
        return None
    return Staff(
        lines,
        spacing,
        Region(
            min(line.x_start for line in lines),
            lines[0].y - (lines[0].thickness - 1) / 2,
            max(line.x_end for line in lines),
            lines[-1].y + (lines[-1].thickness - 1) / 2,
        ),
    )


def _has_horizontal_overlap(staff: Staff) -> bool:
    left = max(line.x_start for line in staff.lines)
    right = min(line.x_end for line in staff.lines)
    min_length = min(line.x_end - line.x_start + 1 for line in staff.lines)
    return right - left + 1 >= 0.6 * min_length


def _group_candidates(
    lines: tuple[StaffLine, ...], binary: bytes, width: int, height: int
) -> list[tuple[int, Staff]]:
    groups = []
    for start in range(max(0, len(lines) - 4)):
        staff = _make_staff(lines[start : start + 5])
        if staff is not None:
            refined = _refine_staff_extents(staff, binary, width, height)
            if _has_horizontal_overlap(refined):
                groups.append((start, refined))
    return groups


def _refine_staff_extents(
    staff: Staff, binary: bytes, width: int, height: int
) -> Staff:
    """Recupera trechos após lacunas usando só as cinco linhas da mesma pauta.

    A faixa vertical absorve deslocamentos de rasterização. Trechos separados
    precisam ser substanciais e terminar próximos ao consenso das cinco linhas;
    marcas isoladas além do fim da pauta não alteram seus limites.
    """
    evidence = []
    for line in staff.lines:
        radius = min(
            max(1, round(line.thickness / 2)), max(1, round(staff.spacing / 4))
        )
        center = round(line.y)
        supported_bits = 0
        for y in range(max(0, center - radius), min(height, center + radius + 1)):
            row = binary[y * width : (y + 1) * width]
            supported_bits |= int.from_bytes(row, "little")
        supported = supported_bits.to_bytes(width, "little")
        spans = _horizontal_spans(supported)
        if not spans:
            spans = [(line.x_start, line.x_end)]
        anchor = max(spans, key=lambda span: span[1] - span[0])
        evidence.append((spans, anchor))

    anchor_width = median(anchor[1] - anchor[0] + 1 for _, anchor in evidence)
    min_fragment = max(2 * staff.spacing, anchor_width * 0.05)
    potential = [
        [
            span
            for span in spans
            if span == anchor or span[1] - span[0] + 1 >= min_fragment
        ]
        for spans, anchor in evidence
    ]
    common_left = median(min(span[0] for span in spans) for spans in potential)
    common_right = median(max(span[1] for span in spans) for spans in potential)
    slack = max(2 * staff.spacing, width * 0.03)
    refined = []
    for line, (spans, anchor) in zip(staff.lines, evidence, strict=True):
        accepted = [anchor]
        for span in spans:
            if span == anchor or span[1] - span[0] + 1 < min_fragment:
                continue
            if span[0] < common_left - slack or span[1] > common_right + slack:
                continue
            accepted.append(span)
        refined.append(
            replace(
                line,
                x_start=min(span[0] for span in accepted),
                x_end=max(span[1] for span in accepted),
            )
        )
    return replace(
        staff,
        lines=tuple(refined),
        region=replace(
            staff.region,
            left=min(line.x_start for line in refined),
            right=max(line.x_end for line in refined),
        ),
    )


def detect_staffs(image: Image.Image) -> DetectionResult:
    """Detecta geometria horizontal; status não confirma identidade musical.

    Aceita imagem Pillow, sem mutá-la. Grupos concorrentes compartilham linhas e
    são omitidos de staffs, mantendo candidatos e status ambiguous para revisão.
    """
    gray = normalize_image(image).convert("L")
    histogram = gray.histogram()
    threshold = _otsu_threshold(histogram)
    # Imagens uniformes não contêm separação entre fundo e linhas.
    if gray.getextrema()[0] == gray.getextrema()[1]:
        return DetectionResult(
            gray.width,
            gray.height,
            "no_staff",
            (),
            (),
            threshold,
            ("uniform_image",),
            threshold,
        )
    background = max(range(256), key=histogram.__getitem__)
    # Otsu pode omitir bordas claras de linhas suavizadas. O ajuste relativo ao
    # tom mais frequente recupera essas bordas sem fixar intensidade em pixels.
    analysis_threshold = max(
        threshold, round(threshold + 0.30 * (background - threshold))
    )
    pixels = gray.tobytes()
    binary = pixels.translate(bytes(int(i <= analysis_threshold) for i in range(256)))
    lines = _line_candidates(binary, gray.width, gray.height)
    groups = _group_candidates(lines, binary, gray.width, gray.height)
    retried = False
    if not groups and background > threshold:
        # Só ampliar o limiar quando nenhum grupo foi encontrado. Otsu pode
        # selecionar símbolos pretos e ignorar pautas cinzentas mais claras.
        retry_threshold = round(background - 0.1 * (background - gray.getextrema()[0]))
        if retry_threshold > analysis_threshold:
            retried = True
            analysis_threshold = retry_threshold
            binary = pixels.translate(
                bytes(int(i <= analysis_threshold) for i in range(256))
            )
            lines = _line_candidates(binary, gray.width, gray.height)
            groups = _group_candidates(lines, binary, gray.width, gray.height)
    conflicting: set[int] = set()
    for (start, _), (other, _) in zip(groups, groups[1:], strict=False):
        if other - start < 5:
            conflicting.update((start, other))
    staffs = tuple(staff for start, staff in groups if start not in conflicting)
    status = "ambiguous" if conflicting else "detected" if staffs else "no_staff"
    diagnostics = ["horizontal_geometry_only"]
    if analysis_threshold > threshold:
        diagnostics.append("contrast_threshold_adjusted")
    if retried:
        diagnostics.append("contrast_retry")
    if conflicting:
        diagnostics.append("overlapping_five_line_groups")
    if not groups:
        diagnostics.append("insufficient_or_inconsistent_lines")
    if len(lines) > 5 * len(staffs):
        diagnostics.append("unassigned_line_candidates")
    return DetectionResult(
        gray.width,
        gray.height,
        status,
        staffs,
        lines,
        threshold,
        tuple(diagnostics),
        analysis_threshold,
    )


def detect_staffs_file(path: str | Path) -> DetectionResult:
    """API de arquivo PNG/JPEG; dimensões referem-se à orientação normalizada."""
    return detect_staffs(load_image(path))
