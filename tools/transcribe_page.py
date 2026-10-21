"""CLI experimental para uma página solo; JSON parcial sempre preservado."""

import argparse
import hashlib
import json
from pathlib import Path

from fluteomr.document import transcribe_page
from fluteomr.image_io import load_image
from fluteomr.music import Instrument
from fluteomr.musicxml import to_musicxml


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--layout", choices=["solo"], required=True)
    parser.add_argument("--clef", choices=["treble"], required=True, help="configurada")
    parser.add_argument("--time", choices=["4/4"], required=True, help="configurado")
    parser.add_argument("--page-number", type=int, default=1)
    parser.add_argument("--instrument", choices=["flute"])
    parser.add_argument(
        "--allow-clefless",
        action="store_true",
        help="somente para pautas sem clave impressa; assume clave de sol",
    )
    parser.add_argument(
        "--leading-spaces",
        type=float,
        default=0,
        help="margem extra após clave, em espaços da pauta",
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, help="MusicXML novo, somente se nenhuma pauta falhar"
    )
    args = parser.parse_args()
    if args.report.exists() or (args.output and args.output.exists()):
        parser.error("saída já existe; escolha arquivos novos")
    if args.output and args.output.resolve() == args.report.resolve():
        parser.error("JSON e MusicXML exigem caminhos distintos")
    try:
        result = transcribe_page(
            load_image(args.image),
            layout=args.layout,
            page_number=args.page_number,
            allow_clefless=args.allow_clefless,
            leading_spaces=args.leading_spaces,
            instrument=Instrument.flute() if args.instrument else None,
        )
        report = result.to_dict()
        report["source"] = {
            "image": args.image.name,
            "sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
        }
        xml = None
        try:
            xml = to_musicxml(result.score)
            report["xml_export"] = "well_formed_not_schema_validated"
        except ValueError as exc:
            report["xml_export"] = "blocked_by_prediction_issues"
            report["export_error"] = str(exc)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        if xml is not None and args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("xb") as stream:
                stream.write(xml)
        print(
            json.dumps(
                {
                    "staffs": len(result.staff_results),
                    "events": sum(len(m.notes) for m in result.score.parts[0].measures),
                    "issues": result.score.issues(),
                    "xml_export": report["xml_export"],
                },
                ensure_ascii=False,
            )
        )
        if xml is None:
            raise SystemExit(1)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
