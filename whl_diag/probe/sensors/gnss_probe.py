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
GNSS / PPS / NMEA diagnostics module

Features:
    - PPS device presence and pulse stability
    - NMEA serial data validity
    - GNSS fix status (fix type)
"""

import os
import re
import time
import logging
from typing import List

from whl_diag.execution.interface import IDiagnosticProbe, DiagResult, Status, Severity
from whl_diag.utils.shell_runner import run_command

logger = logging.getLogger(__name__)


class GNSSProbe(IDiagnosticProbe):

    @property
    def name(self) -> str:
        return "GNSS/PPS Probe"

    @property
    def timeout_seconds(self) -> float:
        return 15.0

    def run_check(self) -> List[DiagResult]:
        results = []
        gnss_cfg = self.config.get("time_sync", {}).get("gnss", {})

        pps_device = gnss_cfg.get("pps_device", "/dev/pps0")
        nmea_device = gnss_cfg.get("nmea_device", "/dev/ttyUSB0")
        nmea_baud = gnss_cfg.get("nmea_baud", 115200)

        # ── 1. PPS device check ──
        results.extend(self._check_pps(pps_device))

        # ── 2. NMEA serial check ──
        results.extend(self._check_nmea(nmea_device, nmea_baud))

        return results

    def _check_pps(self, pps_device: str) -> List[DiagResult]:
        results = []

        if not os.path.exists(pps_device):
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="PPS Device",
                    status=Status.FAIL,
                    severity=Severity.CRITICAL,
                    message=f"PPS device {pps_device} not found!",
                    error_code="SYNC_PPS_DEVICE_MISSING",
                )
            )
            return results

        # Sample PPS pulses via ppstest (collect a few pulses only)
        cmd_result = run_command(
            ["timeout", "5", "ppstest", "-a", pps_device],
            timeout=8.0,
        )

        if not cmd_result.success and "source" not in cmd_result.stdout.lower():
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="PPS Signal",
                    status=Status.WARN,
                    severity=Severity.MAJOR,
                    message=f"ppstest failed or not installed: {cmd_result.stderr}",
                    error_code="SYNC_PPS_TEST_FAIL",
                )
            )
            return results

        # Parse ppstest output and extract pulse timestamps
        timestamps = []
        for match in re.finditer(
            r"assert\s+(\d+)\.(\d+),\s+sequence:\s+(\d+)", cmd_result.stdout
        ):
            sec, nsec, seq = (
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            )
            timestamps.append(sec + nsec * 1e-9)

        if len(timestamps) >= 2:
            # Check PPS interval stability (should be near 1.0s)
            intervals = [
                timestamps[i + 1] - timestamps[i] for i in range(len(timestamps) - 1)
            ]
            avg_interval = sum(intervals) / len(intervals)
            jitter_us = max(abs(i - 1.0) * 1e6 for i in intervals)

            if jitter_us < 100:  # < 100 μs jitter
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name="PPS Stability",
                        status=Status.PASS,
                        severity=Severity.INFO,
                        message=f"PPS jitter: {jitter_us:.1f}μs (interval: {avg_interval:.6f}s)",
                        metrics={
                            "jitter_us": round(jitter_us, 1),
                            "avg_interval_s": round(avg_interval, 6),
                            "samples": len(timestamps),
                        },
                    )
                )
            else:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name="PPS Stability",
                        status=Status.WARN,
                        severity=Severity.MAJOR,
                        message=f"PPS jitter high: {jitter_us:.1f}μs",
                        metrics={"jitter_us": round(jitter_us, 1)},
                        error_code="SYNC_PPS_JITTER_HIGH",
                    )
                )
        else:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="PPS Signal",
                    status=Status.FAIL,
                    severity=Severity.CRITICAL,
                    message="No PPS pulses received. Check GNSS antenna sky visibility.",
                    error_code="SYNC_PPS_NO_SIGNAL",
                )
            )

        return results

    def _check_nmea(self, nmea_device: str, baud: int) -> List[DiagResult]:
        results = []

        if not os.path.exists(nmea_device):
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="NMEA Device",
                    status=Status.FAIL,
                    severity=Severity.CRITICAL,
                    message=f"NMEA serial device {nmea_device} not found!",
                    error_code="SYNC_NMEA_DEVICE_MISSING",
                )
            )
            return results

        results.append(
            DiagResult(
                module_name=self.name,
                item_name="NMEA Device",
                status=Status.PASS,
                severity=Severity.INFO,
                message=f"NMEA device {nmea_device} exists.",
            )
        )

        # Read NMEA stream and parse GGA sentences
        try:
            import serial

            ser = serial.Serial(nmea_device, baud, timeout=3)
            lines = []
            start = time.monotonic()
            while time.monotonic() - start < 3.0 and len(lines) < 20:
                line = ser.readline().decode("ascii", errors="ignore").strip()
                if line:
                    lines.append(line)
            ser.close()

            # Find first GGA sentence
            gga_line = None
            for line in lines:
                if "$GPGGA" in line or "$GNGGA" in line:
                    gga_line = line
                    break

            if gga_line:
                parts = gga_line.split(",")
                if len(parts) >= 7:
                    fix_quality = int(parts[6]) if parts[6].isdigit() else 0
                    num_sats = int(parts[7]) if parts[7].isdigit() else 0

                    fix_names = {
                        0: "No Fix",
                        1: "GPS Fix",
                        2: "DGPS",
                        4: "RTK Fixed",
                        5: "RTK Float",
                    }
                    fix_name = fix_names.get(fix_quality, f"Unknown({fix_quality})")

                    if fix_quality >= 4:
                        status = Status.PASS
                        severity = Severity.INFO
                        error_code = ""
                    elif fix_quality >= 1:
                        status = Status.WARN
                        severity = Severity.MAJOR
                        error_code = "SYNC_GNSS_NO_RTK"
                    else:
                        status = Status.FAIL
                        severity = Severity.CRITICAL
                        error_code = "SYNC_GNSS_NO_FIX"

                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name="GNSS Fix Status",
                            status=status,
                            severity=severity,
                            message=f"Fix: {fix_name}, Satellites: {num_sats}",
                            metrics={
                                "fix_quality": fix_quality,
                                "fix_name": fix_name,
                                "num_satellites": num_sats,
                            },
                            error_code=error_code,
                        )
                    )
                else:
                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name="GNSS Fix Status",
                            status=Status.WARN,
                            severity=Severity.MAJOR,
                            message=f"Malformed GGA sentence: {gga_line}",
                            error_code="SYNC_NMEA_PARSE_ERROR",
                        )
                    )
            else:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name="GNSS Fix Status",
                        status=Status.WARN,
                        severity=Severity.MAJOR,
                        message="No GGA sentence found in NMEA stream.",
                        error_code="SYNC_NMEA_NO_GGA",
                    )
                )

        except ImportError:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="NMEA Data",
                    status=Status.SKIP,
                    severity=Severity.INFO,
                    message="pyserial not installed, skipping NMEA check.",
                )
            )
        except Exception as e:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="NMEA Data",
                    status=Status.ERROR,
                    severity=Severity.MAJOR,
                    message=f"Failed to read NMEA: {e}",
                    error_code="SYNC_NMEA_READ_ERROR",
                )
            )

        return results
