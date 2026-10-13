"""Comparação de eventos escritos, independente dos detectores de imagem."""

from dataclasses import dataclass
from fractions import Fraction
from xml.etree import ElementTree as ET

from fluteomr.music import MusicScore


@dataclass(frozen=True)
class Event:
    step: str | None
    octave: int | None
    duration: Fraction | None
    unsupported: str | None = None


@dataclass(frozen=True)
class MeasureEvents:
    number: int
    events: tuple[Event, ...]


def parse_reference(xml: bytes) -> tuple[tuple[MeasureEvents, ...], ...]:
    """Lê somente notas monofônicas escritas de um MusicXML partwise."""
    root = ET.fromstring(xml)
    if root.tag != "score-partwise":
        raise ValueError("referência exige score-partwise")
    parts = []
    for part in root.findall("part"):
        measures = []
        divisions = None
        for measure in part.findall("measure"):
            new_divisions = measure.findtext("attributes/divisions")
            if new_divisions is not None:
                divisions = int(new_divisions)
            if not divisions or divisions < 1:
                raise ValueError("divisions ausente ou inválido")
            events = []
            for note in measure.findall("note"):
                raw_duration = note.findtext("duration")
                duration = (
                    Fraction(int(raw_duration), divisions)
                    if raw_duration is not None
                    else None
                )
                if note.find("rest") is not None:
                    events.append(Event(None, None, duration, "rest"))
                    continue
                if note.find("chord") is not None or note.find("grace") is not None:
                    events.append(Event(None, None, duration, "chord_or_grace"))
                    continue
                pitch = note.find("pitch")
                if pitch is None:
                    events.append(Event(None, None, duration, "missing_pitch"))
                    continue
                step = pitch.findtext("step")
                octave = pitch.findtext("octave")
                if (
                    step is None
                    or step not in "CDEFGAB"
                    or octave is None
                    or duration is None
                ):
                    raise ValueError("nota de referência incompleta")
                alter = pitch.findtext("alter")
                events.append(
                    Event(
                        step,
                        int(octave),
                        duration,
                        "chromatic_alteration" if alter is not None else None,
                    )
                )
            number = measure.get("number")
            if number is None or not number.isdecimal():
                raise ValueError("número de compasso ausente ou não numérico")
            if any(previous.number == int(number) for previous in measures):
                raise ValueError("número de compasso repetido")
            measures.append(MeasureEvents(int(number), tuple(events)))
        parts.append(tuple(measures))
    if not parts:
        raise ValueError("referência sem partes")
    return tuple(parts)


def _align(reference: tuple[Event, ...], prediction: tuple[Event, ...]) -> dict:
    """Levenshtein unitário; empate prefere substituir, depois omitir."""
    rows = len(reference) + 1
    cols = len(prediction) + 1
    cost = [[0] * cols for _ in range(rows)]
    operations = [[""] * cols for _ in range(rows)]
    for i in range(1, rows):
        cost[i][0], operations[i][0] = i, "omission"
    for j in range(1, cols):
        cost[0][j], operations[0][j] = j, "insertion"
    for i in range(1, rows):
        for j in range(1, cols):
            same = reference[i - 1] == prediction[j - 1]
            options = (
                (cost[i - 1][j - 1] + (not same), "match" if same else "substitution"),
                (cost[i - 1][j] + 1, "omission"),
                (cost[i][j - 1] + 1, "insertion"),
            )
            cost[i][j], operations[i][j] = min(options, key=lambda item: item[0])
    counts = dict.fromkeys(
        (
            "matches",
            "insertions",
            "omissions",
            "substitutions",
            "pitch_errors",
            "octave_errors",
            "duration_errors",
            "pitch_correct_aligned",
            "duration_correct_aligned",
        ),
        0,
    )
    i, j = len(reference), len(prediction)
    while i or j:
        operation = operations[i][j]
        if operation in ("match", "substitution"):
            truth, found = reference[i - 1], prediction[j - 1]
            counts["pitch_correct_aligned"] += (
                truth.step == found.step and truth.octave == found.octave
            )
            counts["duration_correct_aligned"] += truth.duration == found.duration
            if operation == "substitution":
                counts["pitch_errors"] += truth.step != found.step
                counts["octave_errors"] += truth.octave != found.octave
                counts["duration_errors"] += truth.duration != found.duration
            counts["matches" if operation == "match" else "substitutions"] += 1
            i -= 1
            j -= 1
        elif operation == "omission":
            counts["omissions"] += 1
            i -= 1
        else:
            counts["insertions"] += 1
            j -= 1
    return counts


