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


from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional
import time


class Status(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"  # Probe internal error (distinct from FAIL on the diagnosed target)


class Severity(Enum):
    """Severity level that determines whether downstream probes are blocked."""

    CRITICAL = "CRITICAL"  # Blocking failure; downstream probes should be skipped
    MAJOR = "MAJOR"  # Important fault
    MINOR = "MINOR"  # Minor anomaly
    INFO = "INFO"  # Informational


class Phase(Enum):
    """Diagnostic phase: Discovery / Validation / Startup"""

    DISCOVERY = "DISCOVERY"
    VALIDATION = "VALIDATION"
    STARTUP = "STARTUP"


class ProbeType(Enum):
    """Kubernetes-style probe type"""

    LIVENESS = "LIVENESS"
    READINESS = "READINESS"
    STARTUP = "STARTUP"


@dataclass
class DiagResult:
    module_name: str
    item_name: str
    status: Status
    severity: Severity
    message: str
    phase: Phase = Phase.VALIDATION
    probe_type: ProbeType = ProbeType.READINESS
    metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    remediation: str = ""  # Remediation suggestion attached directly to the result
    error_code: str = ""  # Machine-readable error code, e.g. "PTP_OFFSET_HIGH"


class IDiagnosticProbe(ABC):
    """Base class that all diagnostic modules must implement."""

    def __init__(self, config: Dict):
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """Module name."""
        ...

    @property
    def dependencies(self) -> List[str]:
        """Declare prerequisite probe names; the engine uses this for topological sorting."""
        return []

    @property
    def timeout_seconds(self) -> float:
        """Maximum execution time for a single probe."""
        return 10.0

    def run_check(self) -> List[DiagResult]:
        """Run diagnostic logic (subclasses may override; or override discovery/liveness/readiness instead)."""
        return []

    def discovery(self) -> List[DiagResult]:
        """Discovery phase: detect devices/topology (non-destructive, fast)."""
        return []

    def liveness(self) -> List[DiagResult]:
        """Liveness probe: device is present and responding."""
        return []

    def readiness(self) -> List[DiagResult]:
        """Readiness probe: data quality and performance are within spec."""
        return self.run_check()

    def startup(self) -> List[DiagResult]:
        """Startup probe: cold-start initialization sequence check."""
        return []

    def on_dependency_failed(self, failed_dep: str) -> List[DiagResult]:
        """Default behavior when a prerequisite dependency fails: generate SKIP result."""
        return [
            DiagResult(
                module_name=self.name,
                item_name="ALL",
                status=Status.SKIP,
                severity=Severity.INFO,
                message=f"Skipped due to dependency failure: {failed_dep}",
                phase=Phase.VALIDATION,
                probe_type=ProbeType.READINESS,
            )
        ]
