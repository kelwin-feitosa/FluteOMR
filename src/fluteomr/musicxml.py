"""Serialização mínima e estrita de compassos melódicos em MusicXML."""

from xml.etree import ElementTree as ET

from fluteomr.music import MusicScore, note_beam_levels


def to_musicxml(score: MusicScore) -> bytes:
    """Recusa saída final quando faltam eventos essenciais ou a duração não fecha."""
    _validate_supported_model(score)
    issues = score.issues()
    if issues:
        raise ValueError(f"transcrição incompleta: {', '.join(issues)}")
    if not score.parts:
        raise ValueError("partitura sem partes")
    kinds = {
        note.duration.kind
        for part in score.parts
        for measure in part.measures
        for note in measure.notes
    }
    divisions = 4 if "sixteenth" in kinds else 2 if "eighth" in kinds else 1
    root = ET.Element("score-partwise", version="4.0")
    part_list = ET.SubElement(root, "part-list")
    for part in score.parts:
        listed = ET.SubElement(part_list, "score-part", id=part.id)
        ET.SubElement(listed, "part-name").text = part.name
        if part.instrument is not None:
            instrument_id = f"{part.id}-I1"
            instrument = ET.SubElement(listed, "score-instrument", id=instrument_id)
            ET.SubElement(instrument, "instrument-name").text = part.instrument.name
            if part.instrument.sound is not None:
                ET.SubElement(
                    instrument, "instrument-sound"
                ).text = part.instrument.sound
            if part.instrument.midi_program is not None:
                midi = ET.SubElement(listed, "midi-instrument", id=instrument_id)
                ET.SubElement(midi, "midi-program").text = str(
                    part.instrument.midi_program
                )
    for part in score.parts:
        part_element = ET.SubElement(root, "part", id=part.id)
        for measure in part.measures:
            element = ET.SubElement(part_element, "measure", number=str(measure.number))
            attributes = ET.SubElement(element, "attributes")
            ET.SubElement(attributes, "divisions").text = str(divisions)
            time = ET.SubElement(attributes, "time")
            ET.SubElement(time, "beats").text = str(measure.time_signature.beats)
            ET.SubElement(time, "beat-type").text = str(
                measure.time_signature.beat_type
            )
            clef = ET.SubElement(attributes, "clef")
            ET.SubElement(clef, "sign").text = "G"
            ET.SubElement(clef, "line").text = "2"
            for note in measure.notes:
                note_element = ET.SubElement(element, "note")
                pitch = ET.SubElement(note_element, "pitch")
                ET.SubElement(pitch, "step").text = note.pitch.step
                ET.SubElement(pitch, "octave").text = str(note.pitch.octave)
                ET.SubElement(note_element, "duration").text = str(
                    note.duration.quarters * divisions
                )
                ET.SubElement(note_element, "type").text = (
                    "16th" if note.duration.kind == "sixteenth" else note.duration.kind
                )
                for level, position in note_beam_levels(note):
                    ET.SubElement(
                        note_element, "beam", number=str(level)
                    ).text = position
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml.replace(
        b"?>",
        b"?>\n<!DOCTYPE score-partwise  PUBLIC "
        b'"-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
        b'"http://www.musicxml.org/dtds/partwise.dtd">',
        1,
    )


def _validate_supported_model(score: MusicScore) -> None:
    """Tipagem estática não valida dados construídos por consumidores da API.

    Recusa valores que o serializador não sabe preservar, sem convertê-los em
    outro símbolo. Não é validação completa pelo esquema MusicXML.
    """
    from re import fullmatch

    ids: set[str] = set()
    for part in score.parts:
        if (
            not isinstance(part.id, str)
            or not fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", part.id)
            or part.id in ids
        ):
            raise ValueError("identificador de parte inválido ou repetido")
        ids.add(part.id)
        if part.clef.kind != "treble":
            raise ValueError("clave não suportada pelo exportador")
        numbers = [measure.number for measure in part.measures]
        if (
            not numbers
            or any(type(n) is not int or n < 1 for n in numbers)
            or numbers != sorted(set(numbers))
        ):
            raise ValueError("compassos ausentes, repetidos ou fora de ordem")
        for measure in part.measures:
            time = measure.time_signature
            if any(type(v) is not int or v < 1 for v in (time.beats, time.beat_type)):
                raise ValueError("fórmula de compasso inválida")
            for note in measure.notes:
                if note.pitch is not None and (
                    note.pitch.step not in ("C", "D", "E", "F", "G", "A", "B")
                    or type(note.pitch.octave) is not int
                ):
                    raise ValueError("altura escrita inválida ou não suportada")
                if note.duration is not None and note.duration.kind not in (
                    "sixteenth",
                    "eighth",
                    "quarter",
                    "half",
                ):
                    raise ValueError("duração não suportada pelo exportador")
                if note.beam not in (None, "begin", "continue", "end"):
                    raise ValueError("feixe não suportado pelo exportador")
                if not isinstance(note.beam_levels, tuple):
                    raise ValueError("níveis de feixe precisam ser uma tupla")
                # Score.issues() verifica as conexões e os hooks. O exportador
                # nunca converte valores inválidos em feixes aproximados.
