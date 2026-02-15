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


import asyncio
import logging
from collections import defaultdict
from typing import Dict, List, Type

from .interface import IDiagnosticProbe, DiagResult, Status, Severity, Phase

logger = logging.getLogger(__name__)


class DiagnosticEngine:
    """诊断执行引擎：负责依赖解析、调度执行、超时控制、错误隔离"""

    def __init__(self, config: Dict):
        self.config = config
        self._probes: Dict[str, IDiagnosticProbe] = {}
        self._results: Dict[str, List[DiagResult]] = {}

    def register(self, probe_cls: Type[IDiagnosticProbe]):
        """注册探针类"""
        probe = probe_cls(self.config)
        self._probes[probe.name] = probe

    def _topological_sort(self) -> List[str]:
        """对探针做拓扑排序，处理依赖关系"""
        in_degree = defaultdict(int)
        graph = defaultdict(list)
        all_names = set(self._probes.keys())

        for name, probe in self._probes.items():
            for dep in probe.dependencies:
                if dep in all_names:
                    graph[dep].append(name)
                    in_degree[name] += 1
            if name not in in_degree:
                in_degree[name] = 0

        queue = [n for n in all_names if in_degree[n] == 0]
        order = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(all_names):
            raise RuntimeError("Circular dependency detected among probes!")
        return order

    async def _run_probe_safe(
        self, probe: IDiagnosticProbe, method_name: str
    ) -> List[DiagResult]:
        """安全执行单个探针阶段：超时控制 + 异常隔离"""
        try:
            loop = asyncio.get_event_loop()
            method = getattr(probe, method_name)
            results = await asyncio.wait_for(
                loop.run_in_executor(None, method),
                timeout=probe.timeout_seconds,
            )
            return results
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
        except Exception as e:
            logger.exception(f"Probe '{probe.name}' crashed")
            return [
                DiagResult(
                    module_name=probe.name,
                    item_name="CRASH",
                    status=Status.ERROR,
                    severity=Severity.CRITICAL,
                    message=f"Probe crashed: {type(e).__name__}: {e}",
                    phase=Phase.VALIDATION,
                    error_code="PROBE_CRASH",
                )
            ]

    def _check_dependencies_passed(self, probe: IDiagnosticProbe) -> str | None:
        """检查前置依赖是否通过，返回第一个失败的依赖名称"""
        for dep_name in probe.dependencies:
            dep_results = self._results.get(dep_name, [])
            has_critical_failure = any(
                r.status in (Status.FAIL, Status.ERROR)
                and r.severity == Severity.CRITICAL
                for r in dep_results
            )
            if has_critical_failure:
                return dep_name
        return None

    async def run_all(self) -> List[DiagResult]:
        """按依赖拓扑顺序执行所有探针"""
        execution_order = self._topological_sort()
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

        for probe_name in execution_order:
            probe = self._probes[probe_name]

            probe_results: List[DiagResult] = []

            for method_name, phase, enabled in phase_methods:
                if not enabled:
                    continue

                # 检查依赖
                failed_dep = self._check_dependencies_passed(probe)
                if failed_dep:
                    results = probe.on_dependency_failed(failed_dep)
                else:
                    results = await self._run_probe_safe(probe, method_name)

                # 若结果未显式标注 phase，则补齐
                for r in results:
                    if not getattr(r, "phase", None):
                        r.phase = phase

                probe_results.extend(results)
                all_results.extend(results)

            self._results[probe_name] = probe_results

        return all_results

    def run(self) -> List[DiagResult]:
        """同步入口"""
        return asyncio.run(self.run_all())
