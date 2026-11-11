"""Avalia um corpus com proteção de splits entre *todos* os manifestos.

A pré-validação ocorre antes de abrir qualquer imagem ou referência. O conjunto
reservado 'test' nunca é executado por padrão.
"""

import argparse
import json
from pathlib import Path

from tools.benchmark_integrity import SPLITS, validate_manifests
from tools.evaluate_music import evaluate_manifest, summarize_results


def evaluate_corpus(
    manifests: list[Path],
    *,
    images_dir: Path | None = None,
    splits: set[str] | None = None,
    continue_on_error: bool = True,
    require_explicit_work_id: bool = True,
) -> dict:
    """Executa cada manifesto somente após verificação global por obra.

    A separação por `work_id` valida metadados, não certifica que o MusicXML
    foi anotado por humanos. `test` deve ser habilitado explicitamente.
    """
    selected = {"development"} if splits is None else set(splits)
    if not selected or not selected.issubset(SPLITS):
        raise ValueError("selecione ao menos um split válido")
    integrity = validate_manifests(
        manifests, require_explicit_work_id=require_explicit_work_id
    )
    rows = []
    for manifest in manifests:
        subset = evaluate_manifest(
            manifest,
            images_dir if images_dir is not None else manifest.parent,
            continue_on_error=continue_on_error,
            splits=selected,
        )
        for row in subset:
            rows.append({"manifest": str(manifest), **row})
    if not rows:
        raise ValueError("nenhum exemplo pertence aos splits selecionados")
    return {
        "format_version": 1,
        "selected_splits": sorted(selected),
        "integrity": integrity,
        "images": rows,
        "summary": summarize_results(rows),
        "by_split": {
            split: summarize_results([row for row in rows if row["split"] == split])
            for split in sorted(selected)
        },
        "ground_truth_caveat": (
            "Validação de manifestos não certifica independência das anotações; "
            "source_authored não é referência humana."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, action="append", required=True,
        help="repita para validar todos os manifestos antes de avaliar",
    )
    parser.add_argument(
        "--images-dir", type=Path,
        help="diretório comum das imagens; padrão: diretório de cada manifesto",
    )
    parser.add_argument(
        "--split", action="append", choices=sorted(SPLITS),
        help="padrão: development; test exige seleção explícita",
    )
    parser.add_argument("--report", type=Path, help="arquivo JSON novo")
    parser.add_argument(
        "--stop-on-error", action="store_true",
        help="não prosseguir se uma imagem falhar",
    )
    parser.add_argument(
        "--allow-legacy-work-id", action="store_true",
        help="desativa exigência de work_id explícito; reduz proteção",
    )
    args = parser.parse_args()
    if args.report is not None and args.report.exists():
        parser.error("relatório já existe; não sobrescrever")
    try:
        result = evaluate_corpus(
            args.manifest,
            images_dir=args.images_dir,
            splits=set(args.split) if args.split else None,
            continue_on_error=not args.stop_on_error,
            require_explicit_work_id=not args.allow_legacy_work_id,
        )
        encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open("x", encoding="utf-8") as stream:
                stream.write(encoded)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(encoded, end="")
    if result["summary"]["processing_failures"]:
        parser.exit(1, "Corpus avaliado com falhas de processamento.\n")


if __name__ == "__main__":
    main()
