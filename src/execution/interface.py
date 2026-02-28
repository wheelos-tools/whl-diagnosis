from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List
import time


class Status(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


class Severity(Enum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    INFO = "INFO"



class Criticality(Enum):
    BLOCKER = "BLOCKER"     # Must pass, otherwise CANNOT enter AD mode
    DEGRADED = "DEGRADED"   # Can pass but with limited AD capability
    OPTIONAL = "OPTIONAL"   # Warn only

class Phase(Enum):
    DISCOVERY = "DISCOVERY"
    VALIDATION = "VALIDATION"
    STARTUP = "STARTUP"


class ProbeType(Enum):
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
    criticality: Criticality = Criticality.BLOCKER
    phase: Phase = Phase.VALIDATION
    probe_type: ProbeType = ProbeType.READINESS
    metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    remediation: str = ""
    error_code: str = ""
    raw_output: str = ""
    sys_logs: str = ""


class IDiagnosticProbe(ABC):
    depends_on: List[str] = []

    def __init__(self, config: Dict):
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    def dependencies(self) -> List[str]:
        """
        Return the dynamically configured dependencies from YAML config,
        or fallback to the class-level 'depends_on' attribute.
        This allows better configuration overrides per vehicle!
        """
        custom_deps = self.config.get("probe_dependencies", {}).get(self.name)
        if custom_deps is not None:
            return custom_deps
        return getattr(self.__class__, "depends_on", [])

    @property
    def timeout_seconds(self) -> float:
        """
        Strict timeout for the entire probe execution.
        If a probe exceeds this time, it will be forcefully terminated by the engine
        to prevent hanging the entire diagnostic process.
        """
        return 10.0

    def run_check(self) -> List[DiagResult]:
        return []

    def discovery(self) -> List[DiagResult]:
        return []

    def liveness(self) -> List[DiagResult]:
        return []

    def readiness(self) -> List[DiagResult]:
        return self.run_check()

    def startup(self) -> List[DiagResult]:
        return []


    def fetch_system_logs(self, keyword: str, lines: int = 20) -> str:
        """Helper to fetch contextual dmesg or journalctl logs for LLM prompting"""
        import subprocess
        try:
            # Check dmesg first
            cmd = f"dmesg -T | grep -i '{keyword}' | tail -n {lines}"
            output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
            if output.strip():
                return "--dmesg--\n" + output.strip()

            # Fallback to journalctl
            cmd2 = f"journalctl -n {lines} | grep -i '{keyword}'"
            output2 = subprocess.check_output(cmd2, shell=True, text=True, stderr=subprocess.DEVNULL)
            if output2.strip():
                return "--journalctl--\n" + output2.strip()

            return ""
        except Exception:
            return ""

    def on_dependency_failed(self, failed_dep: str) -> List[DiagResult]:
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
