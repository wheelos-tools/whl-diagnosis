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
System infrastructure diagnostic module

Features:
  - CPU core count / temperature / frequency throttle detection
  - Memory usage
  - Disk free space and SMART status
  - PCIe bandwidth negotiation detection (e.g. x16 downgraded to x8)
  - Kernel log anomaly detection (dmesg: panic / OOM / hardware errors)
  - System log service failure detection (journalctl)
  - Boot time analysis (systemd-analyze)
  - Crash dump detection (kdump / vmcore)
"""

import os
import re
import glob
import logging
from typing import List

from whl_diag.execution.interface import IDiagnosticProbe, DiagResult, Status, Severity
from whl_diag.utils.shell_runner import run_command, read_sysfs

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
        results.extend(self._check_dmesg())
        results.extend(self._check_journal())
        results.extend(self._check_boot())
        results.extend(self._check_kernel_crash())
        return results

    # ── CPU checks ──

    def _check_cpu(self) -> List[DiagResult]:
        results = []

        # CPU core count
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
                    "Check if cores are isolated by isolcpus or brought offline.",
                    metrics={"cpu_cores": actual_cores},
                    error_code="INFRA_CPU_CORE_MISMATCH",
                )
            )

        # CPU temperature (via hwmon)
        results.extend(self._check_cpu_temperature())

        # CPU frequency throttle check
        results.extend(self._check_cpu_frequency())

        return results

    def _check_cpu_temperature(self) -> List[DiagResult]:
        results = []
        threshold = self.config.get("thresholds", {}).get("cpu_temp_c", 90)

        # Scan hwmon directories for CPU temperature sensors
        hwmon_dirs = glob.glob("/sys/class/hwmon/hwmon*/")
        for hwmon in hwmon_dirs:
            name_file = os.path.join(hwmon, "name")
            name = read_sysfs(name_file)
            if name and name in ("coretemp", "k10temp", "zenpower"):
                # Found CPU temperature sensor
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
        """Detect CPU throttling (governor is not 'performance')."""
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
                        "Recommend setting 'performance' governor to avoid latency jitter.",
                        metrics={"governors": list(governors)},
                        error_code="INFRA_CPU_GOV_NOT_PERF",
                    )
                )

        return results

    # ── Memory checks ──

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

    # ── Disk checks ──

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
                        "Road-test data may fail to write!",
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

        # SMART health check
        results.extend(self._check_smart())

        return results

    def _check_smart(self) -> List[DiagResult]:
        """Check disk SMART health status via smartctl."""
        results = []
        cmd_result = run_command(["smartctl", "--scan"], timeout=5.0)
        if not cmd_result.success:
            return results  # smartctl not installed, skip

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
                        message="SMART health: FAILED! Disk is failing, replace immediately!",
                        metrics={"device": device, "smart": "FAILED"},
                        error_code="INFRA_DISK_SMART_FAIL",
                    )
                )

        return results

    # ── PCIe checks ──

    def _check_pcie(self) -> List[DiagResult]:
        """
        Detect PCIe bandwidth downgrade.
        E.g. GPU capable of x16 but negotiated x8, indicating poor gold-finger
        contact or a cable issue.
        """
        results = []
        cmd_result = run_command(["lspci", "-vv"], timeout=10.0)
        if not cmd_result.success:
            return results

        # Parse lspci output to find LnkCap vs LnkSta
        current_device = ""
        link_cap = ""
        for line in cmd_result.stdout.split("\n"):
            # Device line
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

                # Only report degraded high-bandwidth devices (x4 and above)
                if cap_width >= 4 and sta_width < cap_width:
                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name=f"PCIe Width ({current_device[:50]})",
                            status=Status.WARN,
                            severity=Severity.MAJOR,
                            message=f"PCIe degraded: capable x{cap_width}, "
                            f"negotiated x{sta_width}. Check physical connection.",
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

    # ── dmesg kernel log anomaly detection ──

    # Patterns that indicate critical kernel-level events
    _DMESG_PATTERNS = [
        (
            re.compile(
                r"(kernel panic|Oops:|BUG:|general protection fault|machine check exception)",
                re.IGNORECASE,
            ),
            "Kernel Panic / BUG",
            Status.FAIL,
            Severity.CRITICAL,
            "INFRA_KERNEL_PANIC",
        ),
        (
            re.compile(r"Out of memory|oom.kill|oom_kill_process", re.IGNORECASE),
            "OOM Kill",
            Status.FAIL,
            Severity.CRITICAL,
            "INFRA_OOM_KILL",
        ),
        (
            re.compile(
                r"(hardware error|uncorrected error|DRAM ECC|DIMM|DRAM failure|MCE)",
                re.IGNORECASE,
            ),
            "Hardware Error",
            Status.FAIL,
            Severity.CRITICAL,
            "INFRA_HW_ERROR",
        ),
        (
            re.compile(
                r"(ACPI Error|firmware bug|BIOS.*error|UEFI.*error)", re.IGNORECASE
            ),
            "Firmware / ACPI Error",
            Status.WARN,
            Severity.MAJOR,
            "INFRA_FIRMWARE_ERROR",
        ),
        (
            re.compile(r"(I/O error|blk_update_request|buffer I/O error)", re.IGNORECASE),
            "Disk I/O Error",
            Status.WARN,
            Severity.MAJOR,
            "INFRA_DISK_IO_ERROR",
        ),
    ]

    def _check_dmesg(self) -> List[DiagResult]:
        """Parse dmesg kernel log to detect critical anomalies: panic, OOM, hardware errors."""
        results = []
        lines_limit = self.config.get("thresholds", {}).get("dmesg_lines", 2000)
        cmd_result = run_command(
            ["dmesg", "--level=err,crit,alert,emerg", "--notime"],
            timeout=10.0,
        )

        if not cmd_result.success:
            # dmesg may require elevated privileges; degrade gracefully
            return results

        output = cmd_result.stdout
        lines = output.splitlines()[-lines_limit:]

        matched: dict = {}  # pattern label → first matching line
        for line in lines:
            for pattern, label, status, severity, error_code in self._DMESG_PATTERNS:
                if label not in matched and pattern.search(line):
                    matched[label] = (line.strip(), status, severity, error_code)

        for label, (sample, status, severity, error_code) in matched.items():
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name=f"dmesg: {label}",
                    status=status,
                    severity=severity,
                    message=f"Detected in dmesg: {sample[:200]}",
                    metrics={"sample": sample[:200]},
                    error_code=error_code,
                )
            )

        if not matched:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="dmesg Anomalies",
                    status=Status.PASS,
                    severity=Severity.INFO,
                    message="No critical kernel anomalies found in dmesg.",
                )
            )

        return results

    # ── journalctl service failure detection ──

    def _check_journal(self) -> List[DiagResult]:
        """Detect recent systemd service failures via journalctl."""
        results = []
        since = self.config.get("thresholds", {}).get(
            "journal_since", "24 hours ago"
        )
        cmd_result = run_command(
            [
                "journalctl",
                "--priority=err",
                f"--since={since}",
                "--no-pager",
                "--quiet",
            ],
            timeout=15.0,
        )

        if not cmd_result.success:
            # journalctl not available (e.g., non-systemd system)
            return results

        lines = [l for l in cmd_result.stdout.splitlines() if l.strip()]
        failed_services: set = set()
        fail_re = re.compile(
            r"([\w@\-\.]+\.service).*(failed|start request repeated too quickly)",
            re.IGNORECASE,
        )
        for line in lines:
            m = fail_re.search(line)
            if m:
                failed_services.add(m.group(1))

        if failed_services:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="Systemd Service Failures",
                    status=Status.WARN,
                    severity=Severity.MAJOR,
                    message=f"Failed services detected: {', '.join(sorted(failed_services))}",
                    metrics={"failed_services": sorted(failed_services)},
                    error_code="INFRA_SERVICE_FAILED",
                )
            )
        else:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="Systemd Service Failures",
                    status=Status.PASS,
                    severity=Severity.INFO,
                    message=f"No service failures found in journal (since: {since}).",
                )
            )

        return results

    # ── Boot time analysis ──

    def _check_boot(self) -> List[DiagResult]:
        """Detect boot time bottlenecks using systemd-analyze."""
        results = []
        boot_warn_s = self.config.get("thresholds", {}).get("boot_time_warn_s", 60)
        boot_fail_s = self.config.get("thresholds", {}).get("boot_time_fail_s", 120)

        cmd_result = run_command(["systemd-analyze"], timeout=10.0)
        if not cmd_result.success:
            return results

        # Parse total boot time, e.g.:
        # "Startup finished in 3.891s (kernel) + 12.345s (userspace) = 16.236s"
        time_match = re.search(
            r"Startup finished in.*=\s*([\d.]+)(min\s+)?([\d.]+)?s", cmd_result.stdout
        )
        total_s = None
        if time_match:
            # May be "X min Y.Zs" or just "X.Ys"
            if time_match.group(2):  # minutes present
                total_s = float(time_match.group(1)) * 60 + float(
                    time_match.group(3) or 0
                )
            else:
                total_s = float(time_match.group(1))

        if total_s is None:
            # Try simpler pattern for kernel+userspace total
            simple = re.search(r"=\s*([\d.]+)s", cmd_result.stdout)
            if simple:
                total_s = float(simple.group(1))

        if total_s is not None:
            if total_s >= boot_fail_s:
                status, severity, error_code = (
                    Status.FAIL,
                    Severity.CRITICAL,
                    "INFRA_BOOT_SLOW",
                )
            elif total_s >= boot_warn_s:
                status, severity, error_code = (
                    Status.WARN,
                    Severity.MAJOR,
                    "INFRA_BOOT_SLOW",
                )
            else:
                status, severity, error_code = Status.PASS, Severity.INFO, ""

            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="Boot Time",
                    status=status,
                    severity=severity,
                    message=f"System boot completed in {total_s:.1f}s "
                    f"(warn: {boot_warn_s}s, fail: {boot_fail_s}s)",
                    metrics={"boot_time_s": round(total_s, 1)},
                    error_code=error_code,
                )
            )

        # Report the top slow units (blame)
        blame_result = run_command(
            ["systemd-analyze", "blame", "--no-pager"], timeout=10.0
        )
        if blame_result.success:
            slow_units = []
            for line in blame_result.stdout.splitlines()[:5]:
                line = line.strip()
                if line:
                    slow_units.append(line)
            if slow_units:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name="Boot Slowest Units",
                        status=Status.PASS,
                        severity=Severity.INFO,
                        message="Top 5 slowest boot units: " + "; ".join(slow_units),
                        metrics={"slow_units": slow_units},
                    )
                )

        return results

    # ── Crash dump detection ──

    _VMCORE_DIRS = [
        "/var/crash",
        "/var/lib/systemd/coredump",
        "/var/kdump",
    ]

    def _check_kernel_crash(self) -> List[DiagResult]:
        """Check for unprocessed kernel crash dumps (kdump / systemd-coredump)."""
        results = []
        found_dumps: List[str] = []

        for crash_dir in self._VMCORE_DIRS:
            if not os.path.isdir(crash_dir):
                continue
            try:
                for entry in os.scandir(crash_dir):
                    # Count both vmcore files and crash subdirectories
                    # (kdump creates per-crash directories; systemd-coredump stores individual files)
                    if entry.is_file() or entry.is_dir(follow_symlinks=False):
                        found_dumps.append(entry.path)
            except PermissionError:
                logger.warning(f"Permission denied reading {crash_dir}")

        if found_dumps:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="Kernel Crash Dumps",
                    status=Status.WARN,
                    severity=Severity.MAJOR,
                    message=f"{len(found_dumps)} crash dump(s) found: "
                    + ", ".join(found_dumps[:5]),
                    metrics={"crash_dump_count": len(found_dumps)},
                    error_code="INFRA_CRASH_DUMP_FOUND",
                )
            )
        else:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="Kernel Crash Dumps",
                    status=Status.PASS,
                    severity=Severity.INFO,
                    message="No kernel crash dumps found.",
                )
            )

        return results
