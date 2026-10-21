"""Relações geométricas mínimas entre cabeças, hastes e barras de compasso."""

from dataclasses import dataclass
from math import ceil, floor

from PIL import Image

from fluteomr.image_io import normalize_image
from fluteomr.notes import NoteheadObservation
from fluteomr.staff_detection import Region, Staff


@dataclass(frozen=True)
class StemCandidate:
    id: str
    head_id: str
    region: Region
    status: str
    evidence: str


@dataclass(frozen=True)
class BarlineCandidate:
    id: str
    x: int
    region: Region
    coverage: float  # fração de linhas verticais escuras, sem linhas da pauta
    status: str  # accepted, rejected, inconclusive
    evidence: str


def head_id(head: NoteheadObservation, staff_index: int = 0) -> str:
    return f"s{staff_index}-h{head.center_x}-{head.center_y}"


def linked_stems(
    image: Image.Image,
    staff: Staff,
    threshold: int,
    heads: tuple[NoteheadObservation, ...],
    staff_index: int = 0,
) -> tuple[StemCandidate, ...]:
    """Liga a melhor sonda vertical a cada cabeça com haste confirmada."""
    pixels = normalize_image(image).convert("L").load()
    stems = []
    reach = round(3.4 * staff.spacing)
    for head in heads:
        if not head.stem_present:
            continue
        rx = (head.region.right - head.region.left) // 2
        ry = (head.region.bottom - head.region.top) // 2
        probes = []
        for edge in (-1, 1):
            for offset in (-1, 0, 1):
                x = head.center_x + edge * rx + offset
                if not 0 <= x < image.width:
                    continue
                for direction in (-1, 1):
                    start = head.center_y + direction * (ry + 1)
                    end = head.center_y + direction * reach
                    ys = range(min(start, end), max(start, end) + 1)
                    count = sum(
                        pixels[x, y] <= threshold for y in ys if 0 <= y < image.height
                    )
                    probes.append((count, x, start, end))
        if not probes:
            continue
        _, x, start, end = max(probes)
        stems.append(
            StemCandidate(
                f"{head_id(head, staff_index)}-stem",
                head_id(head, staff_index),
                Region(x, min(start, end), x + 1, max(start, end)),
                "accepted",
                "vertical_probe_adjacent_to_head",
            )
        )
    return tuple(stems)


def detect_barlines(
    image: Image.Image,
    staff: Staff,
    threshold: int,
    left: int,
    right: int,
    heads: tuple[NoteheadObservation, ...] = (),
) -> tuple[BarlineCandidate, ...]:
    """Busca tinta quase contínua entre a primeira e quinta linhas da pauta.

    As linhas horizontais são excluídas da cobertura. Uma coluna perto de uma
    cabeça não é aceita como barra, mesmo se cruzar toda a altura da pauta.
    A cobertura global não basta: o traço deve alcançar ambas as bordas.
    Uma extremidade sem suporte mantém o candidato inconclusivo.
    """
    if not 0 <= left < right < image.width:
        raise ValueError("limites fora da imagem")
    gray = normalize_image(image).convert("L")
    pixels = gray.load()
    top = round(staff.lines[0].y)
    bottom = round(staff.lines[-1].y)
    excluded = {
        y
        for line in staff.lines
        for y in range(
            round(line.y - line.thickness / 2) - 1,
            round(line.y + line.thickness / 2) + 2,
        )
    }
    rows = [y for y in range(top, bottom + 1) if y not in excluded]
    if len(rows) < 5:
        return ()
    # Sondar logo após a tinta horizontal, sem a margem extra usada na
    # cobertura global. Uma haste de 3,5 espaços pode cobrir quase toda a
    # pauta mesmo sem alcançar uma das linhas externas.
    edge_depth = max(1, round(0.25 * staff.spacing))
    first = staff.lines[0]
    last = staff.lines[-1]
    inner_top = floor(first.y + (first.thickness - 1) / 2) + 1
    inner_bottom = ceil(last.y - (last.thickness - 1) / 2) - 1
    endpoint_rows = (
        *range(inner_top, inner_top + edge_depth),
        *range(inner_bottom - edge_depth + 1, inner_bottom + 1),
    )
    columns = []
    for x in range(left + 1, right):
        coverage = sum(pixels[x, y] <= threshold for y in rows) / len(rows)
        if coverage >= 0.78:
            columns.append((x, coverage))
    groups: list[list[tuple[int, float]]] = []
    for column in columns:
        if not groups or column[0] - groups[-1][-1][0] > 1:
            groups.append([])
        groups[-1].append(column)
    candidates = []
    for group in groups:
        x = round((group[0][0] + group[-1][0]) / 2)
        coverage = max(value for _, value in group)
        near_head = any(abs(x - head.center_x) <= 1.1 * staff.spacing for head in heads)
        wide = len(group) > max(3, round(0.5 * staff.spacing))
        anchored = all(
            any(pixels[column_x, y] <= threshold for column_x, _ in group)
            for y in endpoint_rows
        )
        status = (
            "rejected"
            if near_head or wide
            else "accepted"
            if anchored
            else "inconclusive"
        )
        reason = (
            "near_notehead"
            if near_head
            else "too_wide"
            if wide
            else "unanchored_staff_endpoint"
            if not anchored
            else "vertical_staff_span"
        )
        candidates.append(
            BarlineCandidate(
                f"s0-b{x}",
                x,
                Region(group[0][0], top, group[-1][0], bottom),
                coverage,
                status,
                reason,
            )
        )
    return tuple(candidates)
