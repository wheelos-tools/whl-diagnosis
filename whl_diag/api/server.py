# Copyright 2025 The WheelOS Team. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Created Date: 2025-02-15
# Author: daohu527

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import os

from whl_diag.execution.probe_catalog import PROBE_CATALOG
from whl_diag.execution.workflow import run_diagnostics
from whl_diag.output.reporter import JsonReporter


class DiagnosticHandler(BaseHTTPRequestHandler):
    def _read_dashboard_template(self) -> str:
        # Try several possible locations for dashboard.html
        import sys
        candidates = [
            Path(__file__).parent / "templates" / "dashboard.html",
            Path.cwd() / "whl_diag" / "api" / "templates" / "dashboard.html",
            Path.cwd() / "api" / "templates" / "dashboard.html",
            Path.cwd() / "templates" / "dashboard.html",
        ]
        # Also try sys.path entries
        for p in sys.path:
            p = Path(p)
            if (p / "whl_diag/api/templates/dashboard.html").exists():
                candidates.append(p / "whl_diag/api/templates/dashboard.html")
            if (p / "api/templates/dashboard.html").exists():
                candidates.append(p / "api/templates/dashboard.html")
            if (p / "templates/dashboard.html").exists():
                candidates.append(p / "templates/dashboard.html")
        for candidate in candidates:
            if candidate.exists():
                html = candidate.read_text(encoding="utf-8")
                default_config = os.getenv("AD_DIAG_CONFIG", "config/vehicle_topology.yaml")
                return html.replace("__DEFAULT_CONFIG__", default_config)
        raise FileNotFoundError(f"dashboard.html not found in any known location. Tried: {candidates}")

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "ok"})
            return

        if self.path in ("/", "/dashboard"):
            try:
                html = self._read_dashboard_template()
                raw = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            except Exception as exc:
                self._respond(500, {"error": str(exc)})
                return

        if self.path.startswith("/report"):
            try:
                # Basic query parsing for config path
                from urllib.parse import urlparse, parse_qs
                parsed_url = urlparse(self.path)
                qs = parse_qs(parsed_url.query)
                cfg = qs.get("config", [os.getenv("AD_DIAG_CONFIG", "config/vehicle_topology.yaml")])[0]

                config_path = Path(cfg)
                if not config_path.exists():
                     self._respond(404, {"error": f"Config file not found: {cfg}"})
                     return

                results, metadata, _ = run_diagnostics(config_path=config_path)
                from whl_diag.output.reporter import HtmlReporter
                html = HtmlReporter().generate(results, metadata)

                raw = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            except Exception as exc:
                import traceback
                traceback.print_exc()
                self._respond(500, {"error": str(exc)})
                return

        self._respond(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/run":
            self._respond(404, {"error": "not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = (
                self.rfile.read(content_length).decode("utf-8")
                if content_length
                else "{}"
            )
            payload = json.loads(body)
        except (ValueError, json.JSONDecodeError):
            self._respond(400, {"error": "invalid JSON payload"})
            return

        try:
            import tempfile
            config_content = payload.get("config_content")
            if config_content:
                # Write uploaded YAML to a temp file
                with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
                    tf.write(config_content)
                    config_path = Path(tf.name)
            else:
                config_path = Path(payload.get("config", "config/vehicle_topology.yaml"))
            mode = payload.get("mode", "default")
            selected_modules = payload.get("modules")

            if selected_modules is None:
                module_names = None
            elif isinstance(selected_modules, list):
                module_names = [str(name).strip() for name in selected_modules]
            else:
                self._respond(400, {"error": "'modules' must be a list of module names"})
                return

            results, metadata, unknown_modules = run_diagnostics(
                config_path=config_path,
                mode=mode,
                modules=module_names,
            )

            if unknown_modules:
                self._respond(
                    400,
                    {
                        "error": "unknown modules",
                        "unknown": unknown_modules,
                        "available": list(PROBE_CATALOG.keys()),
                    },
                )
                return

            report = JsonReporter().generate(results, metadata)
            self._respond(200, json.loads(report))
        except FileNotFoundError as exc:
            self._respond(404, {"error": str(exc)})
        except Exception as exc:
            self._respond(500, {"error": f"internal error: {type(exc).__name__}: {exc}"})

    def _respond(self, status: int, payload: dict):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def run_server(host: str = "0.0.0.0", port: int = 8080):
    server = HTTPServer((host, port), DiagnosticHandler)
    server.serve_forever()
