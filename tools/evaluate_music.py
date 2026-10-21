"""Laboratório local: transcreve imagens antes de abrir referências MusicXML."""

import argparse
import json
from pathlib import Path
from time import perf_counter
from xml.etree import ElementTree as ET

from fluteomr.image_io import load_image
from fluteomr.music_evaluation import evaluate_music, parse_reference
from fluteomr.musicxml import to_musicxml
from fluteomr.transcription import transcribe_measures, transcribe_one_measure


def evaluate_manifest(
    manifest_path: Path,
    images_dir: Path,
    *,
    continue_on_error: bool = False,
    splits: set[str] | None = None,
) -> list[dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1 or not isinstance(
        manifest.get("examples"), list
    ):
        raise ValueError("manifesto inválido ou versão não suportada")
    rows = []
    for example in manifest["examples"]:
        if example["split"] not in ("development", "validation", "test"):
            raise ValueError("split inválido")
        if splits is not None and example["split"] not in splits:
            continue
        if example["reference_status"] not in (
            "source_authored",
            "validated",
            "draft",
            "missing",
        ):
            raise ValueError("estado da referência inválido")
        configured = example["configured"]
        if (
            configured.get("clef", "treble") != "treble"
            or configured.get("time", "4/4") != "4/4"
        ):
            raise ValueError("laboratório atual exige clave de sol e fórmula 4/4")
        if type(configured.get("auto_bars", False)) is not bool:
            raise ValueError("auto_bars deve ser booleano")
        image_name = Path(example["image"])
        reference_name = (
            None
            if example["reference_status"] == "missing"
            else Path(example["reference"])
        )
        if image_name.name != str(image_name) or (
            reference_name is not None and reference_name.name != str(reference_name)
        ):
            raise ValueError("use somente nomes de arquivo no manifesto")
        image_path = images_dir / image_name
        started = perf_counter()
        row = {
            "id": example["id"],
            "image": image_name.name,
            "origin": example["origin"],
            "split": example["split"],
            "reference_status": example["reference_status"],
            "work_id": example.get("work_id", example["id"]),
        }
        for key in ("source_category", "renderer", "font", "dpi"):
            if key in example:
                row[key] = example[key]
        score = None
        try:
            image = load_image(image_path)
            row["image_size"] = [image.width, image.height]
            if configured.get("auto_bars", False):
                score = transcribe_measures(
                    image,
                    content_left=configured["measure_left"],
                    content_right=configured["measure_right"],
                ).score
            else:
                score = transcribe_one_measure(
                    image,
                    measure_left=configured["measure_left"],
                    measure_right=configured["measure_right"],
                )
        except (OSError, ValueError) as exc:
            if not continue_on_error:
                raise
            row["processing_error"] = str(exc)
        row["processing_seconds"] = round(perf_counter() - started, 4)
        row["predicted_events"] = (
            sum(len(m.notes) for p in score.parts for m in p.measures)
            if score
            else None
        )
        row["predicted_measures"] = (
            sum(len(p.measures) for p in score.parts) if score else None
        )
        row["prediction_issues"] = score.issues() if score else None
        try:
            if score is None:
                raise ValueError("processing_failed")
            ET.fromstring(to_musicxml(score))
            row["xml_export"] = "well_formed_not_schema_validated"
        except ValueError:
            row["xml_export"] = "blocked_by_prediction_issues"
        if example["reference_status"] in ("draft", "missing"):
            row["evaluation"] = "not_evaluated"
            row["evaluation_reason"] = (
                "missing_human_reference"
                if example["reference_status"] == "missing"
                else "reference_not_validated"
            )
        else:
            # O XML de referência só é lido depois da inferência.
            reference = (manifest_path.parent / reference_name).read_bytes()
            parts = parse_reference(reference)
            row["reference_events"] = sum(len(m.events) for p in parts for m in p)
            row["reference_measures"] = sum(len(p) for p in parts)
            row["evaluation"] = (
                evaluate_music(reference, score) if score else "not_evaluated"
            )
            if score is None:
                row["evaluation_reason"] = "processing_failed"
        rows.append(row)
    return rows


def summarize_results(rows: list[dict]) -> dict:
    """Conta variantes sem chamá-las de obras independentes ou esconder falhas."""
    summary = {
        "images": len(rows),
        "musical_works": len({row.get("work_id", row["id"]) for row in rows}),
        "processing_failures": sum("processing_error" in row for row in rows),
        "reference_events": 0,
        "reference_measures": 0,
        "predicted_measures": sum(row.get("predicted_measures") or 0 for row in rows),
        "complete_matches": 0,
        "unevaluated_reference_events": 0,
        "measures": {"correct": 0, "incorrect": 0, "unevaluable": 0, "total": 0},
    }
    for row in rows:
        summary["reference_measures"] += row.get("reference_measures", 0)
        metrics = row.get("evaluation")
        if isinstance(metrics, dict):
            summary["reference_events"] += metrics["reference_events"]
            summary["complete_matches"] += metrics["matches"]
            summary["unevaluated_reference_events"] += metrics[
                "skipped_reference_events"
            ]
            for key in summary["measures"]:
                summary["measures"][key] += metrics["measure_metrics"][key]
        elif "reference_events" in row:
            summary["reference_events"] += row["reference_events"]
            summary["unevaluated_reference_events"] += row["reference_events"]
            summary["measures"]["total"] += row["reference_measures"]
            summary["measures"]["unevaluable"] += row["reference_measures"]
    summary["match_fraction"] = (
        {
            "matched": summary["complete_matches"],
            "expected": summary["reference_events"],
        }
        if summary["reference_events"]
        else "not_evaluated"
    )
    summary["match_fraction_kind"] = "confirmed_matches_over_all_known_reference_events"
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Comparar transcrições com referências musicais"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, help="novo relatório JSON")
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="registrar falhas individuais e continuar o lote",
    )
    parser.add_argument(
        "--summary", action="store_true", help="incluir resumo com denominadores"
    )
    parser.add_argument(
        "--split",
        action="append",
        choices=("development", "validation", "test"),
        help="processar somente os conjuntos explicitamente selecionados",
    )
    args = parser.parse_args()
    if args.report and args.report.exists():
        parser.error("relatório já existe")
    try:
        rows = evaluate_manifest(
            args.manifest,
            args.images_dir,
            continue_on_error=args.continue_on_error,
            splits=set(args.split) if args.split else None,
        )
        if not rows:
            raise ValueError("manifesto sem exemplos")
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        ET.ParseError,
    ) as exc:
        parser.error(str(exc))
    output = (
        {"images": rows, "summary": summarize_results(rows)} if args.summary else rows
    )
    report = json.dumps(output, indent=2, ensure_ascii=False) + "\n"
    print(report, end="")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")
    if any("processing_error" in row for row in rows):
        parser.exit(1, "Lote concluído com falhas de processamento.\n")


if __name__ == "__main__":
    main()
