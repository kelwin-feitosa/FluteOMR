"""Reconhecimento experimental e conservador de clave de sol impressa."""

from dataclasses import asdict, dataclass
from math import ceil, floor
from typing import Literal

from PIL import Image, ImageFilter

from fluteomr.image_io import normalize_image
from fluteomr.staff_detection import DetectionResult, Region, Staff, StaffLine


@dataclass(frozen=True)
class TrebleClef:
    kind: Literal["treble"]
    staff_index: int
    region: Region
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class ClefObservation:
    staff_index: int
    status: Literal["detected", "no_treble", "inconclusive"]
    clef: TrebleClef | None
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class ClefDetectionResult:
    observations: tuple[ClefObservation, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class _Component:
    left: int
    top: int
    right: int
    bottom: int
    pixels: int
    upper_width: int
    lower_width: int


def _components(
    mask: bytearray, width: int, height: int, split_y: int
) -> list[_Component]:
    visited = bytearray(len(mask))
    result = []
    for start in range(len(mask)):
        if not mask[start] or visited[start]:
            continue
        visited[start] = 1
        stack = [start]
        xs = []
        ys = []
        while stack:
            index = stack.pop()
            x, y = index % width, index // width
            xs.append(x)
            ys.append(y)
            for ny in range(max(0, y - 1), min(height, y + 2)):
                for nx in range(max(0, x - 1), min(width, x + 2)):
                    neighbor = ny * width + nx
                    if mask[neighbor] and not visited[neighbor]:
                        visited[neighbor] = 1
                        stack.append(neighbor)
        upper = [x for x, y in zip(xs, ys, strict=True) if y < split_y]
        lower = [x for x, y in zip(xs, ys, strict=True) if y >= split_y]
        result.append(
            _Component(
                min(xs),
                min(ys),
                max(xs),
                max(ys),
                len(xs),
                max(upper) - min(upper) + 1 if upper else 0,
                max(lower) - min(lower) + 1 if lower else 0,
            )
        )
    return result


def _symbol_mask(
    image: Image.Image,
    region: Region,
    lines: tuple[StaffLine, ...],
    threshold: int,
) -> tuple[bytearray, int, int, int, int]:
    left = max(0, floor(region.left))
    top = max(0, floor(region.top))
    right = min(image.width - 1, ceil(region.right))
    bottom = min(image.height - 1, ceil(region.bottom))
    crop = image.crop((left, top, right + 1, bottom + 1))
    width, height = crop.size
    original = bytearray(int(pixel <= threshold) for pixel in crop.tobytes())
    mask = original.copy()
    for line in lines:
        center = line.y - top
        band_top = max(0, floor(center - line.thickness / 2))
        band_bottom = min(height - 1, ceil(center + line.thickness / 2))
        if band_top == 0 or band_bottom == height - 1:
            continue
        for y in range(band_top, band_bottom + 1):
            for x in range(width):
                index = y * width + x
                if not original[index]:
                    continue
                above = any(
                    original[(band_top - 1) * width + nx]
                    for nx in range(max(0, x - 1), min(width, x + 2))
                )
                below = any(
                    original[(band_bottom + 1) * width + nx]
                    for nx in range(max(0, x - 1), min(width, x + 2))
                )
                if not (above and below):
                    mask[index] = 0
    return mask, left, top, width, height


def _plausible_components(
    components: list[_Component], staff: Staff, left: int, top: int
) -> list[_Component]:
    spacing = staff.spacing
    plausible = []
    for component in components:
        absolute_top, absolute_bottom = component.top + top, component.bottom + top
        component_width = component.right - component.left + 1
        component_height = absolute_bottom - absolute_top + 1
        if (
            4.8 * spacing <= component_height <= 10 * spacing
            and 0.9 * spacing <= component_width <= 4.5 * spacing
            and left + component.left >= staff.region.left + 0.3 * spacing
            and absolute_top <= staff.region.top - 0.5 * spacing
            and absolute_bottom >= staff.region.bottom + 0.4 * spacing
            and component.upper_width >= 0.8 * spacing
            and component.lower_width >= 0.8 * spacing
            and component.pixels >= 1.2 * spacing * spacing
        ):
            plausible.append(component)
    return plausible


def detect_treble_clefs(
    image: Image.Image, detection: DetectionResult
) -> ClefDetectionResult:
    """Inspeciona início das pautas detectadas, sem alterar a detecção legada.

    Exige componente alto com curvas largas acima e abaixo da pauta. Isto não é
    um classificador completo de clave: candidatos ausentes ou concorrentes são
    explicitamente registrados.
    """
    gray = normalize_image(image).convert("L")
    if gray.size != (detection.width, detection.height):
        raise ValueError("Dimensões da imagem e da detecção não coincidem")
    observations = []
    for staff_index, staff in enumerate(detection.staffs):
        spacing = staff.spacing
        search = Region(
            max(0, staff.region.left - 1.5 * spacing),
            max(0, staff.region.top - 3 * spacing),
            min(staff.region.right, staff.region.left + 12 * spacing),
            min(gray.height - 1, staff.region.bottom + 3 * spacing),
        )
        mask, left, top, width, height = _symbol_mask(
            gray, search, staff.lines, detection.threshold
        )
        split_y = round(staff.lines[2].y - top)
        components = _components(mask, width, height, split_y)
        plausible = _plausible_components(components, staff, left, top)
        if not plausible:
            # Tenta religar pequenos cortes de rasterização somente quando a
            # máscara original não fornece uma clave válida.
            bridged = Image.frombytes("L", (width, height), bytes(mask)).filter(
                ImageFilter.MaxFilter(3)
            )
            plausible = _plausible_components(
                _components(bytearray(bridged.tobytes()), width, height, split_y),
                staff,
                left,
                top,
            )
        if len(plausible) == 1:
            component = plausible[0]
            clef = TrebleClef(
                "treble",
                staff_index,
                Region(
                    left + component.left,
                    top + component.top,
                    left + component.right,
                    top + component.bottom,
                ),
                ("tall_cross_staff_component", "upper_and_lower_horizontal_spread"),
            )
            observations.append(ClefObservation(staff_index, "detected", clef, ()))
        else:
            status = "inconclusive" if len(plausible) > 1 else "no_treble"
            reason = (
                "multiple_plausible_components"
                if plausible
                else "no_matching_component"
            )
            observations.append(ClefObservation(staff_index, status, None, (reason,)))
    return ClefDetectionResult(tuple(observations))
