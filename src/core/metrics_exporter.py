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


"""将诊断结果导出为 Prometheus 格式，支持 Grafana 监控"""

from typing import List
from .interface import DiagResult, Status


def export_prometheus(results: List[DiagResult]) -> str:
    """
    生成 Prometheus exposition format
    可被 node_exporter 的 textfile collector 采集
    输出到 /var/lib/prometheus/node-exporter/ad_diag.prom
    """
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

    for r in results:
        safe_module = r.module_name.replace(" ", "_").lower()
        safe_item = r.item_name.replace(" ", "_").lower()
        val = status_val.get(r.status, -1)
        lines.append(
            f'ad_diag_check_status{{module="{safe_module}",item="{safe_item}",'
            f'phase="{r.phase.value.lower()}",probe="{r.probe_type.value.lower()}"}} {val}'
        )

        # 额外导出具体 metrics
        for k, v in r.metrics.items():
            if isinstance(v, (int, float)):
                lines.append(
                    f'ad_diag_metric{{module="{safe_module}",item="{safe_item}",'
                    f'phase="{r.phase.value.lower()}",probe="{r.probe_type.value.lower()}",'
                    f'metric="{k}"}} {v}'
                )

    return "\n".join(lines) + "\n"
