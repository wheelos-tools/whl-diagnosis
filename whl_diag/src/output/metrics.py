from typing import List

from ..execution.interface import DiagResult, Status


def export_prometheus(results: List[DiagResult]) -> str:
    lines = [
        "# HELP ad_diag_check_status Diagnostic check status (1=pass, 0=fail)",
        "# TYPE ad_diag_check_status gauge",
    ]
    status_val = {
        Status.PASS: 1,
        Status.WARN: 0.5,
        Status.FAIL: 0,
        Status.ERROR: -1,
        Status.SKIP: -2,
    }

    for result in results:
        safe_module = result.module_name.replace(" ", "_").lower()
        safe_item = result.item_name.replace(" ", "_").lower()
        val = status_val.get(result.status, -1)
        lines.append(
            f'ad_diag_check_status{{module="{safe_module}",item="{safe_item}",'
            f'phase="{result.phase.value.lower()}",probe="{result.probe_type.value.lower()}"}} {val}'
        )

        for key, value in result.metrics.items():
            if isinstance(value, (int, float)):
                lines.append(
                    f'ad_diag_metric{{module="{safe_module}",item="{safe_item}",'
                    f'phase="{result.phase.value.lower()}",probe="{result.probe_type.value.lower()}",'
                    f'metric="{key}"}} {value}'
                )

    return "\n".join(lines) + "\n"
