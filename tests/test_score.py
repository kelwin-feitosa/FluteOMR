"""Partes são associações lógicas editáveis, separadas da geometria."""

import pytest

from fluteomr.score import (
    ScorePage,
    add_part,
    link_staff,
    page_from_grouping,
    propose_parts_by_order,
    unlink_staff,
)
from fluteomr.staff_detection import Region
from fluteomr.systems import MusicSystem, SystemGroupingResult
from tests.test_systems import make_staff


def grouping(sizes: tuple[int, ...], status: str = "grouped"):
    systems = []
    index = 0
    top = 20
    for system_id, size in enumerate(sizes):
        staffs = tuple(make_staff(top + 50 * rank) for rank in range(size))
        systems.append(
            MusicSystem(
                system_id,
                tuple(range(index, index + size)),
                staffs,
                Region(20, staffs[0].region.top, 380, staffs[-1].region.bottom),
            )
        )
        top += 50 * size + 90
        index += size
    return SystemGroupingResult(tuple(systems), status, ())


@pytest.mark.parametrize("size", [1, 2, 4, 7])
def test_explicit_order_hypothesis_for_solo_duet_quartet_and_variable_size(size):
    result = grouping((size, size, size))
    page = propose_parts_by_order(result)
    assert len(page.parts) == size
    assert page.systems == result.systems
    for rank, part in enumerate(page.parts):
        assert part.id == rank
        assert part.instrument is None
        assert part.instrument_source == "unknown"
        assert [(ref.system_id, ref.staff_index) for ref in part.staffs] == [
            (system_id, system_id * size + rank) for system_id in range(3)
        ]
        assert all(ref.source == "hypothesis" for ref in part.staffs)


def test_unknown_instruments_and_user_identified_instrument():
    page = page_from_grouping(grouping((2, 2)))
    page = add_part(page)
    page = add_part(page, "Flauta transversal")
    assert [part.instrument for part in page.parts] == [None, "Flauta transversal"]
    assert [part.instrument_source for part in page.parts] == ["unknown", "user"]
    with pytest.raises(ValueError, match="Instrumento vazio"):
        add_part(page, " ")


def test_missing_part_in_a_system_requires_manual_links():
    result = grouping((2, 1, 2))
    assert propose_parts_by_order(result).parts == ()
    page = add_part(add_part(page_from_grouping(result)))
    page = link_staff(page, 0, 0, 0)
    page = link_staff(page, 0, 1, 2)
    page = link_staff(page, 0, 2, 3)
    page = link_staff(page, 1, 0, 1)
    page = link_staff(page, 1, 2, 4)
    assert [ref.system_id for ref in page.parts[0].staffs] == [0, 1, 2]
    assert [ref.system_id for ref in page.parts[1].staffs] == [0, 2]


def test_manual_correction_preserves_original_references_and_order():
    page = propose_parts_by_order(grouping((2, 2)))
    original = page.systems[1].staffs[0]
    page = unlink_staff(page, 1, 1)
    page = link_staff(page, 0, 1, 3)
    page = link_staff(page, 1, 1, 2)
    assert page.parts[0].staffs[1].staff_index == 3
    assert page.parts[0].staffs[1].source == "manual"
    assert page.parts[1].staffs[1].staff_index == 2
    assert page.systems[1].staffs[0] is original
    assert [system.id for system in page.systems] == [0, 1]


def test_ambiguous_grouping_does_not_create_parts():
    page = propose_parts_by_order(grouping((1, 1, 1), "ambiguous"))
    assert page.parts == ()
    assert isinstance(page, ScorePage)


def test_invalid_and_duplicate_references_are_rejected():
    page = add_part(add_part(page_from_grouping(grouping((2, 2)))))
    with pytest.raises(ValueError, match="Parte inexistente"):
        link_staff(page, 99, 0, 0)
    with pytest.raises(ValueError, match="Pauta não pertence"):
        link_staff(page, 0, 1, 0)
    page = link_staff(page, 0, 0, 0)
    with pytest.raises(ValueError, match="já associada"):
        link_staff(page, 1, 0, 0)


def test_link_replacement_keeps_one_staff_per_system():
    page = add_part(page_from_grouping(grouping((2, 2))))
    page = link_staff(page, 0, 0, 0)
    page = link_staff(page, 0, 0, 1)
    assert len(page.parts[0].staffs) == 1
    assert page.parts[0].staffs[0].staff_index == 1
