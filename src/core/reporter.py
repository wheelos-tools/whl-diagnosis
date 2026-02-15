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


"""
报告生成器：支持多种输出格式
- Console (Rich)
- JSON (机器可读，供 Prometheus/Grafana 采集)
- HTML (离线查看)
- 历史对比 (diff)
"""

import json
import hashlib
import time
from pathlib import Path
from typing import List, Optional

from .interface import DiagResult, Status
from .error_codes import get_remediation


class BaseReporter:
    def generate(self, results: List[DiagResult], metadata: dict) -> str:
        raise NotImplementedError


class JsonReporter(BaseReporter):
    """生成结构化 JSON 报告，可被监控系统采集"""

    def generate(self, results: List[DiagResult], metadata: dict) -> str:
        report = {
            "schema_version": "1.0.0",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "vehicle_id": metadata.get("vehicle_id", "unknown"),
            "vehicle_type": metadata.get("vehicle_type", "unknown"),
            "diagnosis_mode": metadata.get("diagnosis_mode", "default"),
            "config_version": metadata.get("config_version", ""),
            "software_version": metadata.get("software_version", ""),
            "summary": {
                "total": len(results),
                "pass": sum(1 for r in results if r.status == Status.PASS),
                "warn": sum(1 for r in results if r.status == Status.WARN),
                "fail": sum(1 for r in results if r.status == Status.FAIL),
                "error": sum(1 for r in results if r.status == Status.ERROR),
                "skip": sum(1 for r in results if r.status == Status.SKIP),
            },
            "results": [
                {
                    "module": r.module_name,
                    "item": r.item_name,
                    "status": r.status.value,
                    "severity": r.severity.value,
                    "message": r.message,
                    "phase": r.phase.value,
                    "probe_type": r.probe_type.value,
                    "metrics": r.metrics,
                    "error_code": r.error_code,
                    "remediation": (
                        get_remediation(r.error_code) if r.error_code else ""
                    ),
                    "timestamp": r.timestamp,
                }
                for r in results
            ],
        }
        signature = hashlib.sha256(
            json.dumps(report, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        report["report_sha256"] = signature
        return json.dumps(report, indent=2, ensure_ascii=False)


class ConsoleReporter(BaseReporter):
    """Rich 终端彩色输出"""

    STATUS_STYLE = {
        Status.PASS: "[bold green]✅ PASS[/]",
        Status.WARN: "[bold yellow]⚠️  WARN[/]",
        Status.FAIL: "[bold red]❌ FAIL[/]",
        Status.ERROR: "[bold red on white]💥 ERROR[/]",
        Status.SKIP: "[dim]⏭️  SKIP[/]",
    }

    def generate(self, results: List[DiagResult], metadata: dict) -> str:
        try:
            from rich.console import Console
            from rich.table import Table
            from rich.panel import Panel
        except ImportError:
            return self._fallback_generate(results)

        console = Console(record=True)
        table = Table(
            title=f"🚗 AD Diagnostic Report — {metadata.get('vehicle_id', 'N/A')}",
            show_lines=True,
        )
        table.add_column("Module", style="cyan", width=24)
        table.add_column("Check Item", width=28)
        table.add_column("Phase", width=10)
        table.add_column("Probe", width=10)
        table.add_column("Status", width=12, justify="center")
        table.add_column("Message", width=50)
        table.add_column("Error Code", width=24)

        for r in results:
            table.add_row(
                r.module_name,
                r.item_name,
                r.phase.value,
                r.probe_type.value,
                self.STATUS_STYLE.get(r.status, str(r.status)),
                r.message,
                r.error_code or "-",
            )

        console.print(table)

        # Summary panel
        fail_count = sum(1 for r in results if r.status in (Status.FAIL, Status.ERROR))
        if fail_count == 0:
            console.print(
                Panel("[bold green]ALL CHECKS PASSED ✅[/]", border_style="green")
            )
        else:
            console.print(
                Panel(
                    f"[bold red]{fail_count} CRITICAL ISSUE(S) FOUND[/]",
                    border_style="red",
                )
            )

        return console.export_text()

    def _fallback_generate(self, results: List[DiagResult]) -> str:
        """Rich 未安装时的降级输出"""
        lines = []
        for r in results:
            lines.append(
                f"[{r.status.value:5s}] {r.module_name} / {r.item_name}: {r.message}"
            )
        return "\n".join(lines)
