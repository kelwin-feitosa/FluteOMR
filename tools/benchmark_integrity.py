"""Verificação de integridade dos conjuntos de avaliação musical.

Não acessa imagens ou referências: analisa apenas metadados de manifestos.
Variantes da mesma obra podem coexistir dentro de um split, mas não entre
development, validation e test. Para isso, registre o mesmo work_id em todas
as renderizações de uma obra (fonte, DPI, recorte ou transposição).
"""

import argparse
import json
import re
from collections.abc import Sequence
from pathlib import Path

SPLITS = frozenset({"development", "validation", "test"})


class BenchmarkIntegrityError(ValueError):
    """Metadados de benchmark inconsistentes ou não reprodutíveis."""


def validate_examples(
    examples: object,
    *,
    source: str,
    seen_ids: dict[str, str] | None = None,
    seen_work_splits: dict[str, tuple[str, str]] | None = None,
    seen_image_hashes: dict[str, tuple[str, str, str]] | None = None,
    require_explicit_work_id: bool = False,
) -> None:
    """Valida exemplos sem ler material reservado ou executar predições.

    Os mapas opcionais permitem comparar vários manifestos simultaneamente.
    Um work_id ausente usa o id legado, sem garantir proteção contra variantes;
    use require_explicit_work_id=True para corpora destinados a benchmarks finais.
    """
    if not isinstance(examples, list):
        raise BenchmarkIntegrityError(f"{source}: examples deve ser uma lista")
    if seen_ids is None:
        seen_ids = {}
    if seen_work_splits is None:
        seen_work_splits = {}
    if seen_image_hashes is None:
        seen_image_hashes = {}
    for index, example in enumerate(examples):
        where = f"{source}: examples[{index}]"
        if not isinstance(example, dict):
            raise BenchmarkIntegrityError(f"{where}: exemplo deve ser um objeto")
        identifier = example.get("id")
        split = example.get("split")
        if not isinstance(identifier, str) or not identifier.strip():
            raise BenchmarkIntegrityError(f"{where}: id ausente ou inválido")
        if not isinstance(split, str) or split not in SPLITS:
            raise BenchmarkIntegrityError(f"{where}: split inválido: {split!r}")
        if require_explicit_work_id and "work_id" not in example:
            raise BenchmarkIntegrityError(
                f"{where}: work_id explícito é obrigatório neste benchmark"
            )
        work_id = example.get("work_id", identifier)
        if not isinstance(work_id, str) or not work_id.strip():
            raise BenchmarkIntegrityError(f"{where}: work_id inválido")
        if identifier in seen_ids:
            raise BenchmarkIntegrityError(
                f"{where}: id duplicado {identifier!r}; já usado em "
                f"{seen_ids[identifier]}"
            )
        seen_ids[identifier] = where
        existing = seen_work_splits.get(work_id)
        if existing is not None and existing[0] != split:
            raise BenchmarkIntegrityError(
                f"{where}: vazamento entre splits para work_id={work_id!r}: "
                f"{existing[0]} ({existing[1]}) e {split}"
            )
        seen_work_splits.setdefault(work_id, (split, where))
        # Este campo é opcional em manifestos legados. Quando existe, ajuda a
        # detectar imagens byte-idênticas com ids/work_ids incorretos; não
        # substitui a revisão humana nem reabre imagens de test/validation.
        image_hash = example.get("image_sha256")
        if image_hash is not None:
            if not isinstance(image_hash, str) or not re.fullmatch(
                r"[a-fA-F0-9]{64}", image_hash
            ):
                raise BenchmarkIntegrityError(
                    f"{where}: image_sha256 deve ter 64 caracteres hexadecimais"
                )
            image_hash = image_hash.lower()
            previous = seen_image_hashes.get(image_hash)
            if previous is not None:
                previous_split, previous_work, previous_where = previous
                if previous_split != split:
                    raise BenchmarkIntegrityError(
                        f"{where}: vazamento de imagem entre splits; "
                        f"hash também usado em {previous_where}"
                    )
                if previous_work != work_id:
                    raise BenchmarkIntegrityError(
                        f"{where}: mesma imagem atribuída a obras distintas; "
                        f"hash também usado em {previous_where}"
                    )
            seen_image_hashes.setdefault(image_hash, (split, work_id, where))


def validate_manifests(
    paths: Sequence[Path], *, require_explicit_work_id: bool = False
) -> dict:
    """Confere separação por obra entre manifestos e retorna contagens."""
    if not paths:
        raise BenchmarkIntegrityError("forneça pelo menos um manifesto")
    seen_ids: dict[str, str] = {}
    seen_work_splits: dict[str, tuple[str, str]] = {}
    seen_image_hashes: dict[str, tuple[str, str, str]] = {}
    hash_entries = 0
    counts = {name: {"examples": 0, "works": 0} for name in sorted(SPLITS)}
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(data, dict)
            or type(data.get("format_version")) is not int
            or data["format_version"] != 1
        ):
            raise BenchmarkIntegrityError(f"{path}: format_version incompatível")
        validate_examples(
            data.get("examples"),
            source=str(path),
            seen_ids=seen_ids,
            seen_work_splits=seen_work_splits,
            seen_image_hashes=seen_image_hashes,
            require_explicit_work_id=require_explicit_work_id,
        )
        # As contagens de obras usam o registro global, não contam variantes.
        counts_by_split = {
            split: sum(assigned == split for assigned, _ in seen_work_splits.values())
            for split in SPLITS
        }
        for split in SPLITS:
            counts[split]["works"] = counts_by_split[split]
        for example in data["examples"]:
            counts[example["split"]]["examples"] += 1
            hash_entries += example.get("image_sha256") is not None
    return {
        "manifest_count": len(paths),
        "example_count": len(seen_ids),
        "work_count": len(seen_work_splits),
        "image_hash_entries": hash_entries,
        "image_hash_coverage": {
            "provided": hash_entries,
            "total": len(seen_ids),
        },
        "by_split": counts,
        "status": "metadata_consistent",
        "caveat": (
            "A separação depende de work_id identificar todas as variantes "
            "da mesma obra."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument(
        "--require-work-id",
        action="store_true",
        help="Exigir work_id explícito (para avaliação final)",
    )
    args = parser.parse_args()
    try:
        result = validate_manifests(
            args.manifests, require_explicit_work_id=args.require_work_id
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
