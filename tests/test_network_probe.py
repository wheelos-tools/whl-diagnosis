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

from src.core.interface import Status
from src.modules.network_probe import NetworkLinkProbe


class NetworkProbeTests(unittest.TestCase):
    def test_discovery_interface_missing(self):
        config = {"network": {"interfaces": [{"name": "ethX", "role": "data"}]}}
        probe = NetworkLinkProbe(config)

        with patch("src.modules.network_probe.read_sysfs", return_value=None):
            results = probe.discovery()

        self.assertEqual(results[0].status, Status.FAIL)
        self.assertEqual(results[0].error_code, "INFRA_NET_IFACE_MISSING")

    def test_readiness_speed_mtu_and_errors(self):
        config = {
            "network": {
                "interfaces": [
                    {"name": "eth0", "expected_speed": 1000, "expected_mtu": 9000}
                ]
            }
        }
        probe = NetworkLinkProbe(config)

        def fake_read_sysfs(path):
            if path.endswith("/speed"):
                return "100"
            if path.endswith("/mtu"):
                return "1500"
            if path.endswith("/statistics/rx_errors"):
                return "3"
            if path.endswith("/statistics/tx_errors"):
                return "1"
            if path.endswith("/operstate"):
                return "up"
            return None

        with patch("src.modules.network_probe.read_sysfs", side_effect=fake_read_sysfs):
            results = probe.readiness()

        error_codes = {r.error_code for r in results}
        self.assertIn("INFRA_NET_SPEED_LOW", error_codes)
        self.assertIn("INFRA_NET_MTU_MISMATCH", error_codes)
        self.assertIn("INFRA_NET_ERROR_COUNTERS", error_codes)


if __name__ == "__main__":
    unittest.main()
