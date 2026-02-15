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

from src.core.engine import DiagnosticEngine
from src.core.interface import IDiagnosticProbe, DiagResult, Status, Severity, Phase


class DummyProbe(IDiagnosticProbe):
    def __init__(self, config):
        super().__init__(config)
        self.calls = []

    @property
    def name(self) -> str:
        return "Dummy"

    def discovery(self):
        self.calls.append("discovery")
        return [
            DiagResult(
                module_name=self.name,
                item_name="discovery",
                status=Status.PASS,
                severity=Severity.INFO,
                message="ok",
            )
        ]

    def liveness(self):
        self.calls.append("liveness")
        return [
            DiagResult(
                module_name=self.name,
                item_name="liveness",
                status=Status.PASS,
                severity=Severity.INFO,
                message="ok",
            )
        ]

    def readiness(self):
        self.calls.append("readiness")
        return [
            DiagResult(
                module_name=self.name,
                item_name="readiness",
                status=Status.PASS,
                severity=Severity.INFO,
                message="ok",
            )
        ]


class FailingProbe(IDiagnosticProbe):
    @property
    def name(self) -> str:
        return "Failing"

    def liveness(self):
        return [
            DiagResult(
                module_name=self.name,
                item_name="liveness",
                status=Status.FAIL,
                severity=Severity.CRITICAL,
                message="fail",
            )
        ]


class DependentProbe(IDiagnosticProbe):
    @property
    def name(self) -> str:
        return "Dependent"

    @property
    def dependencies(self):
        return ["Failing"]

    def liveness(self):
        return [
            DiagResult(
                module_name=self.name,
                item_name="liveness",
                status=Status.PASS,
                severity=Severity.INFO,
                message="ok",
            )
        ]


class EnginePhaseTests(unittest.TestCase):
    def test_default_mode_runs_discovery_and_liveness(self):
        config = {"_diagnosis_mode": "default"}
        engine = DiagnosticEngine(config)
        engine.register(DummyProbe)
        results = engine.run()

        self.assertEqual(len(results), 2)
        phases = [r.phase for r in results]
        self.assertIn(Phase.DISCOVERY, phases)
        self.assertIn(Phase.VALIDATION, phases)

    def test_diagnostic_mode_runs_readiness(self):
        config = {"_diagnosis_mode": "diagnostic"}
        engine = DiagnosticEngine(config)
        engine.register(DummyProbe)
        results = engine.run()

        self.assertEqual(len(results), 3)
        items = {r.item_name for r in results}
        self.assertIn("readiness", items)

    def test_dependency_failure_skips_dependent(self):
        config = {"_diagnosis_mode": "default"}
        engine = DiagnosticEngine(config)
        engine.register(FailingProbe)
        engine.register(DependentProbe)
        results = engine.run()

        dependent_results = [r for r in results if r.module_name == "Dependent"]
        self.assertTrue(dependent_results)
        self.assertTrue(all(r.status == Status.SKIP for r in dependent_results))


if __name__ == "__main__":
    unittest.main()
