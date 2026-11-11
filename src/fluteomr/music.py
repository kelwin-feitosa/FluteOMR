"""Modelo musical mínimo, independente da geometria de página e das interfaces."""

from dataclasses import asdict, dataclass
from fractions import Fraction
from typing import Literal

from fluteomr.staff_detection import Region

Origin = Literal["image", "configuration", "user", "unknown"]
BeamPosition = Literal[
    "begin", "continue", "end", "forward hook", "backward hook"
]


@dataclass(frozen=True)
class Pitch:
    step: Literal["C", "D", "E", "F", "G", "A", "B"]
    octave: int


@dataclass(frozen=True)
class Duration:
    kind: Literal["sixteenth", "eighth", "quarter", "half"]

    @property
    def quarters(self) -> Fraction:
        return {
            "sixteenth": Fraction(1, 4),
            "eighth": Fraction(1, 2),
            "quarter": Fraction(1),
            "half": Fraction(2),
        }[self.kind]


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
    beam: Literal["begin", "continue", "end"] | None = None
    # Explicit per-note MusicXML beams. Empty means legacy single/full-beam behavior.
    beam_levels: tuple[tuple[int, BeamPosition], ...] = ()

    @property
    def status(self) -> Literal["recognized", "inconclusive"]:
        return "recognized" if self.pitch and self.duration else "inconclusive"


def note_beam_levels(note: Note) -> tuple[tuple[int, BeamPosition], ...]:
    """Preserva o contrato legado; níveis explícitos permitem hooks e grupos mistos."""
    if note.beam_levels:
        return note.beam_levels
    if note.beam is None:
        return ()
    primary = ((1, note.beam),)
    if note.duration is not None and note.duration.kind == "sixteenth":
        return (*primary, (2, note.beam))
    return primary


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
class Instrument:
    """Identidade fornecida, separada do nome da parte e da observação visual.

    ``midi_program`` segue MusicXML (1–128), não a numeração MIDI de 0–127.
    Nenhum instrumento é escolhido automaticamente pelo reconhecedor.
    """

    name: str
    sound: str | None = None
    midi_program: int | None = None
    origin: Literal["configuration", "user"] = "configuration"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("nome do instrumento deve ser preenchido")
        if self.origin not in ("configuration", "user"):
            raise ValueError(
                "instrumento deve ser informado por configuração ou usuário"
            )
        if self.midi_program is not None and (
            type(self.midi_program) is not int or not 1 <= self.midi_program <= 128
        ):
            raise ValueError("programa MIDI MusicXML deve ser inteiro entre 1 e 128")

    @classmethod
    def flute(
        cls, *, origin: Literal["configuration", "user"] = "configuration"
    ) -> "Instrument":
        """Flauta transversal em Dó, sem transposição nem restrição de tessitura."""
        return cls("Flute", "wind.flutes.flute", 74, origin)


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
        primary_open = False
        secondary_open = False
        primary_group: list[tuple[int, Note]] = []
        for index, note in enumerate(self.notes):
            kind = note.duration.kind if note.duration else None
            levels = note_beam_levels(note)
            if (
                not isinstance(levels, tuple)
                or any(
                    not isinstance(item, tuple)
                    or len(item) != 2
                    or type(item[0]) is not int
                    or item[0] not in (1, 2)
                    or item[1] not in (
                        "begin",
                        "continue",
                        "end",
                        "forward hook",
                        "backward hook",
                    )
                    for item in levels
                )
            ):
                problems.append(f"beam_levels_invalid:note={index}")
                continue
            positions = dict(levels)
            if len(positions) != len(levels) or tuple(positions) != tuple(
                sorted(positions)
            ):
                problems.append(f"beam_levels_invalid:note={index}")
            if note.beam is not None and note.beam_levels and positions.get(1) != note.beam:
                problems.append(f"beam_primary_conflict:note={index}")
            if levels and kind not in ("eighth", "sixteenth"):
                problems.append(f"beam_requires_eighth:note={index}")
            if 2 in positions and (1 not in positions or kind != "sixteenth"):
                problems.append(f"secondary_beam_invalid:note={index}")
            if 1 in positions and kind == "sixteenth" and 2 not in positions:
                problems.append(f"secondary_beam_missing:note={index}")

            primary = positions.get(1)
            if primary == "begin":
                if primary_open:
                    problems.append(f"beam_restarted:note={index}")
                primary_open = True
                primary_group = [(index, note)]
            elif primary in ("continue", "end"):
                if not primary_open:
                    problems.append(f"beam_without_begin:note={index}")
                primary_group.append((index, note))
                if primary == "end":
                    # Legacy mixed groups have no explicit level 2 information.
                    # Never assign implied partial beams solely from durations.
                    kinds = {
                        member.duration.kind
                        for _, member in primary_group
                        if member.duration is not None
                    }
                    if len(kinds) > 1 and any(
                        not member.beam_levels for _, member in primary_group
                    ):
                        problems.append(f"mixed_beam_durations:note={index}")
                    primary_open = False
                    primary_group = []
            else:
                if primary is not None:
                    problems.append(f"primary_beam_hook_invalid:note={index}")
                if primary_open:
                    problems.append(f"beam_interrupted:note={index}")
                primary_open = False
                primary_group = []

            secondary = positions.get(2)
            if secondary == "begin":
                if secondary_open:
                    problems.append(f"secondary_beam_restarted:note={index}")
                secondary_open = True
            elif secondary in ("continue", "end"):
                if not secondary_open:
                    problems.append(f"secondary_beam_without_begin:note={index}")
                secondary_open = secondary != "end"
            elif secondary in ("forward hook", "backward hook"):
                if secondary_open:
                    problems.append(f"secondary_beam_interrupted:note={index}")
                    secondary_open = False
            elif secondary_open:
                problems.append(f"secondary_beam_interrupted:note={index}")
                secondary_open = False
            if primary == "end" and secondary_open:
                problems.append(f"secondary_beam_without_end:note={index}")
                secondary_open = False
        if primary_open:
            problems.append("beam_without_end")
        if secondary_open:
            problems.append("secondary_beam_without_end")
        return tuple(problems)


@dataclass(frozen=True)
class MusicPart:
    id: str
    name: str
    name_origin: Origin
    staff_indices: tuple[int, ...]
    clef: Clef
    measures: tuple[Measure, ...]
    instrument: Instrument | None = None


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
