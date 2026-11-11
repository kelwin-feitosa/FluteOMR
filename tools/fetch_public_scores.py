"""Aquisição opcional e verificável de partituras públicas catalogadas.

Sem rede durante pytest ou CI de qualidade padrão. Download explícito somente
de URLs HTTPS permitidas no catálogo, sem contornar paywalls ou controles.
"""

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_PDF_BYTES = 20 * 1024 * 1024
TRUSTED_HOSTS = frozenset({"www.mutopiaproject.org", "mutopiaproject.org"})
_CHUNK = 64 * 1024


class CorpusSourceError(ValueError):
    """Fonte não permitida ou conteúdo inconsistente com o catálogo."""


def _approved_url(value: str) -> None:
    if not isinstance(value, str):
        raise CorpusSourceError("URL precisa ser string HTTPS")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in TRUSTED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
        or not parsed.path.lower().endswith(".pdf")
    ):
        raise CorpusSourceError("somente PDFs HTTPS de hosts aprovados são aceitos")


def load_catalog(path: Path) -> dict[str, dict]:
    """Valida identidade, direitos e URLs antes de qualquer acesso à rede."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if type(data) is not dict or data.get("format_version") != 1:
        raise CorpusSourceError("versão de catálogo incompatível")
    if not isinstance(data.get("sources"), list):
        raise CorpusSourceError("sources deve ser lista")
    entries = {}
    for item in data["sources"]:
        if not isinstance(item, dict):
            raise CorpusSourceError("item de catálogo inválido")
        key = item.get("id")
        if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", key):
            raise CorpusSourceError("id de obra inseguro")
        if key in entries:
            raise CorpusSourceError(f"id duplicado: {key}")
        if item.get("license") not in (
            "Public Domain dedication by typesetter (declared)",
            "Public Domain (Mutopia edition declaration)",
        ):
            raise CorpusSourceError("fonte sem declaração permitida de domínio público")
        if not isinstance(item.get("rights_evidence_url"), str) or not item[
            "rights_evidence_url"
        ].startswith("https://"):
            raise CorpusSourceError("evidência de direitos ausente")
        if not isinstance(item.get("work_id"), str) or not item["work_id"].strip():
            raise CorpusSourceError("work_id obrigatório")
        _approved_url(item.get("pdf_url"))
        digest = item.get("pdf_sha256")
        if digest is not None and (
            not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise CorpusSourceError("sha256 esperado inválido")
        entries[key] = item
    return entries


class _RestrictedRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _approved_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_approved(request: Request, *, timeout: int):
    return build_opener(_RestrictedRedirect()).open(request, timeout=timeout)


def download_score(
    entry: dict,
    destination: Path,
    *,
    opener=None,
) -> dict:
    """Baixa PDF sem sobrescrever saída e verifica hash quando declarado.

    O digest é registrado mesmo no primeiro download sem hash fixado, mas nesse
    caso NÃO constitui pin criptográfico contra troca futura da origem.
    """
    url = entry["pdf_url"]
    _approved_url(url)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", entry["id"]):
        raise CorpusSourceError("id inseguro")
    folder = destination / entry["id"]
    pdf_path = folder / "source.pdf"
    metadata_path = folder / "acquisition.json"
    if pdf_path.exists() or metadata_path.exists():
        raise FileExistsError("saída existente: não sobrescrever downloads anteriores")

    if opener is None:
        opener = _open_approved
    request = Request(
        url,
        headers={
            "User-Agent": "FluteOMR-corpus/1.0 (public-domain research)",
            "Accept": "application/pdf",
            "Accept-Encoding": "identity",
        },
    )
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with opener(request, timeout=30) as response:
            _approved_url(response.geturl())
            stated_length = response.headers.get("Content-Length")
            if stated_length and int(stated_length) > MAX_PDF_BYTES:
                raise CorpusSourceError("PDF ultrapassa limite por Content-Length")
            hasher = hashlib.sha256()
            total = 0
            prefix = b""
            tail = b""
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=folder, prefix=".incoming-", delete=False
            ) as out:
                temporary = Path(out.name)
                while True:
                    chunk = response.read(_CHUNK)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_PDF_BYTES:
                        raise CorpusSourceError("PDF ultrapassa limite de 20 MiB")
                    if len(prefix) < 1024:
                        prefix = (prefix + chunk)[:1024]
                    tail = (tail + chunk)[-2048:]
                    hasher.update(chunk)
                    out.write(chunk)
        if total < 16 or b"%PDF-" not in prefix or b"%%EOF" not in tail:
            raise CorpusSourceError("arquivo remoto não parece PDF completo")
        actual = hasher.hexdigest()
        expected = entry.get("pdf_sha256")
        if expected is not None and actual != expected:
            raise CorpusSourceError("hash do PDF não corresponde ao catálogo")
        metadata = {
            "format_version": 1,
            "id": entry["id"],
            "work_id": entry["work_id"],
            "source_url": url,
            "rights_evidence_url": entry["rights_evidence_url"],
            "license": entry["license"],
            "license_status": "catalogued_source_claim_not_legal_opinion",
            "bytes": total,
            "pdf_sha256": actual,
            "checksum_verified_against_pin": expected is not None,
            "source_category": entry["source_category"],
            "musicxml_reference_status": "missing",
            "human_review_status": "not_reviewed",
        }
        # O link atômico falha se já existir arquivo de mesmo nome (Linux).
        os.link(temporary, pdf_path)
        try:
            with metadata_path.open("x", encoding="utf-8") as out:
                json.dump(metadata, out, indent=2, ensure_ascii=False)
                out.write("\n")
        except BaseException:
            pdf_path.unlink()
            raise
        return metadata
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("tests/data/real_scores/sources.json"),
    )
    parser.add_argument("--id", action="append", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        entries = load_catalog(args.catalog)
        if any(key not in entries for key in args.id):
            raise CorpusSourceError("obra não cadastrada no catálogo")
        if len(set(args.id)) != len(args.id):
            raise CorpusSourceError("id repetido")
        acquired = [download_score(entries[key], args.out_dir) for key in args.id]
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps({"acquired": acquired}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
