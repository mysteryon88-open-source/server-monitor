"""Loopback-only read-only dashboard API; no general-purpose file or shell API."""

from __future__ import annotations

import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .fleet import MonitorFleet


class LocalHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def create_http_server(port: int, fleet: MonitorFleet, static_dir: Path,
                       token: str) -> LocalHTTPServer:
    routes = {
        "/": ("index.html", "text/html; charset=utf-8"),
        "/index.html": ("index.html", "text/html; charset=utf-8"),
        "/app.js": ("app.js", "text/javascript; charset=utf-8"),
        "/style.css": ("style.css", "text/css; charset=utf-8"),
        "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    }

    class Handler(BaseHTTPRequestHandler):
        server_version = "ServerMonitor"
        sys_version = ""
        protocol_version = "HTTP/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, format, *args):
            # Polling does not flood the launch window or write server data to logs.
            pass

        def _allowed_hosts(self) -> set[str]:
            actual_port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}"}
            if actual_port == 80:
                hosts.update({"127.0.0.1", "localhost"})
            return hosts

        def _host_ok(self) -> bool:
            return (len(self.headers.get_all("Host", [])) == 1
                    and self.headers.get("Host", "").lower() in self._allowed_hosts())

        def _authorized(self) -> bool:
            origin = self.headers.get("Origin")
            if origin is not None and origin not in {"http://" + host for host in self._allowed_hosts()}:
                return False
            if self.headers.get("Sec-Fetch-Site") == "cross-site":
                return False
            supplied = self.headers.get("X-Monitor-Token", "")
            return hmac.compare_digest(supplied.encode("utf-8"), token.encode("utf-8"))

        def _send(self, code: int, body: bytes, content_type: str = "application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self'; style-src 'self'; "
                             "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                             "base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            self.end_headers()
            if self.command != "HEAD":
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def _json(self, code: int, value: dict):
            self._send(code, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))

        def _route(self):
            if not self._host_ok():
                self._json(403, {"error": "Access is allowed only through localhost."})
                return
            try:
                url = urlsplit(self.path)
                path = url.path
            except ValueError:
                self._json(400, {"error": "Invalid address."})
                return
            if path.startswith("/api/"):
                if not self._authorized():
                    self._json(403, {"error": "Invalid session. Reload the page."})
                    return
                if path == "/api/servers":
                    if self.command not in {"GET", "HEAD"}:
                        self._json(405, {"error": "Use GET."})
                    else:
                        self._json(200, fleet.list_servers())
                    return
                if path not in {"/api/snapshot", "/api/reconnect"}:
                    self._json(404, {"error": "Not found."})
                    return
                try:
                    query = parse_qs(url.query, keep_blank_values=True, max_num_fields=4)
                except ValueError:
                    self._json(400, {"error": "Invalid server selection."})
                    return
                ids = query.get("server", ["0"])
                if set(query) - {"server"} or len(ids) != 1:
                    self._json(400, {"error": "Invalid server selection."})
                    return
                server_id = ids[0]
                if server_id not in fleet.states:
                    self._json(404, {"error": "Unknown server."})
                    return
                if path == "/api/snapshot":
                    if self.command not in {"GET", "HEAD"}:
                        self._json(405, {"error": "Use GET."})
                    else:
                        self._json(200, fleet.snapshot(server_id))
                elif path == "/api/reconnect":
                    if self.command != "POST":
                        self._json(405, {"error": "Use POST."})
                        return
                    if self.headers.get("Transfer-Encoding"):
                        self._json(400, {"error": "Chunked requests are not supported."})
                        return
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                    except ValueError:
                        length = -1
                    if not 0 <= length <= 1024:
                        self._json(413, {"error": "Request too large."})
                        return
                    if length:
                        self.rfile.read(length)
                    fleet.reconnect(server_id)
                    self._json(200, {"ok": True})
                return
            if self.command not in {"GET", "HEAD"}:
                self._json(405, {"error": "Use GET."})
                return
            entry = routes.get(path)
            if entry is None:
                self._json(404, {"error": "Not found."})
                return
            filename, mime = entry
            try:
                body = (static_dir / filename).read_bytes()
            except OSError:
                self._json(500, {"error": "Dashboard files are missing. Extract the complete ZIP."})
                return
            if filename == "index.html":
                body = body.replace(b"__MONITOR_TOKEN__", token.encode("ascii"))
                body = body.replace(b"__MONITOR_LANGUAGE__", fleet.config.language.encode("ascii"))
            self._send(200, body, mime)

        do_GET = _route
        do_HEAD = _route
        do_POST = _route

    return LocalHTTPServer(("127.0.0.1", port), Handler)
