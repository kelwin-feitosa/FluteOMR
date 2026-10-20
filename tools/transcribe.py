"""CLI experimental separada para não alterar `python -m fluteomr`."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from PIL import ImageDraw

from fluteomr.image_io import load_image
from fluteomr.music import Instrument
from fluteomr.musicxml import to_musicxml
from fluteomr.staff_detection import detect_staffs
from fluteomr.transcription import transcribe_measures, transcribe_one_measure


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Transcrição experimental de uma pauta em 4/4"
    )
    parser.add_argument("image", type=Path, help="PNG de uma pauta horizontal")
    parser.add_argument(
        "--clef",
        choices=("treble",),
        required=True,
        help="Clave fornecida pelo usuário; não reconhecida nesta CLI",
    )
    parser.add_argument(
        "--time",
        choices=("4/4",),
        required=True,
        help="Fórmula fornecida pelo usuário; não reconhecida",
    )
    parser.add_argument(
        "--measure-left", type=int, required=True, help="limite esquerdo configurado"
    )
    parser.add_argument(
        "--measure-right", type=int, required=True, help="limite direito configurado"
    )
    parser.add_argument(
        "--auto-bars",
        action="store_true",
        help="inferir barras internas e múltiplos compassos",
    )
    parser.add_argument("--debug", type=Path, help="PNG de diagnóstico, novo arquivo")
    parser.add_argument("--output", type=Path, required=True, help="MusicXML novo")
    parser.add_argument("--part-name", help="Nome fornecido pelo usuário")
    parser.add_argument(
        "--instrument",
        choices=("flute",),
        help="Instrumento configurado pelo usuário, nunca inferido da imagem",
    )
    parser.add_argument(
        "--native-heads",
        action="store_true",
        help="desativar normalização local de cabeças pequenas para comparação",
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("a saída já existe; escolha um arquivo novo")
    if args.debug and not args.auto_bars:
        parser.error("--debug requer --auto-bars")
    if args.debug and args.debug.exists():
        parser.error("a imagem de depuração já existe")
    try:
        image = load_image(args.image)
        analysis = (
            transcribe_measures(
                image,
                content_left=args.measure_left,
                content_right=args.measure_right,
                part_name=args.part_name,
                instrument=Instrument.flute() if args.instrument else None,
                normalize_heads=not args.native_heads,
            )
            if args.auto_bars
            else None
        )
        score = (
            analysis.score
            if analysis
            else transcribe_one_measure(
                image,
                measure_left=args.measure_left,
                measure_right=args.measure_right,
                part_name=args.part_name,
                instrument=Instrument.flute() if args.instrument else None,
                normalize_heads=not args.native_heads,
            )
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    report = score.to_dict()
    if analysis:
        report["symbol_diagnostics"] = {
            "barlines": [asdict(bar) for bar in analysis.barlines],
            "stems": [asdict(stem) for stem in analysis.stems],
            "rhythm_evidence": [asdict(mark) for mark in analysis.rhythm_evidence],
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.debug and analysis:
        overlay = image.convert("RGB")
        draw = ImageDraw.Draw(overlay)
        staff = detect_staffs(image).staffs[0]
        for line in staff.lines:
            draw.line((line.x_start, line.y, line.x_end, line.y), fill="blue", width=1)
        for head in analysis.heads:
            box = head.region
            draw.rectangle(
                (box.left, box.top, box.right, box.bottom),
                outline="green" if head.stem_present else "orange",
                width=2,
            )
        for bar in analysis.barlines:
            draw.line(
                (bar.x, bar.region.top, bar.x, bar.region.bottom),
                fill="purple" if bar.status == "accepted" else "red",
                width=2,
            )
        args.debug.parent.mkdir(parents=True, exist_ok=True)
        overlay.save(args.debug)
    if score.issues():
        parser.exit(2, "Transcrição incompleta: MusicXML não gerado.\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open("xb") as stream:
            stream.write(to_musicxml(score))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
