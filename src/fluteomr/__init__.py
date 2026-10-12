"""Núcleo geométrico e reconhecimento inicial de clave de sol."""

from fluteomr.clefs import (
    ClefDetectionResult,
    ClefObservation,
    TrebleClef,
    detect_treble_clefs,
)
from fluteomr.score import (
    Part,
    ScorePage,
    StaffRef,
    add_part,
    link_staff,
    page_from_grouping,
    propose_parts_by_order,
    unlink_staff,
)
from fluteomr.staff_detection import DetectionResult, detect_staffs, detect_staffs_file
from fluteomr.systems import MusicSystem, SystemGroupingResult, group_staffs

__all__ = [
    "ClefDetectionResult",
    "ClefObservation",
    "DetectionResult",
    "MusicSystem",
    "Part",
    "ScorePage",
    "StaffRef",
    "SystemGroupingResult",
    "TrebleClef",
    "add_part",
    "detect_staffs",
    "detect_staffs_file",
    "detect_treble_clefs",
    "group_staffs",
    "link_staff",
    "page_from_grouping",
    "propose_parts_by_order",
    "unlink_staff",
]
