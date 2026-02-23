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
    ERROR = "ERROR"  # 新增：探针自身异常（区别于被诊断对象的 FAIL）


class Severity(Enum):
    """严重等级，影响是否阻断后续诊断"""

    CRITICAL = "CRITICAL"  # 阻断性故障，下游探针应跳过
    MAJOR = "MAJOR"  # 重要故障
    MINOR = "MINOR"  # 轻微异常
    INFO = "INFO"  # 信息采集


class Phase(Enum):
    """诊断阶段：Discovery / Validation / Startup"""

    DISCOVERY = "DISCOVERY"
    VALIDATION = "VALIDATION"
    STARTUP = "STARTUP"


class ProbeType(Enum):
    """K8s 风格探针类型"""

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
    remediation: str = ""  # 修复建议直接附带在结果中
    error_code: str = ""  # 机器可读的错误编码，例如 "PTP_OFFSET_HIGH"


class IDiagnosticProbe(ABC):
    """所有诊断模块必须实现的基类"""

    def __init__(self, config: Dict):
        self.config = config

    @property
    @abstractmethod
    def name(self) -> str:
        """模块名称"""
        ...

    @property
    def dependencies(self) -> List[str]:
        """声明前置依赖的探针名称列表，引擎据此做拓扑排序"""
        return []

    @property
    def timeout_seconds(self) -> float:
        """单个探针的最大执行时间"""
        return 10.0

    def run_check(self) -> List[DiagResult]:
        """执行诊断逻辑（子类可覆盖；也可直接覆盖 discovery/liveness/readiness）"""
        return []

    def discovery(self) -> List[DiagResult]:
        """Discovery Phase: 发现设备/拓扑（无损、快速）"""
        return []

    def liveness(self) -> List[DiagResult]:
        """Liveness Probe: 设备存在且响应"""
        return []

    def readiness(self) -> List[DiagResult]:
        """Readiness Probe: 数据质量/性能达标"""
        return self.run_check()

    def startup(self) -> List[DiagResult]:
        """Startup Probe: 冷启动初始化序列检查"""
        return []

    def on_dependency_failed(self, failed_dep: str) -> List[DiagResult]:
        """当前置依赖失败时的默认行为：生成 SKIP 结果"""
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
