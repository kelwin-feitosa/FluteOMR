"""Compara cobertura de dois perfis de ritmo sem atribuir acurácia musical.

Ambos os relatórios devem vir da mesma página de partitura publicada.
Não substitui ground truth independente nem revisão humana.
"""

import argparse
import json
import re
from pathlib import Path


def _count(report: dict, name: str) -> int:
    value = report.get(name)
    if type(value) is not int or value < 0:
        raise ValueError(f"contagem ausente ou inválida: {name}")
    return value


def compare_probe_reports(baseline: dict, adaptive: dict) -> dict:
    """Compara cobertura apenas após conferir condições e proveniência."""
    if not isinstance(baseline, dict) or not isinstance(adaptive, dict):
        raise ValueError("relatórios precisam ser objetos JSON")
    for label, report, enabled in (
        ("baseline", baseline, False),
        ("adaptativo", adaptive, True),
    ):
        if report.get("status") != "diagnostic_only":
            raise ValueError(f"{label}: transcrição não foi concluída")
        if report.get("format_version") != 2:
            raise ValueError(f"{label}: formato da sonda sem proveniência completa")
        if report.get("experimental_adaptive_secondary") is not enabled:
            raise ValueError(f"{label}: modo de reconhecimento incorreto")
        if report.get("musical_accuracy") != "not_evaluated":
            raise ValueError(f"{label}: alegação de precisão não verificável")
        if report.get("xml_export") != "not_attempted":
            raise ValueError(f"{label}: exportação XML não pertence à sonda")
        events = _count(report, "predicted_events")
        resolved = _count(report, "resolved_duration_events")
        unresolved = _count(report, "unresolved_duration_events")
        if resolved + unresolved != events:
            raise ValueError(f"{label}: contagens inconsistentes")
        kinds = report.get("resolved_duration_kind_counts")
        if not isinstance(kinds, dict):
            raise ValueError(f"{label}: contagem por duração ausente")
        if any(
            not isinstance(name, str)
            or not name
            or type(number) is not int
            or number < 0
            for name, number in kinds.items()
        ):
            raise ValueError(f"{label}: contagem por duração inválida")
        if sum(kinds.values()) != resolved:
            raise ValueError(f"{label}: soma de tipos rítmicos incompatível")
        _count(report, "rejected_invalid_beam_group_count")
        _count(report, "predicted_double_beam_sixteenths")
        _count(report, "confirmed_mixed_beam_note_count")
        if not isinstance(report.get("unresolved_duration_diagnostic_counts"), dict):
            raise ValueError(f"{label}: diagnósticos ausentes")

    coordinates = (
        "source_pdf",
        "source_pdf_sha256",
        "page_image_sha256",
        "page_image_size",
        "page_number",
        "dpi",
    )
    if any(baseline.get(key) != adaptive.get(key) for key in coordinates):
        raise ValueError("relatórios não correspondem à mesma imagem e DPI")
    if not isinstance(baseline.get("source_pdf"), str) or not baseline["source_pdf"]:
        raise ValueError("identificação do PDF ausente")
    for key in ("source_pdf_sha256", "page_image_sha256"):
        value = baseline.get(key)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"proveniência SHA-256 obrigatória: {key}")
    size = baseline.get("page_image_size")
    if (
        not isinstance(size, list)
        or len(size) != 2
        or any(type(dimension) is not int or dimension <= 0 for dimension in size)
    ):
        raise ValueError("dimensões da imagem ausentes ou inválidas")
    for key in ("page_number", "dpi"):
        value = baseline.get(key)
        if type(value) is not int or value <= 0:
            raise ValueError(f"parâmetro inválido: {key}")

    metrics = (
        "predicted_events",
        "resolved_duration_events",
        "unresolved_duration_events",
        "predicted_double_beam_sixteenths",
        "rejected_invalid_beam_group_count",
        "confirmed_mixed_beam_note_count",
    )
    changes = {
        name: {
            "baseline": _count(baseline, name),
            "adaptive": _count(adaptive, name),
            "delta": _count(adaptive, name) - _count(baseline, name),
        }
        for name in metrics
    }
    original_kinds = baseline["resolved_duration_kind_counts"]
    adaptive_kinds = adaptive["resolved_duration_kind_counts"]
    kind_changes = {
        name: {
            "baseline": original_kinds.get(name, 0),
            "adaptive": adaptive_kinds.get(name, 0),
            "delta": adaptive_kinds.get(name, 0) - original_kinds.get(name, 0),
        }
        for name in sorted(set(original_kinds) | set(adaptive_kinds))
    }
    baseline_reasons = baseline["unresolved_duration_diagnostic_counts"]
    adaptive_reasons = adaptive["unresolved_duration_diagnostic_counts"]
    reasons = {}
    for name in sorted(set(baseline_reasons) | set(adaptive_reasons)):
        old = baseline_reasons.get(name, 0)
        new = adaptive_reasons.get(name, 0)
        if type(old) is not int or type(new) is not int or min(old, new) < 0:
            raise ValueError("contagem inválida em diagnósticos de incerteza")
        reasons[name] = {"baseline": old, "adaptive": new, "delta": new - old}

    return {
        "format_version": 2,
        "experiment": "adaptive_secondary_beam_profile",
        "source_pdf": baseline["source_pdf"],
        "source_pdf_sha256": baseline["source_pdf_sha256"],
        "page_image_sha256": baseline["page_image_sha256"],
        "page_image_size": baseline["page_image_size"],
        "page_number": baseline["page_number"],
        "dpi": baseline["dpi"],
        "coverage_comparison": changes,
        "resolved_duration_kind_comparison": kind_changes,
        "unresolved_diagnostic_comparison": reasons,
        "musical_accuracy": "not_evaluated",
        "human_reviewed": False,
        "xml_export": "not_attempted",
        "caveat": (
            "Mudanças na cobertura de durações são predições e podem incluir "
            "falsos positivos; não representam melhoria de acurácia."
        ),
    }


def compare_files(baseline: Path, adaptive: Path, output: Path) -> dict:
    """Rejeita sobrescrita e grava relatório comparativo verificável."""
    if output.exists():
        raise FileExistsError("relatório de comparação já existe")
    result = compare_probe_reports(
        json.loads(baseline.read_text(encoding="utf-8")),
        json.loads(adaptive.read_text(encoding="utf-8")),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("adaptive", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = compare_files(args.baseline, args.adaptive, args.report)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
