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


import unittest
from unittest.mock import patch

from src.utils.shell_runner import CommandResult
from src.execution.interface import Status
from src.probe.sensors.camera_probe import CameraProbe


class CameraProbeTests(unittest.TestCase):
    def test_discovery_fingerprint_change(self):
        config = {
            "sensors": {
                "cameras": [
                    {"name": "front", "device": "/dev/video0", "serial_number": "ABC"}
                ]
            }
        }
        probe = CameraProbe(config)

        def fake_run_command(args, timeout=10.0, check=False, env=None):
            if args[:2] == ["test", "-e"]:
                return CommandResult(0, "", "")
            if args[0] == "udevadm":
                return CommandResult(0, "ID_SERIAL_SHORT=XYZ", "")
            return CommandResult(1, "", "fail")

        with patch(
            "src.probe.sensors.camera_probe.run_command", side_effect=fake_run_command
        ), patch("src.probe.sensors.camera_probe.check_and_update", return_value="changed"):
            results = probe.discovery()

        fingerprint = [r for r in results if "Fingerprint" in r.item_name][0]
        self.assertEqual(fingerprint.status, Status.WARN)

    def test_readiness_fps_and_resolution(self):
        config = {
            "sensors": {
                "cameras": [
                    {
                        "name": "front",
                        "device": "/dev/video0",
                        "expected_fps": 30,
                        "resolution": "1920x1080",
                    }
                ]
            }
        }
        probe = CameraProbe(config)

        output = "Frames per second: 25.0\nWidth/Height : 1280 / 720\n"

        with patch(
            "src.probe.sensors.camera_probe.run_command",
            return_value=CommandResult(0, output, ""),
        ):
            results = probe.readiness()

        fps = [r for r in results if r.item_name.endswith("FPS")][0]
        res = [r for r in results if r.item_name.endswith("Resolution")][0]
        self.assertEqual(fps.status, Status.WARN)
        self.assertEqual(res.status, Status.WARN)


if __name__ == "__main__":
    unittest.main()
