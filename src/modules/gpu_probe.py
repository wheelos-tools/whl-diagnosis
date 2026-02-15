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
GPU 健康度诊断模块
支持 NVIDIA GPU (通过 nvidia-smi) 和未来的其他加速器
"""

import json
from typing import List, Dict

from src.core.interface import IDiagnosticProbe, DiagResult, Status, Severity
from src.utils.shell_runner import run_command


class GPUProbe(IDiagnosticProbe):

    @property
    def name(self) -> str:
        return "GPU Health Probe"

    @property
    def timeout_seconds(self) -> float:
        return 15.0

    def run_check(self) -> List[DiagResult]:
        results = []

        # 使用 nvidia-smi 查询 JSON 格式数据
        cmd_result = run_command(
            [
                "nvidia-smi",
                "--query-gpu=index,name,temperature.gpu,utilization.gpu,"
                "utilization.memory,memory.total,memory.used,clocks_throttle_reasons.active,ecc.errors.corrected.aggregate.total",
                "--format=csv,noheader,nounits",
            ]
        )

        if not cmd_result.success:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="GPU Detection",
                    status=Status.FAIL,
                    severity=Severity.CRITICAL,
                    message=f"nvidia-smi failed: {cmd_result.stderr}",
                    error_code="INFRA_GPU_NOT_FOUND",
                )
            )
            return results

        for line in cmd_result.stdout.strip().split("\n"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 8:
                continue

            idx, gpu_name, temp, gpu_util, mem_util, mem_total, mem_used, throttle = (
                parts[:8]
            )
            ecc_errors = parts[8] if len(parts) > 8 else "0"

            temp = int(temp)
            temp_threshold = self.config.get("gpu_temp_threshold", 85)

            # 温度检查
            if temp >= temp_threshold:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"GPU[{idx}] Temperature",
                        status=Status.FAIL if temp > 95 else Status.WARN,
                        severity=Severity.CRITICAL if temp > 95 else Severity.MAJOR,
                        message=f"{gpu_name}: {temp}°C (threshold: {temp_threshold}°C)",
                        metrics={"gpu_index": idx, "temperature_c": temp},
                        error_code="INFRA_GPU_THROTTLE",
                    )
                )
            else:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"GPU[{idx}] Temperature",
                        status=Status.PASS,
                        severity=Severity.INFO,
                        message=f"{gpu_name}: {temp}°C OK",
                        metrics={"gpu_index": idx, "temperature_c": temp},
                    )
                )

            # ECC 错误检查
            ecc_count = int(ecc_errors) if ecc_errors.isdigit() else 0
            if ecc_count > 0:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"GPU[{idx}] ECC Errors",
                        status=Status.WARN,
                        severity=Severity.MAJOR,
                        message=f"ECC corrected errors: {ecc_count}. 硬件可能正在老化。",
                        metrics={"ecc_errors": ecc_count},
                        error_code="INFRA_GPU_ECC",
                    )
                )

            # 降频检查
            if throttle and throttle.lower() not in (
                "0x0000000000000000",
                "[not supported]",
                "0",
            ):
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"GPU[{idx}] Throttling",
                        status=Status.WARN,
                        severity=Severity.MAJOR,
                        message=f"GPU is throttling! Reason bitmask: {throttle}",
                        metrics={"throttle_reason": throttle},
                        error_code="INFRA_GPU_THROTTLE",
                    )
                )

        return results
