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
PTP (Precision Time Protocol) diagnostics module

Features:
    - PTP interface and clock device discovery
    - ptp4l and phc2sys service liveness checks
    - PTP offset and Grandmaster identity validation
    - Clock jump detection
"""

import glob
import logging
import re
from typing import List

from whl_diag.execution.interface import (
    IDiagnosticProbe,
    DiagResult,
    Status,
    Severity,
    Phase,
    ProbeType,
)
from whl_diag.utils.shell_runner import run_command, read_sysfs

logger = logging.getLogger(__name__)


class PTPProbe(IDiagnosticProbe):
    depends_on = ["Network Link Probe"]

    @property
    def name(self) -> str:
        return "PTP Sync Probe"

    @property

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
                    raw_output=run_command(["ip", "a"]).stdout,
                    sys_logs=self.fetch_system_logs("ptp"),
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
                    message=f"Found PTP devices: {', '.join(ptp_devices)}",
                    phase=Phase.DISCOVERY,
                    probe_type=ProbeType.LIVENESS,
                    metrics={"ptp_devices": ptp_devices},
                )
            )

        return results

    def liveness(self) -> List[DiagResult]:
        results = []

        # Check ptp4l
        cmd_result = run_command(["pgrep", "-f", "ptp4l"], timeout=3.0)
        if cmd_result.success and cmd_result.stdout.strip():
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="ptp4l Service",
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
                    item_name="ptp4l Service",
                    status=Status.WARN,
                    severity=Severity.MAJOR,
                    message="ptp4l service not detected.",
                    phase=Phase.VALIDATION,
                    probe_type=ProbeType.LIVENESS,
                    error_code="SYNC_PTP_SERVICE_MISSING",
                )
            )

        # Check phc2sys
        cmd_result = run_command(["pgrep", "-f", "phc2sys"], timeout=3.0)
        if cmd_result.success and cmd_result.stdout.strip():
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="phc2sys Service",
                    status=Status.PASS,
                    severity=Severity.INFO,
                    message="phc2sys service running.",
                    phase=Phase.VALIDATION,
                    probe_type=ProbeType.LIVENESS,
                )
            )
        else:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="phc2sys Service",
                    status=Status.WARN,
                    severity=Severity.MAJOR,
                    message="phc2sys service not detected. System clock may not be synced to PTP hardware clock.",
                    phase=Phase.VALIDATION,
                    probe_type=ProbeType.LIVENESS,
                    error_code="SYNC_PHC2SYS_MISSING",
                )
            )

        return results

    def readiness(self) -> List[DiagResult]:
        results = []
        ptp_cfg = self.config.get("time_sync", {}).get("ptp", {})
        threshold_ns = self.config.get("thresholds", {}).get("ptp_offset_ns", 1000) # Industry standard is usually < 1us (1000ns)
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
        state_match = re.search(r"portState\s+(\w+)", output)

        # Check Port State
        if state_match:
            state = state_match.group(1)
            if state not in ("SLAVE", "MASTER"):
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name="PTP Port State",
                        status=Status.WARN,
                        severity=Severity.MAJOR,
                        message=f"PTP port state is {state} (expected SLAVE or MASTER)",
                        phase=Phase.VALIDATION,
                        probe_type=ProbeType.READINESS,
                        error_code="SYNC_PTP_STATE_INVALID",
                    )
                )
            else:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name="PTP Port State",
                        status=Status.PASS,
                        severity=Severity.INFO,
                        message=f"PTP port state is {state}",
                        phase=Phase.VALIDATION,
                        probe_type=ProbeType.READINESS,
                        metrics={"port_state": state},
                    )
                )

        # Check Offset
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
                    raw_output=cmd_result.stdout if status != Status.PASS else "",
                    sys_logs=self.fetch_system_logs("ptp4l", 30) if status != Status.PASS else "",
                )
            )
        else:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="PTP Offset",
                    status=Status.WARN,
                    severity=Severity.MAJOR,
                    message="Could not parse offsetFromMaster from pmc output.",
                    phase=Phase.VALIDATION,
                    probe_type=ProbeType.READINESS,
                    error_code="SYNC_PTP_PARSE_ERROR",
                )
            )

        # Check Grandmaster
        if gm_match:
            actual_gm = gm_match.group(1)
            if expected_gm and actual_gm.lower() != expected_gm.lower():
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name="PTP Grandmaster",
                        status=Status.WARN,
                        severity=Severity.MAJOR,
                        message=f"GM Identity mismatch: {actual_gm} (expected {expected_gm})",
                        phase=Phase.VALIDATION,
                        probe_type=ProbeType.READINESS,
                        metrics={"gm_identity": actual_gm},
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
                        message=f"GM Identity: {actual_gm}",
                        phase=Phase.VALIDATION,
                        probe_type=ProbeType.READINESS,
                        metrics={"gm_identity": actual_gm},
                    )
                )

        return results
