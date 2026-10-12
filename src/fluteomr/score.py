"""Estrutura de página, sistemas e partes; não identifica instrumentos."""

from dataclasses import dataclass, replace
from typing import Literal

from fluteomr.systems import MusicSystem, SystemGroupingResult


@dataclass(frozen=True)
class StaffRef:
    """Referência a uma pauta original de um sistema nesta página."""

    system_id: int
    staff_index: int
    source: Literal["manual", "hypothesis"]


@dataclass(frozen=True)
class Part:
    """Parte lógica; uma pauta por sistema, sem pressupor o instrumento."""

    id: int
    instrument: str | None = None
    instrument_source: Literal["unknown", "user"] = "unknown"
    staffs: tuple[StaffRef, ...] = ()


@dataclass(frozen=True)
class ScorePage:
    """Sistemas ordenados e associações editáveis de partes nesta página."""

    systems: tuple[MusicSystem, ...]
    parts: tuple[Part, ...] = ()


def page_from_grouping(grouping: SystemGroupingResult) -> ScorePage:
    return ScorePage(grouping.systems)


def add_part(page: ScorePage, instrument: str | None = None) -> ScorePage:
    """Cria parte sem associar pautas ou deduzir instrumento da imagem."""
    if instrument is not None and not instrument.strip():
        raise ValueError("Instrumento vazio")
    next_id = max((part.id for part in page.parts), default=-1) + 1
    part = Part(next_id, instrument, "user" if instrument else "unknown")
    return replace(page, parts=(*page.parts, part))


def link_staff(
    page: ScorePage, part_id: int, system_id: int, staff_index: int
) -> ScorePage:
    """Associação manual; substitui a pauta anterior da parte no sistema."""
    if not any(part.id == part_id for part in page.parts):
        raise ValueError("Parte inexistente")
    system = next((s for s in page.systems if s.id == system_id), None)
    if system is None or staff_index not in system.staff_indices:
        raise ValueError("Pauta não pertence ao sistema")
    if any(
        ref.system_id == system_id and ref.staff_index == staff_index
        for part in page.parts
        if part.id != part_id
        for ref in part.staffs
    ):
        raise ValueError("Pauta já associada a outra parte")
    new_parts = []
    for part in page.parts:
        if part.id != part_id:
            new_parts.append(part)
            continue
        refs = tuple(ref for ref in part.staffs if ref.system_id != system_id)
        refs = (*refs, StaffRef(system_id, staff_index, "manual"))
        refs = tuple(sorted(refs, key=lambda ref: ref.system_id))
        new_parts.append(replace(part, staffs=refs))
    return replace(page, parts=tuple(new_parts))


def unlink_staff(page: ScorePage, part_id: int, system_id: int) -> ScorePage:
    """Remove uma ligação para permitir correção ou omissão de pauta."""
    if not any(part.id == part_id for part in page.parts):
        raise ValueError("Parte inexistente")
    return replace(
        page,
        parts=tuple(
            replace(
                part,
                staffs=tuple(ref for ref in part.staffs if ref.system_id != system_id),
            )
            if part.id == part_id
            else part
            for part in page.parts
        ),
    )


def propose_parts_by_order(grouping: SystemGroupingResult) -> ScorePage:
    """Hipótese explícita apenas para sistemas confirmados de igual tamanho.

    Não identifica instrumentos. Se o agrupamento é ambíguo ou há pauta ausente,
    abstém-se e deixa as associações para revisão manual.
    """
    page = page_from_grouping(grouping)
    systems = grouping.systems
    if grouping.status != "grouped" or not systems:
        return page
    count = len(systems[0].staff_indices)
    if any(len(system.staff_indices) != count for system in systems):
        return page
    parts = tuple(
        Part(
            rank,
            staffs=tuple(
                StaffRef(system.id, system.staff_indices[rank], "hypothesis")
                for system in systems
            ),
        )
        for rank in range(count)
    )
    return replace(page, parts=parts)
