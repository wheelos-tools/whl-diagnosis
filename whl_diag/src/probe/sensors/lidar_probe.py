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
LiDAR diagnostics module
Evaluates LiDAR health using UDP packet rate and integrity
"""

import socket
import time
from typing import List

from whl_diag.execution.interface import IDiagnosticProbe, DiagResult, Status, Severity


class LiDARProbe(IDiagnosticProbe):
    depends_on = ["Network Link Probe", "PTP Sync Probe"]

    @property
    def name(self) -> str:
        return "LiDAR Packet Probe"

    @property
    def timeout_seconds(self) -> float:
        return 30.0  # LiDAR requires multi-frame sampling

    def run_check(self) -> List[DiagResult]:
        results = []
        lidars = self.config.get("lidars", [])

        for lidar_cfg in lidars:
            lidar_name = lidar_cfg["name"]
            port = lidar_cfg["port"]
            expected_pps = lidar_cfg.get(
                "expected_packets_per_second", 754
            )  # Typical value for Velodyne VLP-16
            sample_duration = lidar_cfg.get("sample_duration_s", 2.0)

            pkt_count, avg_size = self._sample_udp_packets(port, sample_duration)
            actual_pps = pkt_count / sample_duration if sample_duration > 0 else 0

            tolerance = 0.15  # 15% tolerance
            if actual_pps >= expected_pps * (1 - tolerance):
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"{lidar_name} Packet Rate",
                        status=Status.PASS,
                        severity=Severity.INFO,
                        message=f"{actual_pps:.0f} pkt/s (expected ~{expected_pps})",
                        metrics={
                            "packets_per_second": round(actual_pps, 1),
                            "avg_packet_size": avg_size,
                            "sample_packets": pkt_count,
                        },
                    )
                )
            elif actual_pps > 0:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"{lidar_name} Packet Rate",
                        status=Status.WARN,
                        severity=Severity.MAJOR,
                        message=f"Packet rate low: {actual_pps:.0f} pkt/s (expected ~{expected_pps})",
                        metrics={"packets_per_second": round(actual_pps, 1)},
                        error_code="SENSOR_LIDAR_PKT_LOSS",
                    )
                )
            else:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"{lidar_name} Packet Rate",
                        status=Status.FAIL,
                        severity=Severity.CRITICAL,
                        message=f"No UDP packets received on port {port}!",
                        metrics={"packets_per_second": 0},
                        error_code="SENSOR_LIDAR_NO_DATA",
                        raw_output=f"Timeout waiting for UDP packets on port {port}",
                        sys_logs=self.fetch_system_logs("eth1|network", 20),
                    )
                )

        return results

    def _sample_udp_packets(self, port: int, duration: float) -> tuple:
        """Sample UDP packets and compute count / average size."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1.0)
        sock.bind(("0.0.0.0", port))

        count = 0
        total_size = 0
        start = time.monotonic()

        try:
            while time.monotonic() - start < duration:
                try:
                    data, _ = sock.recvfrom(65535)
                    count += 1
                    total_size += len(data)
                except socket.timeout:
                    continue
        finally:
            sock.close()

        avg_size = total_size // count if count > 0 else 0
        return count, avg_size
