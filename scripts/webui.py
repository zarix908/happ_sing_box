#!/usr/bin/env python3
"""Minimal Web UI to pick one subscription URI (avoids slow urltest over all nodes)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from uri_list import load_uri_entries, write_selected_uri  # noqa: E402

WORK_DIR = Path(os.environ.get("CONFIG_WORK_DIR", "/tmp/happ-sing-box"))
URIS_FILE = WORK_DIR / "uris.txt"
SELECTED_INDEX_FILE = WORK_DIR / "selected.uri_index"
GENERATE_SCRIPT = Path(
    os.environ.get(
        "GENERATE_CONFIG_SCRIPT", "/opt/happ-sing-box/scripts/generate-config.sh"
    )
)
CHANGED_MARKER = WORK_DIR / "config.changed"
LISTEN = os.environ.get("WEBUI_LISTEN", "0.0.0.0")
PORT = int(os.environ.get("WEBUI_PORT", "8080"))
REGEN_LOCK = threading.Lock()


def read_selected_index() -> int:
    if not SELECTED_INDEX_FILE.is_file():
        return 0
    raw = SELECTED_INDEX_FILE.read_text(encoding="utf-8").strip()
    if raw.isdigit():
        return int(raw)
    return 0


def write_selected_index(index: int) -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    SELECTED_INDEX_FILE.write_text(f"{index}\n", encoding="utf-8")


def run_generate_config() -> tuple[bool, str]:
    env = os.environ.copy()
    with REGEN_LOCK:
        try:
            proc = subprocess.run(
                [str(GENERATE_SCRIPT)],
                env=env,
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return False, "config generation timed out"
        except OSError as exc:
            return False, str(exc)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return False, detail or f"exit {proc.returncode}"
    return True, "ok"


def nodes_payload() -> dict:
    if not URIS_FILE.is_file():
        return {
            "selected_index": read_selected_index(),
            "nodes": [],
            "error": "no subscription yet; wait for initial fetch",
        }
    entries = load_uri_entries(URIS_FILE)
    return {
        "selected_index": read_selected_index(),
        "nodes": [e.to_json() for e in entries],
    }


PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>happ-sing-box · node picker</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
    body { max-width: 42rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.45; }
    h1 { font-size: 1.25rem; font-weight: 600; }
    .meta { opacity: 0.75; font-size: 0.9rem; margin-bottom: 1rem; }
    ul { list-style: none; padding: 0; margin: 0; }
    li { margin: 0.35rem 0; }
    label { display: flex; gap: 0.6rem; align-items: flex-start; padding: 0.55rem 0.65rem;
            border: 1px solid color-mix(in srgb, CanvasText 18%, transparent); border-radius: 8px;
            cursor: pointer; }
    label:hover { background: color-mix(in srgb, CanvasText 6%, transparent); }
    input { margin-top: 0.2rem; }
    .name { font-weight: 600; }
    .sub { font-size: 0.85rem; opacity: 0.8; word-break: break-all; }
    button { margin-top: 1rem; padding: 0.55rem 1rem; font-size: 1rem; border-radius: 8px;
             border: 1px solid color-mix(in srgb, CanvasText 25%, transparent); cursor: pointer; }
    #status { margin-top: 0.75rem; min-height: 1.2rem; font-size: 0.9rem; }
    .err { color: #c0392b; }
    .ok { color: #27ae60; }
  </style>
</head>
<body>
  <h1>Choose proxy node</h1>
  <p class="meta">Only the selected URI is converted and used (no urltest sweep). Default: first in list.</p>
  <ul id="nodes"></ul>
  <button type="button" id="apply" disabled>Apply selection</button>
  <div id="status"></div>
  <script>
    const headers = { 'Content-Type': 'application/json' };

    let selected = 0;

    function setStatus(msg, cls) {
      const el = document.getElementById('status');
      el.textContent = msg;
      el.className = cls || '';
    }

    async function loadNodes() {
      const r = await fetch('/api/nodes');
      const data = await r.json();
      if (data.error) setStatus(data.error, 'err');
      selected = data.selected_index ?? 0;
      const ul = document.getElementById('nodes');
      ul.innerHTML = '';
      (data.nodes || []).forEach((n) => {
        const li = document.createElement('li');
        const id = 'node-' + n.index;
        li.innerHTML = `<label><input type="radio" name="node" id="${id}" value="${n.index}" />
          <span><span class="name">${escapeHtml(n.name)}</span><br /><span class="sub">${escapeHtml(n.scheme)} · ${escapeHtml(n.host)}</span></span></label>`;
        ul.appendChild(li);
        const input = li.querySelector('input');
        input.checked = n.index === selected;
        input.addEventListener('change', () => { selected = n.index; document.getElementById('apply').disabled = false; });
      });
      document.getElementById('apply').disabled = (data.nodes || []).length === 0;
    }

    function escapeHtml(s) {
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
    }

    document.getElementById('apply').addEventListener('click', async () => {
      setStatus('Applying…');
      const r = await fetch('/api/select', { method: 'POST', headers, body: JSON.stringify({ index: selected }) });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) { setStatus(data.error || r.statusText, 'err'); return; }
      setStatus('Applied. sing-box will reload if the config changed.', 'ok');
    });

    loadNodes().catch((e) => setStatus(String(e), 'err'));
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "happ-sing-box-webui/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[webui] " + (fmt % args) + "\n")

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, status: int, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._html(HTTPStatus.OK, PAGE_HTML)
            return
        if path == "/api/nodes":
            self._json(HTTPStatus.OK, nodes_payload())
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/select":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
            index = int(data["index"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "expected JSON {\"index\": number}"})
            return
        if not URIS_FILE.is_file():
            self._json(HTTPStatus.CONFLICT, {"error": "subscription not loaded yet"})
            return
        try:
            write_selected_index(index)
            write_selected_uri(URIS_FILE, index, WORK_DIR / "uris.selected.txt")
        except (ValueError, IndexError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        ok, msg = run_generate_config()
        if not ok:
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": msg})
            return
        self._json(HTTPStatus.OK, {"ok": True, "index": index, "detail": msg})


def main() -> int:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    if not SELECTED_INDEX_FILE.is_file():
        write_selected_index(0)
    httpd = ThreadingHTTPServer((LISTEN, PORT), Handler)
    sys.stderr.write(f"[webui] listening on http://{LISTEN}:{PORT}/\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
