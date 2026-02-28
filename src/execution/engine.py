import asyncio
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Type

from .interface import DiagResult, IDiagnosticProbe, Phase, Severity, Status

logger = logging.getLogger(__name__)


class DiagnosticEngine:
    def __init__(self, config: Dict):
        self.config = config
        self._probes: Dict[str, IDiagnosticProbe] = {}
        self._results: Dict[str, List[DiagResult]] = {}

    def register(self, probe_cls: Type[IDiagnosticProbe]):
        probe = probe_cls(self.config)
        self._probes[probe.name] = probe

    def _topological_layers(self) -> List[List[str]]:
        graph = defaultdict(list)
        in_degree: Dict[str, int] = {name: 0 for name in self._probes.keys()}
        all_names = set(self._probes.keys())

        for name, probe in self._probes.items():
            for dep in probe.dependencies:
                if dep in all_names:
                    graph[dep].append(name)
                    in_degree[name] += 1

        queue = sorted([name for name, degree in in_degree.items() if degree == 0])
        layers: List[List[str]] = []
        processed = 0

        while queue:
            current_layer = queue
            layers.append(current_layer)
            processed += len(current_layer)

            next_queue: List[str] = []
            for node in current_layer:
                for neighbor in sorted(graph[node]):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)

            queue = sorted(next_queue)

        if processed != len(all_names):
            raise RuntimeError("Circular dependency detected among probes!")

        return layers

    async def _run_probe_safe(
        self, probe: IDiagnosticProbe, method_name: str
    ) -> List[DiagResult]:
        try:
            loop = asyncio.get_event_loop()
            method = getattr(probe, method_name)
            return await asyncio.wait_for(
                loop.run_in_executor(None, method),
                timeout=probe.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.error(
                f"Probe '{probe.name}' timed out after {probe.timeout_seconds}s"
            )
            return [
                DiagResult(
                    module_name=probe.name,
                    item_name="TIMEOUT",
                    status=Status.ERROR,
                    severity=Severity.CRITICAL,
                    message=f"Probe execution timed out ({probe.timeout_seconds}s)",
                    phase=Phase.VALIDATION,
                    error_code="PROBE_TIMEOUT",
                )
            ]
        except Exception as exc:
            logger.exception(f"Probe '{probe.name}' crashed")
            return [
                DiagResult(
                    module_name=probe.name,
                    item_name="CRASH",
                    status=Status.ERROR,
                    severity=Severity.CRITICAL,
                    message=f"Probe crashed: {type(exc).__name__}: {exc}",
                    phase=Phase.VALIDATION,
                    error_code="PROBE_CRASH",
                )
            ]

    def _check_dependencies_passed(self, probe: IDiagnosticProbe) -> Optional[str]:
        for dep_name in probe.dependencies:
            dep_results = self._results.get(dep_name, [])
            has_critical_failure = any(
                (result.status in (Status.FAIL, Status.ERROR) and result.severity == Severity.CRITICAL)
                or result.status == Status.SKIP
                for result in dep_results
            )
            if has_critical_failure:
                return dep_name
        return None

    async def _run_probe_pipeline(
        self,
        probe: IDiagnosticProbe,
        phase_methods: List[Tuple[str, Phase, bool]],
    ) -> Tuple[str, List[DiagResult]]:
        probe_results: List[DiagResult] = []

        for method_name, phase, enabled in phase_methods:
            if not enabled:
                continue

            failed_dep = self._check_dependencies_passed(probe)
            if failed_dep:
                results = probe.on_dependency_failed(failed_dep)
                for result in results:
                    result.phase = phase
                probe_results.extend(results)
                break

            results = await self._run_probe_safe(probe, method_name)
            for result in results:
                result.phase = phase
            probe_results.extend(results)

        return probe.name, probe_results

    async def run_all(self) -> List[DiagResult]:
        execution_layers = self._topological_layers()
        all_results: List[DiagResult] = []

        mode = (
            self.config.get("_diagnosis_mode")
            or self.config.get("diagnosis_mode")
            or "default"
        )
        run_readiness = mode in ("diagnostic", "stress")
        run_startup = bool(
            self.config.get("startup_check") or self.config.get("startup_phase")
        )

        phase_methods = [
            ("discovery", Phase.DISCOVERY, True),
            ("liveness", Phase.VALIDATION, True),
            ("readiness", Phase.VALIDATION, run_readiness),
            ("startup", Phase.STARTUP, run_startup),
        ]

        for layer in execution_layers:
            tasks = [
                self._run_probe_pipeline(self._probes[probe_name], phase_methods)
                for probe_name in layer
            ]
            layer_outputs = await asyncio.gather(*tasks)

            for probe_name, probe_results in layer_outputs:
                self._results[probe_name] = probe_results
                all_results.extend(probe_results)

        return all_results

    def run(self) -> List[DiagResult]:
        return asyncio.run(self.run_all())
