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
Network and time synchronization diagnostics module

Features:
    - Interface discovery
    - Link liveness checks
    - Speed/MTU/error-counter readiness checks
    - PTP offset readiness checks
"""

import glob
import logging
import re
from typing import List, Dict

from src.execution.interface import (
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
                        raw_output=run_command(["ip", "a"]).stdout,
                        sys_logs=self.fetch_system_logs(iface, 20),
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
                        raw_output=run_command(["ip", "link", "show", iface]).stdout,
                        sys_logs=self.fetch_system_logs(iface, 20),
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
                        raw_output=run_command(["ethtool", iface]).stdout,
                        sys_logs=self.fetch_system_logs(iface, 30),
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


