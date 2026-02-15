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
系统基础设施诊断模块

功能:
  - CPU 核心数 / 温度 / 频率降频检测
  - 内存使用率
  - 磁盘剩余空间与 SMART 状态
  - PCIe 带宽协商检测 (x16 降级为 x8 等)
"""

import os
import re
import glob
import logging
from typing import List

from src.core.interface import IDiagnosticProbe, DiagResult, Status, Severity
from src.utils.shell_runner import run_command, read_sysfs

logger = logging.getLogger(__name__)


class SystemProbe(IDiagnosticProbe):

    @property
    def name(self) -> str:
        return "System Infrastructure Probe"

    @property
    def timeout_seconds(self) -> float:
        return 20.0

    def run_check(self) -> List[DiagResult]:
        results = []
        results.extend(self._check_cpu())
        results.extend(self._check_memory())
        results.extend(self._check_disk())
        results.extend(self._check_pcie())
        return results

    # ── CPU 检查 ──

    def _check_cpu(self) -> List[DiagResult]:
        results = []

        # CPU 核心数
        expected_cores = self.config.get("infrastructure", {}).get(
            "expected_cpu_cores", 1
        )
        actual_cores = os.cpu_count() or 0

        if actual_cores >= expected_cores:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="CPU Core Count",
                    status=Status.PASS,
                    severity=Severity.INFO,
                    message=f"{actual_cores} cores detected (expected >= {expected_cores})",
                    metrics={"cpu_cores": actual_cores},
                )
            )
        else:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="CPU Core Count",
                    status=Status.WARN,
                    severity=Severity.MAJOR,
                    message=f"Only {actual_cores} cores (expected {expected_cores}). "
                    "检查是否有核心被 isolcpus 隔离或被 offline。",
                    metrics={"cpu_cores": actual_cores},
                    error_code="INFRA_CPU_CORE_MISMATCH",
                )
            )

        # CPU 温度 (通过 hwmon)
        results.extend(self._check_cpu_temperature())

        # CPU 频率降频检测
        results.extend(self._check_cpu_frequency())

        return results

    def _check_cpu_temperature(self) -> List[DiagResult]:
        results = []
        threshold = self.config.get("thresholds", {}).get("cpu_temp_c", 90)

        # 遍历 hwmon 目录查找 CPU 温度传感器
        hwmon_dirs = glob.glob("/sys/class/hwmon/hwmon*/")
        for hwmon in hwmon_dirs:
            name_file = os.path.join(hwmon, "name")
            name = read_sysfs(name_file)
            if name and name in ("coretemp", "k10temp", "zenpower"):
                # 找到 CPU 温度传感器
                temp_files = glob.glob(os.path.join(hwmon, "temp*_input"))
                max_temp = 0
                for tf in temp_files:
                    val = read_sysfs(tf)
                    if val and val.isdigit():
                        temp_c = int(val) // 1000  # millidegree → degree
                        max_temp = max(max_temp, temp_c)

                if max_temp > 0:
                    if max_temp >= threshold:
                        results.append(
                            DiagResult(
                                module_name=self.name,
                                item_name="CPU Temperature",
                                status=(
                                    Status.FAIL
                                    if max_temp > threshold + 10
                                    else Status.WARN
                                ),
                                severity=(
                                    Severity.CRITICAL
                                    if max_temp > threshold + 10
                                    else Severity.MAJOR
                                ),
                                message=f"CPU temp: {max_temp}°C (threshold: {threshold}°C)",
                                metrics={"cpu_temp_c": max_temp},
                                error_code="INFRA_CPU_OVERTEMP",
                            )
                        )
                    else:
                        results.append(
                            DiagResult(
                                module_name=self.name,
                                item_name="CPU Temperature",
                                status=Status.PASS,
                                severity=Severity.INFO,
                                message=f"CPU temp: {max_temp}°C",
                                metrics={"cpu_temp_c": max_temp},
                            )
                        )
                break

        return results

    def _check_cpu_frequency(self) -> List[DiagResult]:
        """检测 CPU 是否被降频 (governor 不是 performance)"""
        results = []
        governors = set()

        for policy_dir in glob.glob("/sys/devices/system/cpu/cpufreq/policy*/"):
            gov = read_sysfs(os.path.join(policy_dir, "scaling_governor"))
            if gov:
                governors.add(gov)

        if governors:
            if governors == {"performance"}:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name="CPU Governor",
                        status=Status.PASS,
                        severity=Severity.INFO,
                        message="All CPUs set to 'performance' governor.",
                        metrics={"governors": list(governors)},
                    )
                )
            else:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name="CPU Governor",
                        status=Status.WARN,
                        severity=Severity.MAJOR,
                        message=f"CPU governor(s): {governors}. "
                        "建议 AD 系统使用 'performance' 以避免延迟抖动。",
                        metrics={"governors": list(governors)},
                        error_code="INFRA_CPU_GOV_NOT_PERF",
                    )
                )

        return results

    # ── Memory 检查 ──

    def _check_memory(self) -> List[DiagResult]:
        results = []
        meminfo = read_sysfs("/proc/meminfo")
        if not meminfo:
            return results

        mem = {}
        for line in meminfo.split("\n"):
            parts = line.split(":")
            if len(parts) == 2:
                key = parts[0].strip()
                val = parts[1].strip().split()[0]
                if val.isdigit():
                    mem[key] = int(val)  # kB

        total_gb = mem.get("MemTotal", 0) / (1024 * 1024)
        available_gb = mem.get("MemAvailable", 0) / (1024 * 1024)
        usage_pct = ((total_gb - available_gb) / total_gb * 100) if total_gb > 0 else 0

        if usage_pct > 90:
            status, severity = Status.FAIL, Severity.CRITICAL
            error_code = "INFRA_MEM_CRITICAL"
        elif usage_pct > 80:
            status, severity = Status.WARN, Severity.MAJOR
            error_code = "INFRA_MEM_HIGH"
        else:
            status, severity = Status.PASS, Severity.INFO
            error_code = ""

        results.append(
            DiagResult(
                module_name=self.name,
                item_name="Memory Usage",
                status=status,
                severity=severity,
                message=f"Memory: {usage_pct:.1f}% used ({available_gb:.1f}GB / {total_gb:.1f}GB free)",
                metrics={
                    "total_gb": round(total_gb, 1),
                    "available_gb": round(available_gb, 1),
                    "usage_pct": round(usage_pct, 1),
                },
                error_code=error_code,
            )
        )

        return results

    # ── Disk 检查 ──

    def _check_disk(self) -> List[DiagResult]:
        results = []
        storage_cfg = self.config.get("infrastructure", {}).get("storage", {})
        data_path = storage_cfg.get("data_path", "/data")
        min_free_gb = storage_cfg.get("min_free_gb", 50)

        try:
            stat = os.statvfs(data_path)
            free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
            total_gb = (stat.f_blocks * stat.f_frsize) / (1024**3)

            if free_gb < min_free_gb:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"Disk Space ({data_path})",
                        status=Status.FAIL,
                        severity=Severity.CRITICAL,
                        message=f"Only {free_gb:.1f}GB free (minimum: {min_free_gb}GB). "
                        "路测数据可能无法写入!",
                        metrics={
                            "free_gb": round(free_gb, 1),
                            "total_gb": round(total_gb, 1),
                        },
                        error_code="INFRA_DISK_LOW",
                    )
                )
            else:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"Disk Space ({data_path})",
                        status=Status.PASS,
                        severity=Severity.INFO,
                        message=f"{free_gb:.1f}GB free of {total_gb:.1f}GB",
                        metrics={
                            "free_gb": round(free_gb, 1),
                            "total_gb": round(total_gb, 1),
                        },
                    )
                )
        except OSError as e:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name=f"Disk Space ({data_path})",
                    status=Status.WARN,
                    severity=Severity.MAJOR,
                    message=f"Cannot stat {data_path}: {e}",
                    error_code="INFRA_DISK_PATH_MISSING",
                )
            )

        # SMART 状态检查
        results.extend(self._check_smart())

        return results

    def _check_smart(self) -> List[DiagResult]:
        """通过 smartctl 检查磁盘 SMART 健康状态"""
        results = []
        cmd_result = run_command(["smartctl", "--scan"], timeout=5.0)
        if not cmd_result.success:
            return results  # smartctl 未安装，跳过

        for line in cmd_result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            device = line.split()[0]  # /dev/sda, /dev/nvme0, etc.

            health_result = run_command(["smartctl", "-H", device], timeout=10.0)
            if "PASSED" in health_result.stdout:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"SMART ({device})",
                        status=Status.PASS,
                        severity=Severity.INFO,
                        message=f"SMART health: PASSED",
                        metrics={"device": device, "smart": "PASSED"},
                    )
                )
            elif "FAILED" in health_result.stdout:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"SMART ({device})",
                        status=Status.FAIL,
                        severity=Severity.CRITICAL,
                        message=f"SMART health: FAILED! 磁盘即将故障，请立即更换!",
                        metrics={"device": device, "smart": "FAILED"},
                        error_code="INFRA_DISK_SMART_FAIL",
                    )
                )

        return results

    # ── PCIe 检查 ──

    def _check_pcie(self) -> List[DiagResult]:
        """
        检测 PCIe 设备是否发生带宽降级。
        例如：GPU 应该是 x16 但协商为 x8，说明金手指接触不良或线缆问题。
        """
        results = []
        cmd_result = run_command(["lspci", "-vv"], timeout=10.0)
        if not cmd_result.success:
            return results

        # 解析 lspci 输出，查找 LnkCap vs LnkSta
        current_device = ""
        link_cap = ""
        for line in cmd_result.stdout.split("\n"):
            # 设备行
            device_match = re.match(r"^([0-9a-f]{2}:[0-9a-f]{2}\.\d)\s+(.+)", line)
            if device_match:
                current_device = f"{device_match.group(1)} {device_match.group(2)}"
                link_cap = ""
                continue

            cap_match = re.search(r"LnkCap:.*Width\s+x(\d+)", line)
            if cap_match:
                link_cap = cap_match.group(1)

            sta_match = re.search(r"LnkSta:.*Width\s+x(\d+)", line)
            if sta_match and link_cap:
                link_sta = sta_match.group(1)
                cap_width = int(link_cap)
                sta_width = int(link_sta)

                # 只报告降级的高带宽设备 (x4 以上)
                if cap_width >= 4 and sta_width < cap_width:
                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name=f"PCIe Width ({current_device[:50]})",
                            status=Status.WARN,
                            severity=Severity.MAJOR,
                            message=f"PCIe degraded: capable x{cap_width}, "
                            f"negotiated x{sta_width}. 检查物理连接。",
                            metrics={
                                "device": current_device,
                                "capable_width": cap_width,
                                "actual_width": sta_width,
                            },
                            error_code="INFRA_PCIE_DEGRADED",
                        )
                    )
                link_cap = ""

        if not any(r.item_name.startswith("PCIe") for r in results):
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="PCIe Link Status",
                    status=Status.PASS,
                    severity=Severity.INFO,
                    message="No PCIe bandwidth degradation detected.",
                )
            )

        return results
