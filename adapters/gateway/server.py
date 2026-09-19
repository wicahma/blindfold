"""Blindfold standalone gateway server — zero-dependency reverse proxy.

Uses stdlib http.server + urllib.request. Proxies incoming requests to an
upstream URL (e.g. OpenAI, Anthropic, or local Ollama/vLLM), scrubbing secrets
from both requests and responses.

Can be run directly via:
    python3 -m blindfold.adapters.gateway.server --port 8080 --upstream https://api.openai.com
"""
from __future__ import annotations

import argparse
import http.server
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Type

from .build import build_handler
from .mask import mask_messages, mask_response

logger = logging.getLogger("blindfold.gateway")


def make_handler(upstream_url: str, secrets: list[str]) -> Type[http.server.BaseHTTPRequestHandler]:
    """Factory creating an HTTP handler bound to upstream_url and secrets list."""
    clean_upstream = upstream_url.rstrip("/")
    values = [s for s in secrets if s]

    class GatewayHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Terse: no spammy access logs by default
            pass

        def _forward(self, body_bytes: bytes | None = None):
            target_url = f"{clean_upstream}{self.path}"
            headers = {k: v for k, v in self.headers.items() if k.lower() not in ("host", "content-length")}

            if body_bytes is not None:
                # Mask request body if JSON
                try:
                    data = json.loads(body_bytes.decode("utf-8"))
                    masked = mask_messages(data, values)
                    body_bytes = json.dumps(masked).encode("utf-8")
                except Exception:
                    pass  # Non-JSON or raw payload: pass through as-is
                headers["Content-Length"] = str(len(body_bytes))

            req = urllib.request.Request(target_url, data=body_bytes, headers=headers, method=self.command)

            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    resp_status = resp.status
                    resp_headers = resp.headers
                    resp_body = resp.read()
            except urllib.error.HTTPError as e:
                resp_status = e.code
                resp_headers = e.headers
                resp_body = e.read()
            except Exception as e:
                self.send_error(502, f"Bad Gateway: {e}")
                return

            # Mask response body if JSON
            try:
                data = json.loads(resp_body.decode("utf-8"))
                masked = mask_response(data, values)
                resp_body = json.dumps(masked).encode("utf-8")
            except Exception:
                pass

            self.send_response(resp_status)
            for k, v in resp_headers.items():
                if k.lower() not in ("transfer-encoding", "content-length", "content-encoding"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)

        def do_GET(self):
            self._forward(None)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length > 0 else None
            self._forward(body)

        def do_PUT(self):
            self.do_POST()

        def do_DELETE(self):
            self._forward(None)

    return GatewayHandler


def run_gateway(host: str = "127.0.0.1", port: int = 8080, upstream_url: str = "https://api.openai.com", roots: list[Path] | None = None):
    handler = build_handler(roots=roots)
    handler_cls = make_handler(upstream_url=upstream_url, secrets=handler.values)
    server = http.server.ThreadingHTTPServer((host, port), handler_cls)
    print(f"Blindfold gateway listening on http://{host}:{port} -> {upstream_url} ({len(handler.values)} secret values tracked)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Blindfold universal gateway proxy")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--upstream", default="https://api.openai.com")
    args = parser.parse_args()
    run_gateway(host=args.host, port=args.port, upstream_url=args.upstream)
