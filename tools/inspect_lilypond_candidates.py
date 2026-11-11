"""Inventário de MusicXML derivado de fonte LilyPond (NÃO é ground truth humano).

Não converte partituras nem altera as fontes. A conversão precisa ocorrer
externamente; este módulo só valida e descreve candidatos.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

MAX_MUSICXML_BYTES = 16 * 1024 * 1024


class CandidateReferenceError(ValueError):
    """Fonte ou candidata inexistente, inválida ou impossível de auditar."""


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _analyse_xml(path: Path) -> dict:
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_MUSICXML_BYTES:
        raise CandidateReferenceError("MusicXML ausente ou acima do limite")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise CandidateReferenceError(f"MusicXML não parseável: {path.name}") from exc
    if root.tag.endswith("}score-partwise"):
        namespace = root.tag.split("}", 1)[0] + "}"
    elif root.tag == "score-partwise":
        namespace = ""
    else:
        raise CandidateReferenceError("somente score-partwise é permitido")
    def q(name: str) -> str:
        return namespace + name

    parts = root.findall(q("part"))
    if not parts:
        raise CandidateReferenceError("nenhuma parte musical encontrada")
    measures = [measure for part in parts for measure in part.findall(q("measure"))]
    if not measures:
        raise CandidateReferenceError("partes sem compassos")
    all_notes = [note for measure in measures for note in measure.findall(q("note"))]
    pitch_count = sum(note.find(q("pitch")) is not None for note in all_notes)
    if not pitch_count:
        raise CandidateReferenceError("MusicXML sem notas com altura")

    types = Counter()
    rests = missing_durations = 0
    first_measure = []
    for part in parts:
        for index, measure in enumerate(part.findall(q("measure"))):
            for note in measure.findall(q("note")):
                is_rest = note.find(q("rest")) is not None
                rests += is_rest
                typ = note.findtext(q("type")) or "unspecified"
                types[typ] += 1
                raw_duration = note.findtext(q("duration"))
                if raw_duration is None:
                    missing_durations += 1
                elif not raw_duration.isdecimal() or int(raw_duration) <= 0:
                    raise CandidateReferenceError("duração numérica inválida")
                if index == 0 and len(first_measure) < 24:
                    pitch = note.find(q("pitch"))
                    pitch_step = pitch_alter = pitch_octave = None
                    if pitch is not None:
                        pitch_step = pitch.findtext(q("step"))
                        pitch_alter = pitch.findtext(q("alter"))
                        pitch_octave = pitch.findtext(q("octave"))
                    first_measure.append(
                        {
                            "part_id": part.get("id"),
                            "measure_number": measure.get("number"),
                            "rest": is_rest,
                            "step": pitch_step,
                            "alter": pitch_alter,
                            "octave": pitch_octave,
                            "type": typ,
                            "duration_ticks": raw_duration,
                        }
                    )
    return {
        "parts": len(parts),
        "measures_across_parts": len(measures),
        "events": len(all_notes),
        "pitched_events": pitch_count,
        "rests": rests,
        "missing_duration_elements": missing_durations,
        "types": dict(sorted(types.items())),
        "first_measure_preview": first_measure,
    }


def _read_prefix_guard(source: Path, manifest: Path) -> tuple[list[dict], str]:
    """Verifica que o prefixo anotado consta na MESMA fonte versionada."""
    if not manifest.is_file() or manifest.stat().st_size > 64 * 1024:
        raise CandidateReferenceError("anotação de prefixo ausente ou muito grande")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("format_version") != 1:
        raise CandidateReferenceError("versão da anotação incompatível")
    if data.get("source_sha256") != _sha256(source):
        raise CandidateReferenceError("hash da fonte diferente da anotação")
    literal = data.get("source_literal")
    if not isinstance(literal, str) or not 2 <= len(literal) <= 180:
        raise CandidateReferenceError("prefixo literal inválido")
    if literal not in source.read_text(encoding="utf-8"):
        raise CandidateReferenceError("trecho anotado não existe no LilyPond")
    expected = data.get("expected_events")
    if not isinstance(expected, list) or not 1 <= len(expected) <= 24:
        raise CandidateReferenceError("lista de eventos de prefixo inválida")
    for event in expected:
        if not isinstance(event, dict) or set(event) != {
            "rest", "type", "step", "alter", "octave"
        }:
            raise CandidateReferenceError("evento de prefixo inválido")
        if type(event["rest"]) is not bool or event["type"] not in (
            "16th", "eighth", "quarter", "half"
        ):
            raise CandidateReferenceError("tipo de evento de prefixo inválido")
        if event["rest"] and any(event[key] is not None for key in (
            "step", "alter", "octave"
        )):
            raise CandidateReferenceError("pausa não deve ter altura")
    return expected, literal


def _verify_prefix(candidate: dict, expected: list[dict]) -> dict:
    preview = candidate["first_measure_preview"]
    details = []
    for index, wanted in enumerate(expected):
        observed = preview[index] if index < len(preview) else None
        found = (
            {key: observed[key] for key in wanted}
            if observed is not None
            else None
        )
        if found != wanted:
            details.append({
                "event_index": index,
                "expected": wanted,
                "observed": found,
            })
    return {
        "status": "mismatch" if details else "prefix_matches_only",
        "compared_events": len(expected),
        "mismatches": details,
    }


def inspect_source_candidates(
    source: Path,
    candidate_dir: Path,
    report: Path,
    *,
    expected_prefix: Path | None = None,
) -> dict:
    """Gera manifesto estritamente classificado como conversão NÃO revisada."""
    source = source.resolve()
    candidate_dir = candidate_dir.resolve()
    report = report.resolve()
    if source.suffix.lower() != ".ly" or not source.is_file():
        raise CandidateReferenceError("fonte LilyPond .ly é obrigatória")
    if not candidate_dir.is_dir():
        raise CandidateReferenceError("pasta de MusicXML não encontrada")
    if report.exists():
        raise FileExistsError("não sobrescrever relatórios existentes")
    paths = sorted(candidate_dir.rglob("*.musicxml"))
    if not paths:
        raise CandidateReferenceError("nenhum arquivo MusicXML foi gerado")
    expected = None
    if expected_prefix is not None:
        expected, _ = _read_prefix_guard(source, expected_prefix)
    entries = []
    for path in paths:
        inspected = _analyse_xml(path)
        entry = {
            "file": path.relative_to(candidate_dir).as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
            **inspected,
        }
        if expected is not None:
            entry["source_prefix_check"] = _verify_prefix(entry, expected)
        entries.append(entry)
    contradicted = expected is not None and all(
        entry["source_prefix_check"]["status"] == "mismatch" for entry in entries
    )
    result = {
        "format_version": 1,
        "origin": "LilyPond engraving source, not FluteOMR predictions",
        "source": {
            "filename": source.name,
            "sha256": _sha256(source),
        },
        "candidate_count": len(entries),
        "candidates": entries,
        "reference_quality": (
            "rejected_source_prefix_mismatch"
            if contradicted
            else "source_derived_unreviewed"
        ),
        "source_prefix_alignment": (
            "mismatch" if contradicted else "prefix_only" if expected else "not_checked"
        ),
        "usable_as_music_ground_truth": False,
        "human_reviewed": False,
        "same_engraving_as_pdf_verified": False,
        "score_alignment_verified": False,
        "music_accuracy": "not_evaluated",
        "caveat": (
            "Conversão automática pode mudar notas, articulações, "
            "repetições, fórmulas e compassos. Conferir contra a edição "
            "publicada ANTES de usar como referência para precisão OMR."
        ),
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-prefix", type=Path)
    args = parser.parse_args()
    try:
        result = inspect_source_candidates(
            args.source,
            args.candidates,
            args.report,
            expected_prefix=args.expected_prefix,
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
