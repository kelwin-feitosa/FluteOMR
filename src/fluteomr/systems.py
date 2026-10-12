"""Agrupamento conservador de pautas em sistemas pela geometria da página."""

from dataclasses import asdict, dataclass
from math import sqrt
from statistics import median
from typing import Literal

from fluteomr.staff_detection import Region, Staff


@dataclass(frozen=True)
class MusicSystem:
    """Pautas na ordem da página; índices referem-se à detecção original."""

    id: int
    staff_indices: tuple[int, ...]
    staffs: tuple[Staff, ...]
    region: Region


@dataclass(frozen=True)
class SystemGroupingResult:
    systems: tuple[MusicSystem, ...]
    status: Literal["grouped", "ambiguous", "empty"]
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict:
        return {**asdict(self), "system_count": len(self.systems)}


def _system(
    indices: tuple[int, ...], staffs: tuple[Staff, ...], id: int
) -> MusicSystem:
    members = tuple(staffs[index] for index in indices)
    return MusicSystem(
        id,
        indices,
        members,
        Region(
            min(staff.region.left for staff in members),
            min(staff.region.top for staff in members),
            max(staff.region.right for staff in members),
            max(staff.region.bottom for staff in members),
        ),
    )


def group_staffs(staffs: tuple[Staff, ...]) -> SystemGroupingResult:
    """Separa sistemas quando as lacunas verticais formam duas escalas claras.

    Sem duas escalas, devolve pautas isoladas com status ambíguo: uma sequência
    uniforme pode ser solo ou um conjunto; a imagem precisará de outra evidência.
    """
    if not staffs:
        return SystemGroupingResult((), "empty", ())
    ordered = tuple(sorted(range(len(staffs)), key=lambda i: staffs[i].region.top))
    if len(ordered) == 1:
        return SystemGroupingResult((_system(ordered, staffs, 0),), "grouped", ())

    gaps = [
        staffs[b].region.top - staffs[a].region.bottom
        for a, b in zip(ordered, ordered[1:], strict=False)
    ]
    if any(gap <= 0 for gap in gaps):
        return SystemGroupingResult(
            tuple(_system((index,), staffs, n) for n, index in enumerate(ordered)),
            "ambiguous",
            ("overlapping_staff_regions",),
        )
    sorted_gaps = sorted(gaps)
    # São necessárias pelo menos duas lacunas pequenas para definir uma escala
    # interna; um único par não diferencia dois sistemas de um sistema duplo.
    cuts = [
        (sorted_gaps[i + 1] / sorted_gaps[i], i) for i in range(1, len(sorted_gaps) - 1)
    ]
    ratio, cut = max(cuts, default=(0.0, -1))
    if ratio < 1.5:
        return SystemGroupingResult(
            tuple(_system((index,), staffs, n) for n, index in enumerate(ordered)),
            "ambiguous",
            ("no_distinct_inter_system_gap",),
        )
    boundary = sqrt(sorted_gaps[cut] * sorted_gaps[cut + 1])
    groups: list[list[int]] = [[ordered[0]]]
    for gap, index in zip(gaps, ordered[1:], strict=True):
        if gap > boundary:
            groups.append([])
        groups[-1].append(index)

    # A separação baseada somente em distância fica inconclusiva se a faixa
    # interna também variar muito ou produzir apenas sistemas de uma pauta.
    intra = [gap for gap in gaps if gap <= boundary]
    if not intra or max(intra) > 1.5 * median(intra):
        return SystemGroupingResult(
            tuple(_system((index,), staffs, n) for n, index in enumerate(ordered)),
            "ambiguous",
            ("inconsistent_inner_gaps",),
        )
    for indices in groups:
        members = [staffs[index] for index in indices]
        if len(members) < 2:
            continue
        left = max(staff.region.left for staff in members)
        right = min(staff.region.right for staff in members)
        shortest = min(staff.region.right - staff.region.left + 1 for staff in members)
        if right - left + 1 < 0.5 * shortest:
            return SystemGroupingResult(
                tuple(_system((index,), staffs, n) for n, index in enumerate(ordered)),
                "ambiguous",
                ("weak_horizontal_alignment",),
            )
    return SystemGroupingResult(
        tuple(_system(tuple(indices), staffs, n) for n, indices in enumerate(groups)),
        "grouped",
        ("vertical_gap_clusters",),
    )
