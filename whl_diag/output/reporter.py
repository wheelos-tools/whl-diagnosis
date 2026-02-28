import hashlib
import json
import time
from typing import List

from ..execution.interface import DiagResult, Status
from ..knowledge.error_codes import get_remediation


class BaseReporter:
    def generate(self, results: List[DiagResult], metadata: dict) -> str:
        raise NotImplementedError


class JsonReporter(BaseReporter):
    def generate(self, results: List[DiagResult], metadata: dict) -> str:
        report = {
            "schema_version": "1.1.0",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "vehicle_id": metadata.get("vehicle_id", "unknown"),
            "vehicle_type": metadata.get("vehicle_type", "unknown"),
            "diagnosis_mode": metadata.get("diagnosis_mode", "default"),
            "config_version": metadata.get("config_version", ""),
            "software_version": metadata.get("software_version", ""),
            "summary": {
                "total": len(results),
                "pass": sum(1 for result in results if result.status == Status.PASS),
                "warn": sum(1 for result in results if result.status == Status.WARN),
                "fail": sum(1 for result in results if result.status == Status.FAIL),
                "error": sum(1 for result in results if result.status == Status.ERROR),
                "skip": sum(1 for result in results if result.status == Status.SKIP),
            },
            "domain_summary": self._generate_domain_summary(results),
            "results": [
                {
                    "module": result.module_name,
                    "item": result.item_name,
                    "status": result.status.value,
                    "severity": result.severity.value,
                    "message": result.message,
                    "phase": result.phase.value,
                    "probe_type": result.probe_type.value,
                    "metrics": result.metrics,
                    "error_code": result.error_code,
                    "remediation": (
                        get_remediation(result.error_code) if result.error_code else ""
                    ),
                    "timestamp": result.timestamp,
                }
                for result in results
            ],
        }
        signature = hashlib.sha256(
            json.dumps(report, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        report["report_sha256"] = signature
        return json.dumps(report, indent=2, ensure_ascii=False)

    def _generate_domain_summary(self, results: List[DiagResult]) -> dict:
        domains = {}
        for r in results:
            domain = r.module_name.split()[0] # Rough categorization based on module name prefix
            if domain not in domains:
                domains[domain] = {"total": 0, "pass": 0, "fail": 0, "warn": 0}

            domains[domain]["total"] += 1
            if r.status == Status.PASS:
                domains[domain]["pass"] += 1
            elif r.status in (Status.FAIL, Status.ERROR):
                domains[domain]["fail"] += 1
            elif r.status == Status.WARN:
                domains[domain]["warn"] += 1

        return domains


class HtmlReporter(BaseReporter):
    """Generates a standalone HTML dashboard without relying on external template engines like Jinja2."""

    def generate(self, results: List[DiagResult], metadata: dict) -> str:
        # Pre-compute summaries
        total_checks = len(results)
        fail_checks = sum(1 for r in results if r.status in (Status.FAIL, Status.ERROR))
        warn_checks = sum(1 for r in results if r.status == Status.WARN)
        pass_checks = sum(1 for r in results if r.status == Status.PASS)

        status_color_class = "success" if fail_checks == 0 else "danger"
        status_text = "PASSED" if fail_checks == 0 else "FAILED"

        # Generate rows for the table
        rows_html = ""
        for r in results:
            if r.status == Status.PASS:
                row_class = "table-success"
                badge_class = "bg-success"
            elif r.status in (Status.FAIL, Status.ERROR):
                row_class = "table-danger"
                badge_class = "bg-danger"
            elif r.status == Status.WARN:
                row_class = "table-warning"
                badge_class = "bg-warning"
            else:
                row_class = "table-secondary"
                badge_class = "bg-secondary"

            remediation_text = get_remediation(r.error_code) if r.error_code else "-"

            # Simple metric string formatting
            metrics_str = ", ".join(f"{k}={v}" for k, v in r.metrics.items()) if r.metrics else "-"

            rows_html += f"""
            <tr class="{row_class}">
                <td>{r.module_name}</td>
                <td>{r.item_name}</td>
                <td><span class="badge {badge_class}">{r.status.value}</span></td>
                <td>{r.message}</td>
                <td><small><code>{r.error_code or '-'}</code></small></td>
                <td><small>{remediation_text}</small></td>
                <td><small class="text-muted">{metrics_str}</small></td>
            </tr>
            """

        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WheelOS Diagnostic Report</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ background-color: #f8f9fa; padding: 20px; }}
        .header-card {{ margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .summary-box {{ text-align: center; padding: 15px; border-radius: 8px; margin-bottom: 20px; color: white; }}
        .bg-pass {{ background-color: #198754; }}
        .bg-fail {{ background-color: #dc3545; }}
        .bg-warn {{ background-color: #ffc107; color: black; }}
        .bg-total {{ background-color: #0d6efd; }}
        .table-container {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="card header-card">
            <div class="card-body d-flex justify-content-between align-items-center">
                <div>
                    <h2 class="card-title mb-0">Autonomous Driving Diagnostic Report</h2>
                    <p class="text-muted mb-0">Time: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
                <div class="text-end">
                    <h4 class="mb-0">Vehicle: {metadata.get('vehicle_id', 'UNKNOWN')}</h4>
                    <span class="badge bg-{status_color_class} fs-6">System Status: {status_text}</span>
                </div>
            </div>
        </div>

        <div class="row">
            <div class="col-md-3">
                <div class="summary-box bg-total">
                    <h3>{total_checks}</h3>
                    <div>Total Checks</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="summary-box bg-pass">
                    <h3>{pass_checks}</h3>
                    <div>Passed</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="summary-box bg-warn">
                    <h3>{warn_checks}</h3>
                    <div>Warnings</div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="summary-box bg-fail">
                    <h3>{fail_checks}</h3>
                    <div>Failed</div>
                </div>
            </div>
        </div>

        <div class="table-container">
            <table class="table table-hover table-sm">
                <thead class="table-dark">
                    <tr>
                        <th>Domain/Module</th>
                        <th>Check Item</th>
                        <th>Status</th>
                        <th>Message</th>
                        <th>Error Code</th>
                        <th>Remediation Suggestion</th>
                        <th>Key Metrics</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>"""
        return html_template


class ConsoleReporter(BaseReporter):
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
            from rich.panel import Panel
            from rich.table import Table
            from rich import box
        except ImportError:
            return self._fallback_generate(results)

        # Use force_terminal to ensure color sequences are captured
        console = Console(force_terminal=True, width=120)
        table = Table(
            title=f"🚗 AD Diagnostic Report — {metadata.get('vehicle_id', 'N/A')}",
            show_lines=False,
            expand=False,
            box=box.SIMPLE
        )
        table.add_column("Module", style="cyan")
        table.add_column("Check Item")
        table.add_column("Status", justify="center")
        table.add_column("Message", style="white")
        table.add_column("Error Code", style="dim")

        for result in results:
            table.add_row(
                result.module_name,
                result.item_name,
                self.STATUS_STYLE.get(result.status, str(result.status)),
                result.message,
                result.error_code or "-",
            )

        with console.capture() as capture:
            console.print(table)
            console.print("")

            fail_count = sum(
                1 for result in results if result.status in (Status.FAIL, Status.ERROR)
            )
            if fail_count == 0:
                console.print(Panel("[bold green]ALL CHECKS PASSED ✅[/]", border_style="green", expand=False))
            else:
                console.print(
                    Panel(
                        f"[bold red]{fail_count} CRITICAL ISSUE(S) FOUND[/]",
                        border_style="red",
                        expand=False
                    )
                )

        return capture.get()

    def _fallback_generate(self, results: List[DiagResult]) -> str:
        return "\n".join(
            f"[{result.status.value:5s}] {result.module_name} / {result.item_name}: {result.message}"
            for result in results
        )

class LlmReporter(BaseReporter):
    """
    Generates a Markdown file specifically designed to act as rich context for LLMs.
    It focuses heavily on failed/warn items, providing raw execution output and contextual system logs.
    """
    def generate(self, results: List[DiagResult], metadata: dict) -> str:
        lines = []
        lines.append(f"# Diagnostic Report for LLM Analysis")
        lines.append(f"**Vehicle ID:** {metadata.get('vehicle_id', 'unknown')}")
        lines.append(f"**Template Mode:** {metadata.get('diagnosis_mode', 'default')}")
        lines.append(f"**Generated At:** {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
        lines.append("\n## Context For LLM:")
        lines.append("The following probes have reported warnings, failures, or errors. Please help analyze the root cause based on the `Raw Log` or `System Log` block.\n")

        abnormal_results = [r for r in results if r.status in [Status.FAIL, Status.WARN, Status.ERROR, Status.SKIP]]

        if not abnormal_results:
            lines.append("### All Systems Normal")
            lines.append("No errors or failures detected across any probes.")
            return "\n".join(lines)

        for i, res in enumerate(abnormal_results, 1):
            lines.append(f"### {i}. [{res.status.value}] Probe: {res.module_name} -> {res.item_name}")

            crit = getattr(res, 'criticality', 'BLOCKER')
            if hasattr(crit, 'value'):
                crit = crit.value

            lines.append(f"- **Severity:** {res.severity.value} | **Criticality:** {crit}")
            lines.append(f"- **Summary Message:** {res.message}")
            if res.error_code:
                lines.append(f"- **Error Code:** {res.error_code}")

            # If Skipped, raw log doesn't matter much
            if res.status == Status.SKIP:
                lines.append(f"- **Note:** Skipped likely due to upstream failure.\n")
                continue

            # Add Raw Output
            lines.append(f"\n#### Raw Execution Output:")
            if getattr(res, 'raw_output', ''):
                lines.append("```text\n" + res.raw_output.strip() + "\n```")
            else:
                lines.append("*(No raw stdout captured)*")

            # Add Subsystem/dmesg Log
            lines.append(f"\n#### Surrounding Subsystem Logs (dmesg/journal):")
            if getattr(res, 'sys_logs', ''):
                lines.append("```text\n" + res.sys_logs.strip() + "\n```")
            else:
                lines.append("*(No surrounding system logs discovered)*\n")

            lines.append("---\n")

        return "\n".join(lines)

class RawReporter(BaseReporter):
    def generate(self, results: List[DiagResult], metadata: dict) -> str:
        lines = [f"[{r.status.value:5s}] {r.module_name:20s} | {r.item_name:25s} | {r.message}" for r in results]
        fail_count = sum(1 for r in results if r.status in (Status.FAIL, Status.ERROR))
        lines.append(f"\nTotal CRITICAL items: {fail_count}")
        return "\n".join(lines)