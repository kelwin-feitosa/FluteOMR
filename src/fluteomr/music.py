"""Modelo musical mínimo, independente da geometria de página e das interfaces."""

from dataclasses import asdict, dataclass
from fractions import Fraction
from typing import Literal

from fluteomr.staff_detection import Region

Origin = Literal["image", "configuration", "user", "unknown"]


@dataclass(frozen=True)
class Pitch:
    step: Literal["C", "D", "E", "F", "G", "A", "B"]
    octave: int


@dataclass(frozen=True)
class Duration:
    kind: Literal["eighth", "quarter", "half"]

    @property
    def quarters(self) -> Fraction:
        return {"eighth": Fraction(1, 2), "quarter": Fraction(1), "half": Fraction(2)}[
            self.kind
        ]


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
        beam_open = False
        for index, note in enumerate(self.notes):
            if note.beam is not None and (
                note.duration is None or note.duration.kind != "eighth"
            ):
                problems.append(f"beam_requires_eighth:note={index}")
            if note.beam == "begin":
                if beam_open:
                    problems.append(f"beam_restarted:note={index}")
                beam_open = True
            elif note.beam in ("continue", "end"):
                if not beam_open:
                    problems.append(f"beam_without_begin:note={index}")
                beam_open = note.beam != "end"
            elif beam_open:
                problems.append(f"beam_interrupted:note={index}")
                beam_open = False
        if beam_open:
            problems.append("beam_without_end")
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
