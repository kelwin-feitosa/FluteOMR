"""Converte MusicXML conhecido com MuseScore como ferramenta opcional de teste.

Nunca usa o MuseScore como motor OMR. As gravuras resultantes são dados
controlados `source_authored`, não ground truth independente de partituras.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

FORMATS = frozenset({"pdf", "png", "svg", "mpos", "spos"})
MAX_SCORE_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_BYTES = 64 * 1024 * 1024


class MuseScoreRenderError(ValueError):
    """Conversão indisponível, incompleta ou potencialmente ambígua."""


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _binary_path(value: str | Path | None) -> Path:
    if value is None:
        for name in ("musescore4", "musescore", "musescore3", "mscore"):
            found = shutil.which(name)
            if found is not None:
                value = found
                break
    if value is None:
        raise MuseScoreRenderError(
            "MuseScore não encontrado: instale separadamente ou use --binary"
        )
    path = Path(value).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise MuseScoreRenderError("executável MuseScore ausente ou sem permissão")
    return path


def render_fixture(
    source: Path,
    destination: Path,
    *,
    formats: tuple[str, ...] = ("pdf", "png", "mpos", "spos"),
    dpi: int = 200,
    binary: str | Path | None = None,
    timeout: int = 120,
) -> dict:
    """Produz arquivos e manifesto em diretório NOVO, sem sobrescrever.

    A entrada deve ser MusicXML de origem independente do FluteOMR, mas não
    se presume revisão humana. A saída depende da versão MuseScore instalada.
    """
    source = source.expanduser().resolve()
    destination = destination.expanduser().resolve()
    if source.suffix.lower() not in {".musicxml", ".xml", ".mxl"}:
        raise MuseScoreRenderError("a entrada precisa ser MusicXML ou MXL")
    if not source.is_file() or not 0 < source.stat().st_size <= MAX_SCORE_BYTES:
        raise MuseScoreRenderError("MusicXML ausente, vazio ou acima de 32 MiB")
    if not isinstance(dpi, int) or isinstance(dpi, bool) or not 72 <= dpi <= 400:
        raise MuseScoreRenderError("DPI precisa ser inteiro de 72 a 400")
    if (
        not isinstance(timeout, int)
        or isinstance(timeout, bool)
        or not 1 <= timeout <= 600
    ):
        raise MuseScoreRenderError("timeout inválido")
    if not formats or len(set(formats)) != len(formats) or not set(formats) <= FORMATS:
        raise MuseScoreRenderError("formatos inválidos ou repetidos")
    if destination.exists() or destination == source.parent:
        raise FileExistsError("diretório de saída já existe; não sobrescrever")
    executable = _binary_path(binary)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory(
            prefix=".musescore-fixture-", dir=destination.parent
        ) as temporary,
        tempfile.TemporaryDirectory(
            prefix=".musescore-profile-", dir=destination.parent
        ) as profile,
    ):
        staging = Path(temporary)
        # Isolar o perfil do SO E evitar que arquivos temporários de
        # configuração sejam publicados junto com as gravuras finais.
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["MU_QT_QPA_PLATFORM"] = "offscreen"
        env["XDG_CONFIG_HOME"] = str(Path(profile) / "config")
        env["XDG_DATA_HOME"] = str(Path(profile) / "data")
        try:
            version = subprocess.run(
                [str(executable), "--version"],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise MuseScoreRenderError("timeout ao consultar MuseScore") from exc
        if version.returncode:
            raise MuseScoreRenderError("não foi possível verificar a versão")
        outputs = []
        for format_name in formats:
            target = staging / f"score.{format_name}"
            try:
                process = subprocess.run(
                    [
                        str(executable),
                        "-r",
                        str(dpi),
                        "-o",
                        str(target),
                        str(source),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise MuseScoreRenderError(
                    f"timeout convertendo {format_name}"
                ) from exc
            if process.returncode:
                raise MuseScoreRenderError(
                    f"MuseScore retornou erro ao gerar {format_name}: "
                    f"{process.stderr[-500:]}"
                )
            files = sorted(
                f
                for f in staging.iterdir()
                if f.is_file()
                and re.fullmatch(
                    rf"score(?:-[1-9][0-9]*)?\.{re.escape(format_name)}",
                    f.name,
                )
            )
            if not files:
                raise MuseScoreRenderError(
                    f"MuseScore não criou {format_name}; formato pode não ser suportado"
                )
            if any(not 0 < f.stat().st_size <= MAX_OUTPUT_BYTES for f in files):
                raise MuseScoreRenderError("saída vazia ou maior que 64 MiB")
            generated = []
            for f in files:
                info = {
                    "name": f.name,
                    "bytes": f.stat().st_size,
                    "sha256": _sha256(f),
                }
                if format_name in ("mpos", "spos"):
                    try:
                        root = ET.parse(f).getroot()
                    except ET.ParseError as exc:
                        raise MuseScoreRenderError("XML de posições inválido") from exc
                    info["root_tag"] = root.tag
                    info["position_elements"] = len(root.findall(".//element"))
                generated.append(info)
            outputs.append({"format": format_name, "files": generated})
        manifest = {
            "format_version": 1,
            "provenance": "source_authored_engraved_by_musescore",
            "independent_printed_score": False,
            "human_ground_truth_reviewed": False,
            "input": {"filename": source.name, "sha256": _sha256(source)},
            "musescore": {
                "binary_name": executable.name,
                "version": (version.stdout or version.stderr).strip()[:250],
            },
            "dpi_requested": dpi,
            "outputs": outputs,
            "position_caveat": (
                "mpos/spos registram coordenadas em unidades dependentes da "
                "versão/exportação; NÃO são necessariamente pixels PNG e "
                "não identificam individualmente cada nota."
            ),
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        # staging fica no mesmo filesystem da saída.
        if destination.exists():
            raise FileExistsError("outro processo criou a pasta de saída")
        staging.rename(destination)
        return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("musicxml", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--format", action="append", choices=sorted(FORMATS))
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--binary")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    try:
        result = render_fixture(
            args.musicxml,
            args.out_dir,
            formats=tuple(args.format)
            if args.format
            else ("pdf", "png", "mpos", "spos"),
            dpi=args.dpi,
            binary=args.binary,
            timeout=args.timeout,
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