def evaluate_music(reference_xml: bytes, prediction: MusicScore) -> dict:
    """Compara por ordem de partes e número ordinal de compasso, sem inferir pixels."""
    reference = parse_reference(reference_xml)
    predicted = tuple(
        tuple(
            MeasureEvents(
                measure.number,
                tuple(
                    Event(
                        note.pitch.step if note.pitch else None,
                        note.pitch.octave if note.pitch else None,
                        Fraction(note.duration.quarters) if note.duration else None,
                        "inconclusive" if not note.pitch or not note.duration else None,
                    )
                    for note in measure.notes
                ),
            )
            for measure in part.measures
        )
        for part in prediction.parts
    )
    totals = dict.fromkeys(
        (
            "matches",
            "insertions",
            "omissions",
            "substitutions",
            "pitch_errors",
            "octave_errors",
            "duration_errors",
            "pitch_correct_aligned",
            "duration_correct_aligned",
        ),
        0,
    )
    measure_errors = {"omissions": 0, "insertions": 0}
    unsupported = {}
    skipped_reference_events = skipped_predicted_events = 0
    for part in (*reference, *predicted):
        for measure in part:
            for event in measure.events:
                if event.unsupported:
                    unsupported[event.unsupported] = (
                        unsupported.get(event.unsupported, 0) + 1
                    )
    expected_count = sum(len(m.events) for p in reference for m in p)
    predicted_count = sum(len(m.events) for p in predicted for m in p)
    for part_index in range(max(len(reference), len(predicted))):
        truth_part = {
            measure.number: measure.events
            for measure in (
                reference[part_index] if part_index < len(reference) else ()
            )
        }
        found_part = {
            measure.number: measure.events
            for measure in (
                predicted[part_index] if part_index < len(predicted) else ()
            )
        }
        if len(found_part) != (
            len(predicted[part_index]) if part_index < len(predicted) else 0
        ):
            raise ValueError("número de compasso previsto repetido")
        for number in sorted(truth_part.keys() | found_part.keys()):
            if number not in truth_part:
                measure_errors["insertions"] += 1
                totals["insertions"] += sum(
                    not event.unsupported for event in found_part[number]
                )
                continue
            if number not in found_part:
                measure_errors["omissions"] += 1
                totals["omissions"] += sum(
                    not event.unsupported for event in truth_part[number]
                )
                continue
            truth, found = truth_part[number], found_part[number]
            if any(event.unsupported for event in (*truth, *found)):
                skipped_reference_events += len(truth)
                skipped_predicted_events += len(found)
                continue
            for key, value in _align(truth, found).items():
                totals[key] += value
    return {
        "status": "partial" if unsupported else "evaluated",
        "reference_xml_parsed": True,
        "notation_graphics": "not_evaluated",
        "reference_parts": len(reference),
        "predicted_parts": len(predicted),
        "part_errors": {
            "omissions": max(0, len(reference) - len(predicted)),
            "insertions": max(0, len(predicted) - len(reference)),
        },
        "reference_measures": sum(map(len, reference)),
        "predicted_measures": sum(map(len, predicted)),
        "measure_alignment": "explicit_number",
        "reference_events": expected_count,
        "predicted_events": predicted_count,
        "measure_errors": measure_errors,
        "unsupported": unsupported,
        "skipped_reference_events": skipped_reference_events,
        "skipped_predicted_events": skipped_predicted_events,
        "inconclusive_predicted_events": sum(
            event.unsupported == "inconclusive"
            for part in predicted
            for measure in part
            for event in measure.events
        ),
        "duration_coverage": {
            "resolved": sum(
                event.duration is not None
                for part in predicted
                for measure in part
                for event in measure.events
            ),
            "total": predicted_count,
        },
        "aligned_events": totals["matches"] + totals["substitutions"],
        "full_match_fraction": (
            "not_evaluated"
            if unsupported or not expected_count
            else {"matched": totals["matches"], "expected": expected_count}
        ),
        **totals,
    }
