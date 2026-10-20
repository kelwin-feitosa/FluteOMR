"""Laboratório local: transcreve imagens antes de abrir referências MusicXML."""

import argparse
import json
from pathlib import Path
from time import perf_counter
from xml.etree import ElementTree as ET

from fluteomr.image_io import load_image
from fluteomr.music_evaluation import evaluate_music
from fluteomr.musicxml import to_musicxml
from fluteomr.transcription import transcribe_one_measure


def evaluate_manifest(manifest_path: Path, images_dir: Path) -> list[dict]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1 or not isinstance(
        manifest.get("examples"), list
    ):
        raise ValueError("manifesto inválido ou versão não suportada")
    rows = []
    for example in manifest["examples"]:
        if example["split"] not in ("development", "validation", "test"):
            raise ValueError("split inválido")
        if example["reference_status"] not in ("source_authored", "validated", "draft"):
            raise ValueError("estado da referência inválido")
        configured = example["configured"]
        if (
            configured.get("clef", "treble") != "treble"
            or configured.get("time", "4/4") != "4/4"
        ):
            raise ValueError("laboratório atual exige clave de sol e fórmula 4/4")
        image_name = Path(example["image"])
        reference_name = Path(example["reference"])
        if image_name.name != str(image_name) or reference_name.name != str(
            reference_name
        ):
            raise ValueError("use somente nomes de arquivo no manifesto")
        image_path = images_dir / image_name
        started = perf_counter()
        score = transcribe_one_measure(
            load_image(image_path),
            measure_left=configured["measure_left"],
            measure_right=configured["measure_right"],
        )
        elapsed = round(perf_counter() - started, 4)
        row = {
            "id": example["id"],
            "image": image_name.name,
            "origin": example["origin"],
            "split": example["split"],
            "reference_status": example["reference_status"],
            "processing_seconds": elapsed,
            "prediction_issues": score.issues(),
        }
        try:
            ET.fromstring(to_musicxml(score))
            row["xml_export"] = "well_formed_not_schema_validated"
        except ValueError:
            row["xml_export"] = "blocked_by_prediction_issues"
        if example["reference_status"] == "draft":
            row["evaluation"] = "not_evaluated"
        else:
            # O XML de referência só é lido depois da inferência.
            reference = (manifest_path.parent / reference_name).read_bytes()
            row["evaluation"] = evaluate_music(reference, score)
        rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Comparar transcrições com referências musicais"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--images-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, help="novo relatório JSON")
    args = parser.parse_args()
    if args.report and args.report.exists():
        parser.error("relatório já existe")
    try:
        rows = evaluate_manifest(args.manifest, args.images_dir)
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
    report = json.dumps(rows, indent=2, ensure_ascii=False) + "\n"
    print(report, end="")
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
