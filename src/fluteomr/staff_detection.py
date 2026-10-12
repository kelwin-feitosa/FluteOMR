"""Projeção horizontal e validação geométrica de cinco linhas.

Coordenadas em pixels na imagem normalizada: origem superior esquerda,
x para a direita, y para baixo. Extremos e bounding boxes são inclusivos.
"""

from dataclasses import asdict, dataclass
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
    positions = [x for x, pixel in enumerate(row) if pixel]
    if not positions:
        return None
    max_gap = max(1, round(len(row) * 0.02))
    start = previous = positions[0]
    spans = []
    for x in positions[1:]:
        if x - previous - 1 > max_gap:
            spans.append((start, previous))
            start = x
        previous = x
    spans.append((start, previous))
    return max(spans, key=lambda span: span[1] - span[0])


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
    if any(abs(gap - spacing) > 0.15 * spacing for gap in gaps):
        return None
    if any(line.thickness > 0.35 * spacing for line in lines):
        return None
    left = max(line.x_start for line in lines)
    right = min(line.x_end for line in lines)
    min_length = min(line.x_end - line.x_start + 1 for line in lines)
    if right - left + 1 < 0.8 * min_length:
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


def detect_staffs(image: Image.Image) -> DetectionResult:
    """Detecta geometria horizontal; status não confirma identidade musical.

    Aceita imagem Pillow, sem mutá-la. Grupos concorrentes compartilham linhas e
    são omitidos de staffs, mantendo candidatos e status ambiguous para revisão.
    """
    gray = normalize_image(image).convert("L")
    threshold = _otsu_threshold(gray.histogram())
    # Imagens uniformes não contêm separação entre fundo e linhas.
    if gray.getextrema()[0] == gray.getextrema()[1]:
        return DetectionResult(
            gray.width, gray.height, "no_staff", (), (), threshold, ("uniform_image",)
        )
    binary = gray.tobytes().translate(bytes(int(i <= threshold) for i in range(256)))
    lines = _line_candidates(binary, gray.width, gray.height)
    groups = []
    for start in range(max(0, len(lines) - 4)):
        staff = _make_staff(lines[start : start + 5])
        if staff is not None:
            groups.append((start, staff))
    conflicting: set[int] = set()
    for (start, _), (other, _) in zip(groups, groups[1:], strict=False):
        if other - start < 5:
            conflicting.update((start, other))
    staffs = tuple(staff for start, staff in groups if start not in conflicting)
    status = "ambiguous" if conflicting else "detected" if staffs else "no_staff"
    diagnostics = ["horizontal_geometry_only"]
    if conflicting:
        diagnostics.append("overlapping_five_line_groups")
    if not groups:
        diagnostics.append("insufficient_or_inconsistent_lines")
    if len(lines) > 5 * len(staffs):
        diagnostics.append("unassigned_line_candidates")
    return DetectionResult(
        gray.width, gray.height, status, staffs, lines, threshold, tuple(diagnostics)
    )


def detect_staffs_file(path: str | Path) -> DetectionResult:
    """API de arquivo PNG/JPEG; dimensões referem-se à orientação normalizada."""
    return detect_staffs(load_image(path))
