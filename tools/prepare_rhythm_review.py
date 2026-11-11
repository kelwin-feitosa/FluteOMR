"""Cria pacote auditável para revisão humana de ritmos inconclusivos.

Lê PDF público já adquirido e consulta o OMR próprio. NÃO usa inferência
externa, não exporta MusicXML final e não atribui revisão humana.
"""

import argparse
import csv
import hashlib
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from PIL import ImageDraw

from fluteomr.document import transcribe_page
from fluteomr.music import Instrument
from fluteomr.pdf_io import load_pdf_page

REASONS = (
    "secondary_stripe_ambiguous",
    "weak_secondary_stripe",
    "stem_not_confirmed",
)
MAX_PDF_BYTES = 20 * 1024 * 1024


def _diverse_staff_sample(candidates: list[dict], count: int) -> list[dict]:
    """Amostra por pauta, sem usar notas verdadeiras nem números de compasso."""
    groups: dict[int, list[dict]] = defaultdict(list)
    for case in candidates:
        groups[case["staff_index"]].append(case)
    picked = []
    while groups and len(picked) < count:
        for staff_index in sorted(tuple(groups)):
            if len(picked) >= count:
                break
            group = groups[staff_index]
            picked.append(group.pop(0))
            if not group:
                del groups[staff_index]
    return picked


def build_review_packet(
    source: Path,
    destination: Path,
    *,
    page: int = 1,
    dpi: int = 200,
    max_cases: int = 12,
) -> dict:
    """Escreve PNGs + JSON/CSV em diretório novo; sem sobrescrever resultados."""
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if source.suffix.lower() != ".pdf" or not source.is_file():
        raise ValueError("fonte PDF local obrigatória")
    if not 0 < source.stat().st_size <= MAX_PDF_BYTES:
        raise ValueError("arquivo PDF vazio ou maior que 20 MiB")
    if type(page) is not int or not 1 <= page <= 100:
        raise ValueError("página inválida")
    if type(dpi) is not int or not 100 <= dpi <= 400:
        raise ValueError("DPI deve estar entre 100 e 400")
    if type(max_cases) is not int or not 1 <= max_cases <= 48:
        raise ValueError("max_cases deve estar entre 1 e 48")
    if destination.exists():
        raise FileExistsError("pasta de revisão já existe")
    image = load_pdf_page(source, page_number=page, dpi=dpi).convert("RGB")
    result = transcribe_page(
        image, layout="solo", page_number=page, instrument=Instrument.flute()
    )
    cases = []
    for part in result.score.parts:
        for measure in part.measures:
            for note in measure.notes:
                match = next(
                    (reason for reason in REASONS if reason in note.diagnostics),
                    None,
                )
                if match is None:
                    continue
                cases.append(
                    {
                        "reason": match,
                        "staff_index": note.staff_index,
                        "measure_index_provisional": measure.number,
                        "candidate_id": note.candidate_id,
                        "head_bounds": {
                            "left": note.source_region.left,
                            "top": note.source_region.top,
                            "right": note.source_region.right,
                            "bottom": note.source_region.bottom,
                        },
                        "proposed_pitch": (
                            {
                                "step": note.pitch.step,
                                "octave": note.pitch.octave,
                            }
                            if note.pitch is not None
                            else None
                        ),
                        "proposed_duration": (
                            note.duration.kind if note.duration is not None else None
                        ),
                        "diagnostics": list(note.diagnostics),
                    }
                )
    counts = Counter(case["reason"] for case in cases)
    # Prioriza os mais ambíguos, mas preserva amostras das outras classes.
    order = (
        (REASONS[0], max_cases // 2),
        (REASONS[1], max(1, max_cases // 4)),
        (REASONS[2], max(1, max_cases // 4)),
    )
    chosen = []
    for reason, quota in order:
        chosen.extend(
            _diverse_staff_sample(
                [case for case in cases if case["reason"] == reason], quota
            )
        )
    seen = {case["candidate_id"] for case in chosen}
    if len(chosen) < max_cases:
        chosen.extend(
            _diverse_staff_sample(
                [case for case in cases if case["candidate_id"] not in seen],
                max_cases - len(chosen),
            )
        )
    chosen = chosen[:max_cases]
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".rhythm-review-", dir=destination.parent
    ) as temp:
        staging = Path(temp)
        items = []
        for index, case in enumerate(chosen, 1):
            h = case["head_bounds"]
            center_x = (h["left"] + h["right"]) // 2
            center_y = (h["top"] + h["bottom"]) // 2
            xpad, ypad = round(dpi * 0.65), round(dpi * 0.35)
            left = max(0, center_x - xpad)
            top = max(0, center_y - ypad)
            right = min(image.width, center_x + xpad)
            bottom = min(image.height, center_y + ypad)
            if left >= right or top >= bottom:
                raise ValueError("coordenadas de nota fora da imagem")
            patch = image.crop((left, top, right, bottom))
            draw = ImageDraw.Draw(patch)
            rect = (
                h["left"] - left - 3,
                h["top"] - top - 3,
                h["right"] - left + 3,
                h["bottom"] - top + 3,
            )
            draw.rectangle(rect, outline="#d02020", width=2)
            filename = f"case-{index:02d}.png"
            patch.save(staging / filename)
            items.append(
                {
                    "review_id": f"BWV1013-p{page}-case{index:02d}",
                    **case,
                    "crop_file": filename,
                    "crop_bounds": [left, top, right, bottom],
                    "human_review_status": "unreviewed",
                    "ground_truth": None,
                }
            )
        with (staging / "review-template.csv").open(
            "x", encoding="utf-8", newline=""
        ) as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(
                [
                    "review_id",
                    "crop_file",
                    "status",
                    "correct_pitch",
                    "correct_duration",
                    "correct_beam_levels",
                    "comment",
                ]
            )
            for item in items:
                writer.writerow(
                    [item["review_id"], item["crop_file"], "unreviewed", "", "", "", ""]
                )
        with source.open("rb") as stream:
            source_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        manifest = {
            "format_version": 1,
            "source_pdf": source.name,
            "source_sha256": source_hash,
            "page": page,
            "dpi": dpi,
            "coordinate_frame": "rasterized_original_page",
            "total_proposed_events": sum(
                len(measure.notes)
                for part in result.score.parts
                for measure in part.measures
            ),
            "unresolved_diagnostics": dict(sorted(counts.items())),
            "case_count": len(items),
            "cases": items,
            "status": "review_packet_unreviewed",
            "reference_quality": "none",
            "warning": (
                "Regiões mostram predições e incertezas do FluteOMR. "
                "Os números de compasso são provisórios; nenhuma "
                "nota foi validada por músico. Não calcular accuracy."
            ),
        }
        (staging / "review-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if destination.exists():
            raise FileExistsError("destino criado por outro processo")
        staging.rename(destination)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--max-cases", type=int, default=12)
    args = parser.parse_args()
    try:
        result = build_review_packet(
            args.pdf,
            args.out_dir,
            page=args.page,
            dpi=args.dpi,
            max_cases=args.max_cases,
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")
    print(
        json.dumps(
            {
                key: value for key, value in result.items() if key != "cases"
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
