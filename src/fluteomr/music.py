"""Modelo musical mínimo, independente da geometria de página e das interfaces."""

from dataclasses import asdict, dataclass
from typing import Literal

from fluteomr.staff_detection import Region

Origin = Literal["image", "configuration", "user", "unknown"]


@dataclass(frozen=True)
class Pitch:
    step: Literal["C", "D", "E", "F", "G", "A", "B"]
    octave: int


@dataclass(frozen=True)
class Duration:
    kind: Literal["quarter", "half"]

    @property
    def quarters(self) -> int:
        return 1 if self.kind == "quarter" else 2


@dataclass(frozen=True)
class Note:
    pitch: Pitch | None
    duration: Duration | None
    source_region: Region
    staff_index: int
    visual_kind: Literal["filled", "hollow", "unknown"]
    diagnostics: tuple[str, ...] = ()
    pitch_origin: Origin = "image"
    duration_origin: Origin = "image"
    candidate_id: str | None = None
    source_page: int = 1

    @property
    def status(self) -> Literal["recognized", "inconclusive"]:
        return "recognized" if self.pitch and self.duration else "inconclusive"


@dataclass(frozen=True)
class Clef:
    kind: Literal["treble"]
    origin: Origin


@dataclass(frozen=True)
class TimeSignature:
    beats: int
    beat_type: int
    origin: Origin

    @property
    def measure_quarters(self) -> int:
        if self.beat_type != 4:
            raise ValueError("apenas denominador 4 é suportado nesta sprint")
        return self.beats


@dataclass(frozen=True)
class Measure:
    number: int
    notes: tuple[Note, ...]
    time_signature: TimeSignature
    boundary_origin: Origin
    source_region: Region | None = None
    boundary_candidate_ids: tuple[str, ...] = ()
    boundary_origins: tuple[Origin, Origin] = ("configuration", "configuration")

    def issues(self) -> tuple[str, ...]:
        problems = []
        if any(note.pitch is None for note in self.notes):
            problems.append("unknown_pitch")
        if any(note.duration is None for note in self.notes):
            problems.append("unknown_duration")
        if all(note.duration is not None for note in self.notes):
            total = sum(note.duration.quarters for note in self.notes if note.duration)
            if total != self.time_signature.measure_quarters:
                problems.append(
                    f"measure_duration_mismatch:{total}/{self.time_signature.measure_quarters}"
                )
        return tuple(problems)


@dataclass(frozen=True)
class MusicPart:
    id: str
    name: str
    name_origin: Origin
    staff_indices: tuple[int, ...]
    clef: Clef
    measures: tuple[Measure, ...]


@dataclass(frozen=True)
class MusicScore:
    parts: tuple[MusicPart, ...]
    diagnostics: tuple[str, ...] = ()

    def issues(self) -> tuple[str, ...]:
        return (
            *self.diagnostics,
            *(
                issue
                for part in self.parts
                for measure in part.measures
                for issue in measure.issues()
            ),
        )

    def to_dict(self) -> dict:
        return {**asdict(self), "issues": self.issues()}
