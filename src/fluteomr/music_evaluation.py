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
    unsupported: str | None = None


def parse_reference(xml: bytes) -> tuple[tuple[MeasureEvents, ...], ...]:
    """Lê somente notas monofônicas escritas de um MusicXML partwise."""
    root = ET.fromstring(xml)
    if root.tag != "score-partwise":
        raise ValueError("referência exige score-partwise")
    parts = []
    for part in root.findall("part"):
        measures = []
        divisions = None
        key_status = None
        time_status = None
        clef_status = None
        for measure in part.findall("measure"):
            new_divisions = measure.findtext("attributes/divisions")
            if new_divisions is not None:
                divisions = int(new_divisions)
            if not divisions or divisions < 1:
                raise ValueError("divisions ausente ou inválido")

            # Elementos de attributes valem até uma próxima alteração explícita.
            # Não podemos pontuar F# como F natural quando há armadura, mesmo
            # que o XML omita <alter> nas notas individuais.
            key = measure.find("attributes/key")
            if key is not None:
                fifths = key.findtext("fifths")
                if fifths is None:
                    key_status = "nontraditional_key"
                else:
                    key_status = "key_signature" if int(fifths) != 0 else None
            time = measure.find("attributes/time")
            if time is not None:
                beats = time.findtext("beats")
                beat_type = time.findtext("beat-type")
                time_status = (
                    None if (beats, beat_type) == ("4", "4") else "time_signature"
                )
            clef = measure.find("attributes/clef")
            if clef is not None:
                clef_status = (
                    None
                    if (clef.findtext("sign"), clef.findtext("line")) == ("G", "2")
                    else "clef"
                )
            # A ordem XML não é a ordem temporal quando o cursor é reposicionado.
            # Não achatar vozes/pautas simultâneas como uma melodia monofônica.
            voices = {note.findtext("voice", "1") for note in measure.findall("note")}
            staffs = {note.findtext("staff", "1") for note in measure.findall("note")}
            measure_unsupported = None
            if (
                measure.find("backup") is not None
                or measure.find("forward") is not None
            ):
                measure_unsupported = "time_cursor"
            elif len(voices) > 1 or len(staffs) > 1:
                measure_unsupported = "multiple_voices_or_staffs"
            else:
                measure_unsupported = key_status or time_status or clef_status
            events = []
            for note in measure.findall("note"):
                raw_duration = note.findtext("duration")
                duration = (
                    Fraction(int(raw_duration), divisions)
                    if raw_duration is not None
                    else None
                )
                if duration is not None and duration <= 0:
                    raise ValueError("duração de referência deve ser positiva")
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
                    or step not in tuple("CDEFGAB")
                    or octave is None
                    or duration is None
                ):
                    raise ValueError("nota de referência incompleta")
                alter = pitch.findtext("alter")
                unsupported = "chromatic_alteration" if alter is not None else None
                if (
                    note.find("tie") is not None
                    or note.find("notations/tied") is not None
                ):
                    unsupported = "tie"
                events.append(
                    Event(
                        step,
                        int(octave),
                        duration,
                        unsupported,
                    )
                )
            number = measure.get("number")
            if number is None or not number.isdecimal():
                raise ValueError("número de compasso ausente ou não numérico")
            if any(previous.number == int(number) for previous in measures):
                raise ValueError("número de compasso repetido")
            measures.append(
                MeasureEvents(int(number), tuple(events), measure_unsupported)
            )
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
    """Compara por ordem de partes e número explícito de compasso.

    Resultados semânticos inconclusivos não pontuam eventos. Compassos ausentes
    ou extras são incorretos mesmo vazios; os demais sem suporte são
    inevaluáveis. A fração de compassos conserva a união completa no denominador.
    """
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
    measure_results = []
    unsupported = {}
    skipped_reference_events = skipped_predicted_events = 0
    for part in (*reference, *predicted):
        for measure in part:
            if measure.unsupported:
                unsupported[measure.unsupported] = (
                    unsupported.get(measure.unsupported, 0) + 1
                )
            for event in measure.events:
                if event.unsupported:
                    unsupported[event.unsupported] = (
                        unsupported.get(event.unsupported, 0) + 1
                    )
    expected_count = sum(len(m.events) for p in reference for m in p)
    predicted_count = sum(len(m.events) for p in predicted for m in p)
    for part_index in range(max(len(reference), len(predicted))):
        truth_part = {
            measure.number: measure
            for measure in (
                reference[part_index] if part_index < len(reference) else ()
            )
        }
        found_part = {
            measure.number: measure
            for measure in (
                predicted[part_index] if part_index < len(predicted) else ()
            )
        }
        if len(found_part) != (
            len(predicted[part_index]) if part_index < len(predicted) else 0
        ):
            raise ValueError("número de compasso previsto repetido")
        for number in sorted(truth_part.keys() | found_part.keys()):
            truth_measure = truth_part.get(number)
            found_measure = found_part.get(number)
            truth = truth_measure.events if truth_measure else ()
            found = found_measure.events if found_measure else ()
            row = {
                "part_index": part_index,
                "number": number,
                "alignment": "aligned",
                "status": "incorrect",
                "reference_events": len(truth),
                "predicted_events": len(found),
                "unsupported": {},
                "inconclusive_predicted_events": sum(
                    event.unsupported == "inconclusive" for event in found
                ),
                "skipped_reference_events": 0,
                "skipped_predicted_events": 0,
                **dict.fromkeys(totals, 0),
            }
            for measure in (truth_measure, found_measure):
                if measure is None:
                    continue
                for reason in (
                    measure.unsupported,
                    *(e.unsupported for e in measure.events),
                ):
                    if reason:
                        row["unsupported"][reason] = (
                            row["unsupported"].get(reason, 0) + 1
                        )
            if number not in truth_part:
                measure_errors["insertions"] += 1
                row["alignment"] = "insertion"
                row["insertions"] = sum(not event.unsupported for event in found)
                row["skipped_predicted_events"] = sum(
                    bool(event.unsupported) for event in found
                )
            elif number not in found_part:
                measure_errors["omissions"] += 1
                row["alignment"] = "omission"
                if truth_measure.unsupported:
                    row["skipped_reference_events"] = len(truth)
                else:
                    row["omissions"] = sum(not event.unsupported for event in truth)
                    row["skipped_reference_events"] = sum(
                        bool(event.unsupported) for event in truth
                    )
            elif truth_measure.unsupported or any(
                event.unsupported for event in (*truth, *found)
            ):
                row["status"] = "unevaluable"
                row["skipped_reference_events"] = len(truth)
                row["skipped_predicted_events"] = len(found)
            else:
                row.update(_align(truth, found))
                if not any(
                    row[key] for key in ("insertions", "omissions", "substitutions")
                ):
                    row["status"] = "correct"
            row["aligned_events"] = row["matches"] + row["substitutions"]
            row["evaluated_reference_events"] = (
                len(truth) - row["skipped_reference_events"]
            )
            row["evaluated_predicted_events"] = (
                len(found) - row["skipped_predicted_events"]
            )
            measure_results.append(row)
            skipped_reference_events += row["skipped_reference_events"]
            skipped_predicted_events += row["skipped_predicted_events"]
            for key in totals:
                totals[key] += row[key]
    correct_measures = sum(row["status"] == "correct" for row in measure_results)
    return {
        "status": "partial" if unsupported else "evaluated",
        "reference_xml_parsed": True,
        "reference_xml_schema_validated": False,
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
        "measure_results": measure_results,
        "measure_metrics": {
            "reference": sum(map(len, reference)),
            "predicted": sum(map(len, predicted)),
            "aligned": sum(row["alignment"] == "aligned" for row in measure_results),
            "total": len(measure_results),
            "correct": correct_measures,
            "incorrect": sum(row["status"] == "incorrect" for row in measure_results),
            "unevaluable": sum(
                row["status"] == "unevaluable" for row in measure_results
            ),
            **measure_errors,
            "correct_fraction": (
                {"correct": correct_measures, "total": len(measure_results)}
                if measure_results
                else "not_evaluated"
            ),
        },
        "unsupported": unsupported,
        "unsupported_reference_events": sum(
            bool(measure.unsupported or event.unsupported)
            for part in reference
            for measure in part
            for event in measure.events
        ),
        "unsupported_predicted_events": sum(
            bool(measure.unsupported or event.unsupported)
            for part in predicted
            for measure in part
            for event in measure.events
        ),
        "skipped_reference_events": skipped_reference_events,
        "skipped_predicted_events": skipped_predicted_events,
        "evaluated_reference_events": expected_count - skipped_reference_events,
        "evaluated_predicted_events": predicted_count - skipped_predicted_events,
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
