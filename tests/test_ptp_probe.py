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
from src.probe.network.ptp_probe import PTPProbe


class PTPProbeTests(unittest.TestCase):
    def test_readiness_offset_and_gm_mismatch(self):
        config = {
            "time_sync": {"ptp": {"expected_gm_identity": "00:11:22"}},
            "thresholds": {"ptp_offset_ns": 100},
        }
        probe = PTPProbe(config)

        pmc_output = "offsetFromMaster 120\n gmIdentity 00:11:33"

        with patch(
            "src.probe.network.ptp_probe.run_command",
            return_value=CommandResult(0, pmc_output, ""),
        ):
            results = probe.readiness()

        offset = [r for r in results if r.item_name == "PTP Offset"][0]
        self.assertEqual(offset.status, Status.WARN)

        gm = [r for r in results if r.item_name == "PTP Grandmaster"][0]
        self.assertEqual(gm.status, Status.WARN)


if __name__ == "__main__":
    unittest.main()
