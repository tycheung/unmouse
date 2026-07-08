from __future__ import annotations

import inspect
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from unmouse.launcher.api import PanelApi
from unmouse.launcher.panel import ui_assets_dir, ui_index_path

E2E_BRIDGE = """
(function () {
  window.pywebview = window.pywebview || {};
  window.pywebview.api = new Proxy(
    {},
    {
      get(_target, prop) {
        if (prop === "then") return undefined;
        return async (...args) => {
          const resp = await fetch("/api/" + String(prop), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ args }),
          });
          const text = await resp.text();
          if (!resp.ok) throw new Error(text || resp.statusText);
          return text ? JSON.parse(text) : null;
        };
      },
    },
  );
})();
"""


def _panel_api_methods(api: PanelApi) -> set[str]:
    return {
        name
        for name, value in inspect.getmembers(api, predicate=callable)
        if not name.startswith("_")
    }


class E2EHarness:
    def __init__(self, api: PanelApi, *, host: str = "127.0.0.1", port: int = 0) -> None:
        self.api = api
        self.host = host
        self.port = port
        self._methods = _panel_api_methods(api)
        self._assets = ui_assets_dir()
        self._index_html = self._build_index_html()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            msg = "E2E harness is not running"
            raise RuntimeError(msg)
        host = self._server.server_address[0]
        port = self._server.server_address[1]
        return f"http://{host}:{port}/"

    def start(self) -> None:
        if self._server is not None:
            return
        handler = self._make_handler()
        self._server = ThreadingHTTPServer((self.host, self.port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None
        self.api.shutdown()

    def _build_index_html(self) -> bytes:
        html = ui_index_path().read_text(encoding="utf-8")
        injection = f"<script>{E2E_BRIDGE}</script>"
        if "</head>" in html:
            html = html.replace("</head>", f"{injection}\n  </head>", 1)
        elif "<body" in html:
            html = html.replace("<body", f"{injection}\n  <body", 1)
        else:
            html = injection + html
        return html.encode("utf-8")

    def _make_handler(self) -> type[BaseHTTPRequestHandler]:
        harness = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def do_GET(self) -> None:
                path = urlparse(self.path).path
                if path in {"", "/"}:
                    self._send_bytes(harness._index_html, "text/html; charset=utf-8")
                    return
                asset_path = harness._resolve_asset(path)
                if asset_path is None:
                    self.send_error(404)
                    return
                content_type = "application/octet-stream"
                if asset_path.suffix == ".css":
                    content_type = "text/css; charset=utf-8"
                elif asset_path.suffix == ".js":
                    content_type = "application/javascript; charset=utf-8"
                self._send_bytes(asset_path.read_bytes(), content_type)

            def do_POST(self) -> None:
                path = urlparse(self.path).path
                if not path.startswith("/api/"):
                    self.send_error(404)
                    return
                method = unquote(path.removeprefix("/api/"))
                if method not in harness._methods:
                    self.send_error(404, f"Unknown API method: {method}")
                    return
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length) if length else b"{}"
                payload = json.loads(raw.decode("utf-8") or "{}")
                args = payload.get("args", [])
                kwargs = payload.get("kwargs", {})
                try:
                    result = getattr(harness.api, method)(*args, **kwargs)
                except Exception as exc:
                    self.send_error(500, str(exc))
                    return
                body = json.dumps(result).encode("utf-8")
                self._send_bytes(body, "application/json")

            def _send_bytes(self, body: bytes, content_type: str) -> None:
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler

    def _resolve_asset(self, path: str) -> Path | None:
        relative = path.lstrip("/")
        if not relative or ".." in relative.replace("\\", "/"):
            return None
        candidate = (self._assets / relative).resolve()
        assets_root = self._assets.resolve()
        if assets_root not in candidate.parents and candidate != assets_root:
            return None
        return candidate if candidate.is_file() else None
