"""Sonda OMR em páginas reais: mede cobertura sem gerar MusicXML não validado."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from time import perf_counter

from fluteomr.document import transcribe_page
from fluteomr.music import Instrument
from fluteomr.pdf_io import load_pdf_page


def probe_pdf(
    source: Path,
    *,
    page_number: int = 1,
    dpi: int = 200,
    report: Path | None = None,
    adaptive_secondary: bool = False,
) -> dict:
    """Executa o reconhecedor completo, sem usar referência nem exportar XML."""
    if report is not None and report.exists():
        raise FileExistsError("relatório existente; não sobrescrever")
    started = perf_counter()
    image = load_pdf_page(source, page_number=page_number, dpi=dpi)
    # O checksum liga as duas variantes aos mesmos bytes e à mesma
    # rasterização; quando o carregamento é simulado, não inventar hash.
    if source.is_file():
        with source.open("rb") as stream:
            source_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    else:
        source_hash = None
    image_hash = hashlib.sha256(image.convert("RGB").tobytes()).hexdigest()
    provenance = {
        "source_pdf_sha256": source_hash,
        "page_image_sha256": image_hash,
        "page_image_size": list(image.size),
    }
    loaded_seconds = perf_counter() - started
    started = perf_counter()
    try:
        options = {
            "layout": "solo",
            "page_number": page_number,
            "instrument": Instrument.flute(),
        }
        if adaptive_secondary:
            options["adaptive_secondary"] = True
        result = transcribe_page(image, **options)
    except (OSError, ValueError) as exc:
        payload = {
            "format_version": 1,
            "source_pdf": source.name,
            **provenance,
            "page_number": page_number,
            "dpi": dpi,
            "experimental_adaptive_secondary": adaptive_secondary,
            "status": "processing_failed",
            "error": str(exc),
            "image_load_seconds": round(loaded_seconds, 4),
            "omr_seconds": round(perf_counter() - started, 4),
            "musical_accuracy": "not_evaluated",
            "xml_export": "not_attempted",
        }
    else:
        notes = [
            note
            for part in result.score.parts
            for measure in part.measures
            for note in measure.notes
        ]
        problems = result.score.issues()
        unknown_durations = [note for note in notes if note.duration is None]
        evidence_counts = Counter(
            diagnostic for note in unknown_durations for diagnostic in note.diagnostics
        )
        payload = {
            "format_version": 1,
            "source_pdf": source.name,
            **provenance,
            "page_number": page_number,
            "dpi": dpi,
            "experimental_adaptive_secondary": adaptive_secondary,
            "status": "diagnostic_only",
            "staff_results": list(result.staff_results),
            "staff_count": len(result.staff_results),
            "predicted_measures": sum(len(p.measures) for p in result.score.parts),
            "predicted_events": len(notes),
            "resolved_pitch_events": sum(note.pitch is not None for note in notes),
            "resolved_duration_events": len(notes) - len(unknown_durations),
            "resolved_duration_kind_counts": dict(
                sorted(
                    Counter(
                        note.duration.kind
                        for note in notes
                        if note.duration is not None
                    ).items()
                )
            ),
            "predicted_double_beam_sixteenths": sum(
                note.duration is not None
                and note.duration.kind == "sixteenth"
                and "double_beam" in note.diagnostics
                for note in notes
            ),
            "confirmed_mixed_beam_note_count": sum(
                "verified_partial_secondary_group" in note.diagnostics for note in notes
            ),
            "confirmed_mixed_beam_duration_counts": dict(
                sorted(
                    Counter(
                        note.duration.kind
                        for note in notes
                        if note.duration is not None
                        and "verified_partial_secondary_group" in note.diagnostics
                    ).items()
                )
            ),
            "unresolved_duration_events": len(unknown_durations),
            "unresolved_duration_diagnostic_counts": dict(
                sorted(evidence_counts.items())
            ),
            "issues": list(problems),
            "issue_count": len(problems),
            "image_load_seconds": round(loaded_seconds, 4),
            "omr_seconds": round(perf_counter() - started, 4),
            "musical_accuracy": "not_evaluated",
            "reference_events": None,
            "xml_export": "not_attempted",
            "warning": (
                "Não há MusicXML independente revisado para essa página. "
                "Contagem de predições não é acerto musical; "
                "símbolos não suportados podem escapar à detecção."
            ),
        }
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        with report.open("x", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--adaptive-secondary",
        action="store_true",
        help="Perfiles de bandas: experimental, desativado por padrão",
    )
    args = parser.parse_args()
    try:
        result = probe_pdf(
            args.pdf,
            page_number=args.page,
            dpi=args.dpi,
            report=args.report,
            adaptive_secondary=args.adaptive_secondary,
        )
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"{exc}\n")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "staff_results"},
            ensure_ascii=False,
            indent=2,
        )
    )
    if result["status"] == "processing_failed":
        parser.exit(1, "Falha registrada; relatório disponível.\n")


if __name__ == "__main__":
    main()
