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

# Created Date: 2025-02-28
# Author: daohu527

"""
GPU health diagnostics module
Supports NVIDIA GPUs (via `nvidia-smi`) and future accelerators

Features:
    - GPU detection and liveness
    - Temperature and thermal throttling detection
    - ECC memory error detection
    - Power draw and power limit checks
    - PCIe bandwidth checks
"""

from typing import List

from whl_diag.execution.interface import IDiagnosticProbe, DiagResult, Status, Severity, Phase, ProbeType
from whl_diag.utils.shell_runner import run_command


class GPUProbe(IDiagnosticProbe):

    @property
    def name(self) -> str:
        return "GPU Health Probe"

    @property
    def timeout_seconds(self) -> float:
        return 15.0

    def run_check(self) -> List[DiagResult]:
        results = []

        # Query GPU telemetry through nvidia-smi
        # Added power.draw, power.limit, pcie.link.gen.current, pcie.link.gen.max
        cmd_result = run_command(
            [
                "nvidia-smi",
                "--query-gpu=index,name,temperature.gpu,utilization.gpu,"
                "utilization.memory,memory.total,memory.used,clocks_throttle_reasons.active,"
                "ecc.errors.corrected.aggregate.total,power.draw,power.limit,"
                "pcie.link.gen.current,pcie.link.gen.max",
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
                    phase=Phase.DISCOVERY,
                    probe_type=ProbeType.LIVENESS,
                    error_code="INFRA_GPU_NOT_FOUND",
                    raw_output=cmd_result.stderr,
                    sys_logs=self.fetch_system_logs("nvidia", 30),
                )
            )
            return results

        for line in cmd_result.stdout.strip().split("\n"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 13:
                continue

            idx, gpu_name, temp, gpu_util, mem_util, mem_total, mem_used, throttle, ecc_errors, power_draw, power_limit, pcie_gen_cur, pcie_gen_max = parts

            temp = int(temp) if temp.isdigit() else 0
            temp_threshold = self.config.get("gpu_temp_threshold", 85)

            # 1. Temperature check
            if temp >= temp_threshold:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"GPU[{idx}] Temperature",
                        status=Status.FAIL if temp > 95 else Status.WARN,
                        severity=Severity.CRITICAL if temp > 95 else Severity.MAJOR,
                        message=f"{gpu_name}: {temp}°C (threshold: {temp_threshold}°C)",
                        metrics={"gpu_index": idx, "temperature_c": temp},
                        error_code="INFRA_GPU_OVERHEAT",
                        raw_output=f"Temperature: {temp}°C (Throttling possible)",
                        sys_logs=self.fetch_system_logs("nvidia", 15),
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

            # 2. ECC error check
            ecc_count = int(ecc_errors) if ecc_errors.isdigit() else 0
            if ecc_count > 0:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"GPU[{idx}] ECC Errors",
                        status=Status.WARN,
                        severity=Severity.MAJOR,
                        message=f"ECC corrected errors: {ecc_count}. Hardware aging may be occurring.",
                        metrics={"ecc_errors": ecc_count},
                        error_code="INFRA_GPU_ECC",
                    )
                )

            # 3. Throttling check
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

            # 4. Power check (if supported)
            if power_draw != "[Not Supported]" and power_limit != "[Not Supported]":
                try:
                    p_draw = float(power_draw)
                    p_limit = float(power_limit)
                    if p_draw > p_limit * 0.95:
                        results.append(
                            DiagResult(
                                module_name=self.name,
                                item_name=f"GPU[{idx}] Power",
                                status=Status.WARN,
                                severity=Severity.MINOR,
                                message=f"GPU power draw ({p_draw}W) is near limit ({p_limit}W)",
                                metrics={"power_draw_w": p_draw, "power_limit_w": p_limit},
                                error_code="INFRA_GPU_POWER_LIMIT",
                            )
                        )
                except ValueError:
                    pass

            # 5. PCIe Bandwidth check
            if pcie_gen_cur != "[Not Supported]" and pcie_gen_max != "[Not Supported]":
                if pcie_gen_cur != pcie_gen_max:
                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name=f"GPU[{idx}] PCIe Link",
                            status=Status.WARN,
                            severity=Severity.MAJOR,
                            message=f"PCIe link downgraded: Gen {pcie_gen_cur} (Max: Gen {pcie_gen_max})",
                            metrics={"pcie_gen_current": pcie_gen_cur, "pcie_gen_max": pcie_gen_max},
                            error_code="INFRA_GPU_PCIE_DOWNGRADE",
                        )
                    )

        return results
