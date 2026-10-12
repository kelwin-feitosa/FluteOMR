"""Sugestões, revisão explícita e avaliação de referências anotadas."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from PIL import ImageDraw, UnidentifiedImageError

from fluteomr.annotations import (
    SCHEMA_VERSION,
    AnnotationError,
    image_sha256,
    load_reference,
    validate_reference,
    verify_image,
)
from fluteomr.clefs import detect_treble_clefs
from fluteomr.debug import render_clefs_debug_image
from fluteomr.image_io import load_image
from fluteomr.metrics import NOT_EVALUABLE, aggregate_reports, evaluate_page
from fluteomr.staff_detection import detect_staffs
from fluteomr.systems import group_staffs


def _write_json(path: Path, data: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _predictions(image):
    detection = detect_staffs(image)
    grouping = group_staffs(detection.staffs)
    clefs = detect_treble_clefs(image, detection)
    predicted = {
        "staffs": [asdict(staff) for staff in detection.staffs],
        "systems": {
            "status": grouping.status,
            "groups": [list(system.staff_indices) for system in grouping.systems],
            "diagnostics": list(grouping.diagnostics),
        },
        "clefs": [
            {
                "status": observation.status,
                "region": asdict(observation.clef.region)
                if observation.clef is not None
                else None,
                "diagnostics": list(observation.diagnostics),
            }
            for observation in clefs.observations
        ],
    }
    return detection, grouping, clefs, predicted


def _review_image(image, detection, grouping, clefs):
    output = render_clefs_debug_image(image, detection, clefs, grouping)
    draw = ImageDraw.Draw(output)
    for index, staff in enumerate(detection.staffs):
        draw.text(
            (max(0, staff.region.left - 22), max(0, round(staff.region.top))),
            f"s{index}",
            fill="blue",
        )
    for index, observation in enumerate(clefs.observations):
        if observation.clef is not None:
            box = observation.clef.region
            draw.text(
                (box.left, max(0, round(box.top) - 10)), f"c{index}", fill="green"
            )
    return output


def _draft(image_info: dict, predicted: dict) -> dict:
    staffs = [
        {
            "id": f"s{index}",
            "order": index,
            "review_state": "unknown",
            "region": staff["region"],
            "lines": [
                {key: line[key] for key in ("x_start", "x_end", "y")}
                for line in staff["lines"]
            ],
        }
        for index, staff in enumerate(predicted["staffs"])
    ]
    systems = [
        {
            "id": f"sys{index}",
            "order": index,
            "staff_ids": [f"s{staff_index}" for staff_index in group],
            "review_state": "uncertain",
            "partial_visible": False,
        }
        for index, group in enumerate(predicted["systems"]["groups"])
    ]
    clefs = [
        {"staff_id": staff["id"], "state": "unknown", "kind": None, "region": None}
        for staff in staffs
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "reference",
        "split": "unspecified",
        "review": {"status": "draft", "confirmed_by": None},
        "image": image_info,
        "coverage": {"staffs": "unknown", "systems": "unknown", "clefs": "unknown"},
        "staffs": staffs,
        "systems": systems,
        "clefs": clefs,
    }


def _selected_images(args) -> tuple[list[str], dict]:
    prelim = {}
    if args.manifest is not None:
        prelim = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(prelim, dict) or any(
            not isinstance(name, str)
            or Path(name).name != name
            or type(count) is not int
            or count < 0
            for name, count in prelim.items()
        ):
            raise AnnotationError("manifesto preliminar inválido")
    if args.image:
        names = args.image
    elif args.manifest is not None:
        names = list(prelim)
    else:
        names = [
            path.name
            for path in sorted(args.images_dir.iterdir())
            if path.suffix.lower() in {".png", ".jpg", ".jpeg"}
        ]
    if not names or len(set(names)) != len(names):
        raise AnnotationError("selecione imagens existentes e sem duplicatas")
    if any(
        Path(name).name != name or not name.lower().endswith((".png", ".jpg", ".jpeg"))
        for name in names
    ):
        raise AnnotationError("--image deve conter apenas nomes PNG/JPEG")
    return names, prelim


def suggest(args) -> int:
    names, prelim = _selected_images(args)
    missing = [name for name in names if not (args.images_dir / name).is_file()]
    if missing:
        raise FileNotFoundError("imagens ausentes: " + ", ".join(missing))
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for name in names:
        path = args.images_dir / name
        image = load_image(path)
        detection, grouping, clefs, predicted = _predictions(image)
        image_info = {
            "id": name,
            "filename": name,
            "sha256": image_sha256(path),
            "width": image.width,
            "height": image.height,
        }
        proposal = {
            "schema_version": SCHEMA_VERSION,
            "kind": "suggestions_not_ground_truth",
            "image": image_info,
            "preliminary_staff_count": prelim.get(name),
            "detections": predicted,
            "review_required": [
                "confirmar todas as pautas, regiões e linhas",
                "corrigir ordem e pertencimento aos sistemas",
                "classificar cada clave como presente, ausente ou desconhecida",
                "marcar cobertura e separação development/test",
            ],
        }
        draft = _draft(image_info, predicted)
        validate_reference(draft)
        _write_json(args.output_dir / f"{name}.suggestions.json", proposal)
        _write_json(args.output_dir / f"{name}.reference-draft.json", draft)
        _review_image(image, detection, grouping, clefs).save(
            args.output_dir / f"{name}.review.png"
        )
        clef_count = sum(item.status == "detected" for item in clefs.observations)
        print(
            f"{name}: sugestões não validadas; pautas={detection.staff_count} "
            f"sistemas={len(grouping.systems)} ({grouping.status}) "
            f"claves_sol={clef_count} "
            f"contagem_preliminar={prelim.get(name, 'unknown')}"
        )
    return 0


def check(args) -> int:
    reference = load_reference(args.annotation)
    verify_image(reference, args.images_dir)
    print(
        f"{args.annotation.name}: formato válido, imagem íntegra, "
        f"status={reference['review']['status']}"
    )
    return 0


def confirm(args) -> int:
    if not args.confirm_reviewed:
        raise AnnotationError("use --confirm-reviewed após revisar manualmente")
    reference = load_reference(args.annotation)
    if reference["review"]["status"] != "draft":
        raise AnnotationError("somente rascunhos podem ser confirmados")
    verify_image(reference, args.images_dir)
    if not any(
        staff["review_state"] == "confirmed" for staff in reference["staffs"]
    ) and not (
        reference["coverage"]["staffs"] == "complete" and not reference["staffs"]
    ):
        raise AnnotationError("revise ao menos uma pauta ou confirme página sem pautas")
    reference["review"] = {"status": "validated", "confirmed_by": args.reviewer}
    validate_reference(reference, require_validated=True)
    _write_json(args.output, reference)
    print(f"{args.output.name}: referência validada por {args.reviewer}")
    return 0


def _error_image(image, reference: dict, predicted: dict, report: dict):
    output = image.copy()
    draw = ImageDraw.Draw(output)
    matched_refs = {item["reference_id"] for item in report["matching"]["pairs"]}
    matched_preds = {item["prediction_index"] for item in report["matching"]["pairs"]}
    for staff in reference["staffs"]:
        box = staff["region"]
        if box is None:
            continue
        color = "cyan" if staff["id"] in matched_refs else "magenta"
        draw.rectangle(
            (box["left"], box["top"], box["right"], box["bottom"]),
            outline=color,
            width=2,
        )
        draw.text(
            (box["left"], max(0, round(box["top"]) - 10)), staff["id"], fill=color
        )
    for index, staff in enumerate(predicted["staffs"]):
        box = staff["region"]
        color = "green" if index in matched_preds else "red"
        draw.rectangle(
            (box["left"], box["top"], box["right"], box["bottom"]), outline=color
        )
        draw.text(
            (box["left"] + 12, max(0, round(box["top"]) - 10)), f"p{index}", fill=color
        )
    for system in reference["systems"]:
        if not system["staff_ids"]:
            continue
        members = [
            staff
            for staff in reference["staffs"]
            if staff["id"] in system["staff_ids"] and staff["region"] is not None
        ]
        if members:
            draw.text(
                (
                    min(s["region"]["left"] for s in members),
                    max(0, round(min(s["region"]["top"] for s in members)) - 20),
                ),
                system["id"],
                fill="purple",
            )
    for clef in reference["clefs"]:
        box = clef["region"]
        if box is not None:
            draw.rectangle(
                (box["left"], box["top"], box["right"], box["bottom"]),
                outline="yellow",
                width=2,
            )
    return output


def evaluate(args) -> int:
    if args.annotation is None and not args.annotations_dir.is_dir():
        raise FileNotFoundError(
            f"diretório de anotações ausente: {args.annotations_dir}"
        )
    paths = (
        [args.annotation]
        if args.annotation
        else sorted(args.annotations_dir.glob("*.reference.json"))
    )
    if args.report is not None and args.report.exists():
        raise FileExistsError(f"relatório já existe: {args.report}")
    if args.errors_dir is not None:
        args.errors_dir.mkdir(parents=True, exist_ok=False)
    reports = []
    seen_hashes = set()
    for path in paths:
        reference = load_reference(path, require_validated=True)
        sha = reference["image"]["sha256"]
        if sha in seen_hashes:
            raise AnnotationError(f"imagem repetida em referências: {path.name}")
        seen_hashes.add(sha)
        image_path = verify_image(reference, args.images_dir)
        image = load_image(image_path)
        _, _, _, predicted = _predictions(image)
        report = evaluate_page(reference, predicted)
        reports.append(report)
        print(
            f"{image_path.name}: pautas={report['staffs']['status']} "
            f"sistemas={report['systems']['status']} "
            f"claves={report['clefs']['status']}"
        )
        if args.errors_dir is not None:
            _error_image(image, reference, predicted, report).save(
                args.errors_dir / f"{image_path.name}.errors.png"
            )
    result = {
        "status": "evaluated" if reports else NOT_EVALUABLE,
        "references_evaluated": len(reports),
        "images": reports,
        "aggregate": aggregate_reports(reports),
        "by_split": {
            split: aggregate_reports(
                [report for report in reports if report["split"] == split]
            )
            for split in ("development", "test")
        },
    }
    if args.report is not None:
        _write_json(args.report, result)
    print(json.dumps(result["aggregate"], ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    suggestions = commands.add_parser("suggest", help="Gerar propostas não validadas")
    suggestions.add_argument("--images-dir", type=Path, required=True)
    suggestions.add_argument("--output-dir", type=Path, required=True)
    suggestions.add_argument("--image", action="append")
    suggestions.add_argument("--manifest", type=Path, help="Contagens preliminares")
    validation = commands.add_parser("check", help="Validar JSON e imagem")
    validation.add_argument("--annotation", type=Path, required=True)
    validation.add_argument("--images-dir", type=Path, required=True)
    promotion = commands.add_parser("confirm", help="Confirmar revisão humana")
    promotion.add_argument("--annotation", type=Path, required=True)
    promotion.add_argument("--images-dir", type=Path, required=True)
    promotion.add_argument("--output", type=Path, required=True)
    promotion.add_argument("--reviewer", required=True)
    promotion.add_argument("--confirm-reviewed", action="store_true")
    evaluation = commands.add_parser(
        "evaluate", help="Medir somente referências validadas"
    )
    evaluation.add_argument("--annotations-dir", type=Path)
    evaluation.add_argument("--annotation", type=Path)
    evaluation.add_argument("--images-dir", type=Path, required=True)
    evaluation.add_argument("--report", type=Path)
    evaluation.add_argument("--errors-dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "suggest":
            return suggest(args)
        if args.command == "check":
            return check(args)
        if args.command == "confirm":
            return confirm(args)
        if args.annotation is None and args.annotations_dir is None:
            raise AnnotationError("informe --annotation ou --annotations-dir")
        return evaluate(args)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    except (AnnotationError, FileExistsError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        print(f"ERROR: processamento falhou: {exc}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
