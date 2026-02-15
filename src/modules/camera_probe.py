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
Camera 诊断模块

功能:
  - Discovery: 设备存在性与指纹记录
  - Readiness: 分辨率与帧率配置检查 (非侵入)
"""

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
from src.core.fingerprint import check_and_update
from src.utils.shell_runner import run_command

logger = logging.getLogger(__name__)


class CameraProbe(IDiagnosticProbe):

    @property
    def name(self) -> str:
        return "Camera Probe"

    @property
    def timeout_seconds(self) -> float:
        return 12.0

    def discovery(self) -> List[DiagResult]:
        results = []
        cameras = self.config.get("sensors", {}).get("cameras", [])

        if not cameras:
            return [
                DiagResult(
                    module_name=self.name,
                    item_name="Camera Configuration",
                    status=Status.SKIP,
                    severity=Severity.INFO,
                    message="No cameras configured, skipping.",
                    phase=Phase.DISCOVERY,
                    probe_type=ProbeType.LIVENESS,
                )
            ]

        for cam in cameras:
            cam_name = cam["name"]
            dev = cam["device"]
            serial_expected = cam.get("serial_number", "")

            cmd_result = run_command(["test", "-e", dev])
            if not cmd_result.success:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"{cam_name} Presence",
                        status=Status.FAIL,
                        severity=Severity.CRITICAL,
                        message=f"Camera device {dev} not found.",
                        phase=Phase.DISCOVERY,
                        probe_type=ProbeType.LIVENESS,
                        error_code="SENSOR_CAM_DEVICE_MISSING",
                    )
                )
                continue

            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name=f"{cam_name} Presence",
                    status=Status.PASS,
                    severity=Severity.INFO,
                    message=f"Camera device {dev} present.",
                    phase=Phase.DISCOVERY,
                    probe_type=ProbeType.LIVENESS,
                    metrics={"device": dev},
                )
            )

            # 尝试读取 udev 序列号并做硬件指纹变更检测
            serial = ""
            udev_result = run_command(
                ["udevadm", "info", "--query=property", "--name", dev],
                timeout=4.0,
            )
            if udev_result.success:
                for line in udev_result.stdout.split("\n"):
                    if line.startswith("ID_SERIAL_SHORT="):
                        serial = line.split("=", 1)[1].strip()
                        break

            if serial:
                change_msg = check_and_update(
                    device_role=cam_name,
                    current_serial=serial,
                    device_info={"device": dev},
                )

                if change_msg:
                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name=f"{cam_name} Fingerprint",
                            status=Status.WARN,
                            severity=Severity.MAJOR,
                            message=change_msg,
                            phase=Phase.DISCOVERY,
                            probe_type=ProbeType.LIVENESS,
                            error_code="SENSOR_CAM_FINGERPRINT_CHANGED",
                        )
                    )
                elif serial_expected and serial_expected != serial:
                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name=f"{cam_name} Fingerprint",
                            status=Status.WARN,
                            severity=Severity.MAJOR,
                            message=f"Serial mismatch: {serial} (expected {serial_expected})",
                            phase=Phase.DISCOVERY,
                            probe_type=ProbeType.LIVENESS,
                            error_code="SENSOR_CAM_FINGERPRINT_MISMATCH",
                        )
                    )
                else:
                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name=f"{cam_name} Fingerprint",
                            status=Status.PASS,
                            severity=Severity.INFO,
                            message=f"Serial OK: {serial}",
                            phase=Phase.DISCOVERY,
                            probe_type=ProbeType.LIVENESS,
                            metrics={"serial": serial},
                        )
                    )

        return results

    def readiness(self) -> List[DiagResult]:
        results = []
        cameras = self.config.get("sensors", {}).get("cameras", [])

        for cam in cameras:
            cam_name = cam["name"]
            dev = cam["device"]
            expected_fps = cam.get("expected_fps", 30)
            expected_res = cam.get("resolution", "")

            cmd_result = run_command(["v4l2-ctl", "-d", dev, "--all"], timeout=6.0)
            if not cmd_result.success:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"{cam_name} Capabilities",
                        status=Status.WARN,
                        severity=Severity.MAJOR,
                        message=f"v4l2-ctl unavailable or failed: {cmd_result.stderr}",
                        phase=Phase.VALIDATION,
                        probe_type=ProbeType.READINESS,
                        error_code="SENSOR_CAM_V4L2_UNAVAILABLE",
                    )
                )
                continue

            output = cmd_result.stdout
            fps_match = re.search(r"Frames per second:\s*([\d.]+)", output)
            res_match = re.search(r"Width/Height\s*:\s*(\d+)\s*/\s*(\d+)", output)

            if fps_match:
                actual_fps = float(fps_match.group(1))
                if actual_fps + 0.1 < expected_fps:
                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name=f"{cam_name} FPS",
                            status=Status.WARN,
                            severity=Severity.MAJOR,
                            message=f"FPS {actual_fps:.1f} (expected {expected_fps})",
                            phase=Phase.VALIDATION,
                            probe_type=ProbeType.READINESS,
                            metrics={"fps": actual_fps},
                            error_code="SENSOR_CAM_FPS_LOW",
                        )
                    )
                else:
                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name=f"{cam_name} FPS",
                            status=Status.PASS,
                            severity=Severity.INFO,
                            message=f"FPS {actual_fps:.1f} OK",
                            phase=Phase.VALIDATION,
                            probe_type=ProbeType.READINESS,
                            metrics={"fps": actual_fps},
                        )
                    )

            if res_match and expected_res:
                width = res_match.group(1)
                height = res_match.group(2)
                actual_res = f"{width}x{height}"
                if actual_res != expected_res:
                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name=f"{cam_name} Resolution",
                            status=Status.WARN,
                            severity=Severity.MAJOR,
                            message=f"Resolution {actual_res} (expected {expected_res})",
                            phase=Phase.VALIDATION,
                            probe_type=ProbeType.READINESS,
                            metrics={"resolution": actual_res},
                            error_code="SENSOR_CAM_RES_MISMATCH",
                        )
                    )
                else:
                    results.append(
                        DiagResult(
                            module_name=self.name,
                            item_name=f"{cam_name} Resolution",
                            status=Status.PASS,
                            severity=Severity.INFO,
                            message=f"Resolution {actual_res} OK",
                            phase=Phase.VALIDATION,
                            probe_type=ProbeType.READINESS,
                            metrics={"resolution": actual_res},
                        )
                    )

        return results
