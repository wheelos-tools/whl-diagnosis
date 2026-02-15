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
网络与时间同步诊断模块

功能:
  - 网络接口发现 (Discovery)
  - 链路存活 (Liveness)
  - 速率/MTU/错误计数 (Readiness)
  - PTP 同步偏移检测 (Readiness)
"""

import glob
import logging
import re
from typing import List, Dict

from src.core.interface import (
    IDiagnosticProbe,
    DiagResult,
    Status,
    Severity,
    Phase,
    ProbeType,
)
from src.utils.shell_runner import run_command, read_sysfs

logger = logging.getLogger(__name__)


class NetworkLinkProbe(IDiagnosticProbe):

    @property
    def name(self) -> str:
        return "Network Link Probe"

    @property
    def timeout_seconds(self) -> float:
        return 8.0

    def discovery(self) -> List[DiagResult]:
        results = []
        net_cfg = self.config.get("network", {})
        interfaces = net_cfg.get("interfaces", [])

        if not interfaces:
            return [
                DiagResult(
                    module_name=self.name,
                    item_name="Network Configuration",
                    status=Status.SKIP,
                    severity=Severity.INFO,
                    message="No network interfaces configured, skipping.",
                    phase=Phase.DISCOVERY,
                    probe_type=ProbeType.LIVENESS,
                )
            ]

        for iface_cfg in interfaces:
            iface = iface_cfg["name"]
            role = iface_cfg.get("role", "data")
            operstate = read_sysfs(f"/sys/class/net/{iface}/operstate")

            if operstate is None:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"{iface} Presence",
                        status=Status.FAIL,
                        severity=Severity.CRITICAL,
                        message=f"Interface {iface} not found in system.",
                        phase=Phase.DISCOVERY,
                        probe_type=ProbeType.LIVENESS,
                        error_code="INFRA_NET_IFACE_MISSING",
                    )
                )
            else:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"{iface} Presence",
                        status=Status.PASS,
                        severity=Severity.INFO,
                        message=f"Interface {iface} present (role: {role}).",
                        phase=Phase.DISCOVERY,
                        probe_type=ProbeType.LIVENESS,
                        metrics={"role": role},
                    )
                )

        return results

    def liveness(self) -> List[DiagResult]:
        results = []
        net_cfg = self.config.get("network", {})
        interfaces = net_cfg.get("interfaces", [])

        for iface_cfg in interfaces:
            iface = iface_cfg["name"]
            operstate = read_sysfs(f"/sys/class/net/{iface}/operstate")

            if operstate is None:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"{iface} Link State",
                        status=Status.FAIL,
                        severity=Severity.CRITICAL,
                        message=f"Interface {iface} not found.",
                        phase=Phase.VALIDATION,
                        probe_type=ProbeType.LIVENESS,
                        error_code="INFRA_NET_IFACE_MISSING",
                    )
                )
            elif operstate == "up":
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"{iface} Link State",
                        status=Status.PASS,
                        severity=Severity.INFO,
                        message=f"Link is UP on {iface}.",
                        phase=Phase.VALIDATION,
                        probe_type=ProbeType.LIVENESS,
                        metrics={"operstate": operstate},
                    )
                )
            else:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"{iface} Link State",
                        status=Status.FAIL,
                        severity=Severity.CRITICAL,
                        message=f"Link is DOWN on {iface} (state: {operstate}).",
                        phase=Phase.VALIDATION,
                        probe_type=ProbeType.LIVENESS,
                        metrics={"operstate": operstate},
                        error_code="INFRA_NET_LINK_DOWN",
                    )
                )

        return results

    def readiness(self) -> List[DiagResult]:
        results = []
        net_cfg = self.config.get("network", {})
        interfaces = net_cfg.get("interfaces", [])

        for iface_cfg in interfaces:
            iface = iface_cfg["name"]
            expected_speed = iface_cfg.get("expected_speed", 1000)
            expected_mtu = iface_cfg.get("expected_mtu", 1500)

            speed_raw = read_sysfs(f"/sys/class/net/{iface}/speed")
            mtu_raw = read_sysfs(f"/sys/class/net/{iface}/mtu")

            actual_speed = int(speed_raw) if speed_raw and speed_raw.isdigit() else -1
            actual_mtu = int(mtu_raw) if mtu_raw and mtu_raw.isdigit() else -1

            if actual_speed > 0:
                if actual_speed < expected_speed:
                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name=f"{iface} Link Speed",
                            status=Status.WARN,
                            severity=Severity.MAJOR,
                            message=f"Speed {actual_speed} Mbps (expected {expected_speed} Mbps)",
                            phase=Phase.VALIDATION,
                            probe_type=ProbeType.READINESS,
                            metrics={"speed_mbps": actual_speed},
                            error_code="INFRA_NET_SPEED_LOW",
                        )
                    )
                else:
                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name=f"{iface} Link Speed",
                            status=Status.PASS,
                            severity=Severity.INFO,
                            message=f"Speed {actual_speed} Mbps OK",
                            phase=Phase.VALIDATION,
                            probe_type=ProbeType.READINESS,
                            metrics={"speed_mbps": actual_speed},
                        )
                    )
            else:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"{iface} Link Speed",
                        status=Status.WARN,
                        severity=Severity.MINOR,
                        message="Unable to read link speed (device may not report).",
                        phase=Phase.VALIDATION,
                        probe_type=ProbeType.READINESS,
                        error_code="INFRA_NET_SPEED_UNKNOWN",
                    )
                )

            if actual_mtu > 0:
                if actual_mtu != expected_mtu:
                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name=f"{iface} MTU",
                            status=Status.WARN,
                            severity=Severity.MAJOR,
                            message=f"MTU {actual_mtu} (expected {expected_mtu})",
                            phase=Phase.VALIDATION,
                            probe_type=ProbeType.READINESS,
                            metrics={"mtu": actual_mtu},
                            error_code="INFRA_NET_MTU_MISMATCH",
                        )
                    )
                else:
                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name=f"{iface} MTU",
                            status=Status.PASS,
                            severity=Severity.INFO,
                            message=f"MTU {actual_mtu} OK",
                            phase=Phase.VALIDATION,
                            probe_type=ProbeType.READINESS,
                            metrics={"mtu": actual_mtu},
                        )
                    )

            rx_errors = read_sysfs(f"/sys/class/net/{iface}/statistics/rx_errors")
            tx_errors = read_sysfs(f"/sys/class/net/{iface}/statistics/tx_errors")
            rx_err = int(rx_errors) if rx_errors and rx_errors.isdigit() else 0
            tx_err = int(tx_errors) if tx_errors and tx_errors.isdigit() else 0

            if rx_err > 0 or tx_err > 0:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"{iface} Error Counters",
                        status=Status.WARN,
                        severity=Severity.MAJOR,
                        message=f"RX errors: {rx_err}, TX errors: {tx_err}",
                        phase=Phase.VALIDATION,
                        probe_type=ProbeType.READINESS,
                        metrics={"rx_errors": rx_err, "tx_errors": tx_err},
                        error_code="INFRA_NET_ERROR_COUNTERS",
                    )
                )

        return results


class PTPProbe(IDiagnosticProbe):

    @property
    def name(self) -> str:
        return "PTP Sync Probe"

    @property
    def dependencies(self) -> List[str]:
        return ["Network Link Probe"]

    @property
    def timeout_seconds(self) -> float:
        return 12.0

    def discovery(self) -> List[DiagResult]:
        results = []
        ptp_cfg = self.config.get("time_sync", {}).get("ptp", {})
        iface = ptp_cfg.get("interface", "eth0")
        operstate = read_sysfs(f"/sys/class/net/{iface}/operstate")
        ptp_devices = glob.glob("/sys/class/ptp/ptp*")

        if operstate is None:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="PTP Interface",
                    status=Status.FAIL,
                    severity=Severity.CRITICAL,
                    message=f"PTP interface {iface} not found.",
                    phase=Phase.DISCOVERY,
                    probe_type=ProbeType.LIVENESS,
                    error_code="SYNC_PTP_IFACE_MISSING",
                )
            )
        else:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="PTP Interface",
                    status=Status.PASS,
                    severity=Severity.INFO,
                    message=f"PTP interface {iface} present.",
                    phase=Phase.DISCOVERY,
                    probe_type=ProbeType.LIVENESS,
                    metrics={"interface": iface},
                )
            )

        if not ptp_devices:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="PTP Clock Device",
                    status=Status.WARN,
                    severity=Severity.MAJOR,
                    message="No /sys/class/ptp/ptp* device found.",
                    phase=Phase.DISCOVERY,
                    probe_type=ProbeType.LIVENESS,
                    error_code="SYNC_PTP_CLOCK_MISSING",
                )
            )
        else:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="PTP Clock Device",
                    status=Status.PASS,
                    severity=Severity.INFO,
                    message=f"PTP clock device(s) detected: {len(ptp_devices)}",
                    phase=Phase.DISCOVERY,
                    probe_type=ProbeType.LIVENESS,
                    metrics={"ptp_device_count": len(ptp_devices)},
                )
            )

        return results

    def liveness(self) -> List[DiagResult]:
        results = []
        cmd_result = run_command(["pgrep", "-f", "ptp4l"], timeout=3.0)
        if cmd_result.success and cmd_result.stdout.strip():
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="PTP Service",
                    status=Status.PASS,
                    severity=Severity.INFO,
                    message="ptp4l service running.",
                    phase=Phase.VALIDATION,
                    probe_type=ProbeType.LIVENESS,
                )
            )
        else:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="PTP Service",
                    status=Status.WARN,
                    severity=Severity.MAJOR,
                    message="ptp4l service not detected.",
                    phase=Phase.VALIDATION,
                    probe_type=ProbeType.LIVENESS,
                    error_code="SYNC_PTP_SERVICE_MISSING",
                )
            )
        return results

    def readiness(self) -> List[DiagResult]:
        results = []
        ptp_cfg = self.config.get("time_sync", {}).get("ptp", {})
        threshold_ns = self.config.get("thresholds", {}).get("ptp_offset_ns", 500)
        expected_gm = ptp_cfg.get("expected_gm_identity", "")

        cmd_result = run_command(
            ["pmc", "-u", "-b", "0", "GET TIME_STATUS_NP"], timeout=6.0
        )

        if not cmd_result.success:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="PTP Offset",
                    status=Status.WARN,
                    severity=Severity.MAJOR,
                    message=f"pmc not available or failed: {cmd_result.stderr}",
                    phase=Phase.VALIDATION,
                    probe_type=ProbeType.READINESS,
                    error_code="SYNC_PTP_TOOL_MISSING",
                )
            )
            return results

        output = cmd_result.stdout
        offset_match = re.search(r"offsetFromMaster\s+(-?\d+)", output)
        gm_match = re.search(r"gmIdentity\s+([0-9a-fA-F:]+)", output)

        if offset_match:
            offset_ns = int(offset_match.group(1))
            abs_offset = abs(offset_ns)
            if abs_offset > threshold_ns * 5:
                status, severity = Status.FAIL, Severity.CRITICAL
                error_code = "SYNC_PTP_OFFSET_HIGH"
            elif abs_offset > threshold_ns:
                status, severity = Status.WARN, Severity.MAJOR
                error_code = "SYNC_PTP_OFFSET_HIGH"
            else:
                status, severity = Status.PASS, Severity.INFO
                error_code = ""

            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="PTP Offset",
                    status=status,
                    severity=severity,
                    message=f"Offset {offset_ns} ns (threshold {threshold_ns} ns)",
                    phase=Phase.VALIDATION,
                    probe_type=ProbeType.READINESS,
                    metrics={"offset_ns": offset_ns},
                    error_code=error_code,
                )
            )
        else:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="PTP Offset",
                    status=Status.WARN,
                    severity=Severity.MAJOR,
                    message="Unable to parse offsetFromMaster from pmc output.",
                    phase=Phase.VALIDATION,
                    probe_type=ProbeType.READINESS,
                    error_code="SYNC_PTP_OFFSET_UNKNOWN",
                )
            )

        if expected_gm and gm_match:
            gm_identity = gm_match.group(1)
            if gm_identity.lower() != expected_gm.lower():
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name="PTP Grandmaster",
                        status=Status.WARN,
                        severity=Severity.MAJOR,
                        message=f"GM identity mismatch: {gm_identity} (expected {expected_gm})",
                        phase=Phase.VALIDATION,
                        probe_type=ProbeType.READINESS,
                        error_code="SYNC_PTP_GM_MISMATCH",
                    )
                )
            else:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name="PTP Grandmaster",
                        status=Status.PASS,
                        severity=Severity.INFO,
                        message=f"GM identity OK: {gm_identity}",
                        phase=Phase.VALIDATION,
                        probe_type=ProbeType.READINESS,
                    )
                )

        return results
