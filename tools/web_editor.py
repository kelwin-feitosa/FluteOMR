"""Editor OMR local: predições somente leitura e correções operacionais separadas."""

import argparse
import json
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from fluteomr.corrections import CorrectionError, PageCatalog, RevisionConflict

ASSETS = Path(__file__).with_name("web_static")
PAGE = re.compile(r"/api/pages/([0-9a-f]{20})(/image|/corrections)?")
MAX_BODY = 64 * 1024


class EditorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], catalog: PageCatalog):
        if address[0] != "127.0.0.1":
            raise ValueError("o editor web deve escutar somente em 127.0.0.1")
        super().__init__(address, EditorHandler)
        self.catalog = catalog
        self.token = secrets.token_urlsafe(32)


class EditorHandler(BaseHTTPRequestHandler):
    server: EditorServer

    def _headers(self, status: int, kind: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
            "frame-ancestors 'none'",
        )
        self.end_headers()

    def _bytes(self, status: int, payload: bytes, kind: str) -> None:
        self._headers(status, kind, len(payload))
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass  # cliente fechou enquanto recebia uma imagem grande

    def _json(self, status: int, data: dict | list) -> None:
        self._bytes(
            status,
            json.dumps(data, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def _origin(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    def _host_ok(self) -> bool:
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self) -> None:
        if not self._host_ok():
            self._error(403, "Host não permitido")
            return
        target = urlsplit(self.path)
        if target.query or target.fragment:
            self._error(404, "rota não encontrada")
            return
        static = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/app.css": ("app.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/geometry.js": ("geometry.js", "text/javascript; charset=utf-8"),
        }
        if target.path in static:
            name, kind = static[target.path]
            self._bytes(200, (ASSETS / name).read_bytes(), kind)
            return
        if target.path == "/api/bootstrap":
            self._json(
                200, {"token": self.server.token, "pages": self.server.catalog.pages()}
            )
            return
        match = PAGE.fullmatch(target.path)
        if match and match[2] != "/corrections":
            try:
                if match[2] == "/image":
                    path = self.server.catalog.image_path(match[1])
                    kind = (
                        "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
                    )
                    self._bytes(200, path.read_bytes(), kind)
                else:
                    self._json(200, self.server.catalog.page(match[1]))
            except KeyError:
                self._error(404, "página não encontrada")
            except (CorrectionError, OSError, ValueError) as exc:
                self._error(409, str(exc))
            return
        self._error(404, "rota não encontrada")

    def do_PUT(self) -> None:
        if not self._host_ok():
            self._error(403, "Host não permitido")
            return
        match = PAGE.fullmatch(urlsplit(self.path).path)
        if not match or match[2] != "/corrections" or urlsplit(self.path).query:
            self._error(404, "rota não encontrada")
            return
        if (
            self.headers.get("Origin") != self._origin()
            or self.headers.get("X-FluteOMR-Token") != self.server.token
            or self.headers.get("Content-Type", "").split(";", 1)[0].strip()
            != "application/json"
        ):
            self._error(403, "origem ou token inválido")
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
            if not 0 < length <= MAX_BODY:
                raise ValueError("corpo ausente ou grande demais")
            payload = json.loads(self.rfile.read(length))
            self._json(200, self.server.catalog.save(match[1], payload))
        except KeyError:
            self._error(404, "página não encontrada")
        except RevisionConflict as exc:
            self._error(409, str(exc))
        except (CorrectionError, ValueError, json.JSONDecodeError) as exc:
            self._error(400, str(exc))
        except OSError as exc:
            self._error(500, str(exc))

    def do_POST(self) -> None:
        self._error(405, "método não permitido")

    def do_DELETE(self) -> None:
        self._error(405, "método não permitido")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--images-dir", type=Path, default=root / "outputs/novas-partituras/png"
    )
    parser.add_argument(
        "--suggestions-dir",
        type=Path,
        default=root / "outputs/novas-partituras/suggestions",
    )
    parser.add_argument(
        "--corrections-dir", type=Path, default=root / "outputs/web-editor/corrections"
    )
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        catalog = PageCatalog(
            args.images_dir, args.suggestions_dir, args.corrections_dir
        )
    except (CorrectionError, OSError) as exc:
        parser.error(str(exc))
    with EditorServer(("127.0.0.1", args.port), catalog) as server:
        print(f"FluteOMR: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
