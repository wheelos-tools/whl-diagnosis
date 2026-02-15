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
配置加载与校验模块

使用 Pydantic v2 进行强类型校验，量产环境中配置错误
是最常见的故障根因之一。每一个字段都有明确的类型约束和校验规则。
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


# ── 枚举类型 ────────────────────────────────────────────────


class DiagnosisMode(str, Enum):
    DEFAULT = "default"
    DIAGNOSTIC = "diagnostic"
    STRESS = "stress"


class MiddlewareType(str, Enum):
    ROS2 = "ros2"
    CYBER_RT = "cyber_rt"


# ── 阈值配置 ────────────────────────────────────────────────


class ThresholdsConfig(BaseModel):
    ptp_offset_ns: int = Field(
        default=500, ge=10, le=100000, description="PTP 同步偏移阈值 (纳秒)"
    )
    gpu_temp_c: int = Field(default=85, ge=50, le=105)
    cpu_temp_c: int = Field(default=90, ge=50, le=110)
    min_disk_free_gb: int = Field(default=50, ge=1)
    can_bus_load_warn_pct: float = Field(default=70.0, ge=0, le=100)
    can_bus_load_fail_pct: float = Field(default=90.0, ge=0, le=100)

    @model_validator(mode="after")
    def bus_load_ordering(self):
        if self.can_bus_load_warn_pct >= self.can_bus_load_fail_pct:
            raise ValueError(
                f"can_bus_load_warn_pct ({self.can_bus_load_warn_pct}) "
                f"must be < can_bus_load_fail_pct ({self.can_bus_load_fail_pct})"
            )
        return self


# ── 基础设施 ────────────────────────────────────────────────


class StorageConfig(BaseModel):
    data_path: str = "/data"
    min_free_gb: int = Field(default=50, ge=1)


class InfrastructureConfig(BaseModel):
    expected_gpu_count: int = Field(default=1, ge=0)
    expected_cpu_cores: int = Field(default=8, ge=1)
    storage: StorageConfig = StorageConfig()


# ── 时间同步 ────────────────────────────────────────────────


class PTPConfig(BaseModel):
    interface: str = "eth0"
    master_ip: str = ""
    domain: int = Field(default=0, ge=0, le=127)
    expected_gm_identity: str = ""

    @field_validator("interface")
    @classmethod
    def validate_interface(cls, v: str) -> str:
        if not v.isidentifier() and not all(c.isalnum() or c in "-_." for c in v):
            raise ValueError(f"Invalid network interface name: {v}")
        return v


class GNSSConfig(BaseModel):
    pps_device: str = "/dev/pps0"
    nmea_device: str = "/dev/ttyUSB0"
    nmea_baud: int = Field(default=115200, ge=4800)


class TimeSyncConfig(BaseModel):
    ptp: PTPConfig = PTPConfig()
    gnss: GNSSConfig = GNSSConfig()


# ── 传感器 ──────────────────────────────────────────────────


class CameraConfig(BaseModel):
    name: str
    device: str
    serial_number: str = ""
    expected_fps: int = Field(default=30, ge=1, le=120)
    resolution: str = "1920x1080"

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, v: str) -> str:
        parts = v.split("x")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError(f"Invalid resolution format: {v}, expected WxH")
        return v


class LiDARConfig(BaseModel):
    name: str
    type: str = "generic"
    port: int = Field(ge=1, le=65535)
    expected_packets_per_second: int = Field(default=754, ge=1)
    sample_duration_s: float = Field(default=2.0, ge=0.5, le=30.0)


class CANMessageConfig(BaseModel):
    id: str  # "0x123" 格式
    name: str
    expected_hz: float = Field(ge=0.1)

    @field_validator("id")
    @classmethod
    def validate_can_id(cls, v: str) -> str:
        try:
            val = int(v, 16) if v.startswith("0x") else int(v)
            if not (0 <= val <= 0x1FFFFFFF):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError(f"Invalid CAN ID: {v}")
        return v


class CANInterfaceConfig(BaseModel):
    name: str
    bitrate: int = Field(default=500000, ge=10000, le=8000000)
    expected_messages: List[CANMessageConfig] = []


class CANConfig(BaseModel):
    interfaces: List[CANInterfaceConfig] = []


class SensorsConfig(BaseModel):
    cameras: List[CameraConfig] = []
    lidars: List[LiDARConfig] = []
    can: CANConfig = CANConfig()


# ── 网络 ────────────────────────────────────────────────────


class NetworkInterfaceConfig(BaseModel):
    name: str
    role: str = "data"
    expected_speed: int = Field(default=1000, description="Expected link speed in Mbps")
    expected_mtu: int = Field(default=1500, ge=68, le=9216)


class NetworkConfig(BaseModel):
    interfaces: List[NetworkInterfaceConfig] = []


# ── 中间件 ──────────────────────────────────────────────────


class ProcessConfig(BaseModel):
    name: str
    expected: bool = True


class TopicConfig(BaseModel):
    name: str
    expected_hz: float = Field(ge=0.1)
    max_latency_ms: float = Field(default=100.0, ge=0)


class MiddlewareConfig(BaseModel):
    type: MiddlewareType = MiddlewareType.ROS2
    critical_processes: List[ProcessConfig] = []
    critical_topics: List[TopicConfig] = []


# ── 顶层配置 ────────────────────────────────────────────────


class VehicleTopologyConfig(BaseModel):
    """车辆拓扑配置 — 顶层 Schema"""

    vehicle_type: str = "unknown"
    vehicle_id: str = Field(default="", description="唯一车辆编号，用于车队管理")
    description: str = ""
    config_version: str = ""
    diagnosis_mode: DiagnosisMode = DiagnosisMode.DEFAULT
    startup_check: bool = False
    thresholds: ThresholdsConfig = ThresholdsConfig()
    infrastructure: InfrastructureConfig = InfrastructureConfig()
    time_sync: TimeSyncConfig = TimeSyncConfig()
    sensors: SensorsConfig = SensorsConfig()
    network: NetworkConfig = NetworkConfig()
    middleware: MiddlewareConfig = MiddlewareConfig()


def load_config(path: str | Path) -> VehicleTopologyConfig:
    """
    加载并校验配置文件。

    支持环境变量覆盖:
      AD_DIAG_VEHICLE_ID  -> vehicle_id
      AD_DIAG_MODE        -> diagnosis_mode
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    # 环境变量覆盖
    env_vehicle_id = os.environ.get("AD_DIAG_VEHICLE_ID")
    if env_vehicle_id:
        raw["vehicle_id"] = env_vehicle_id

    env_mode = os.environ.get("AD_DIAG_MODE")
    if env_mode:
        raw["diagnosis_mode"] = env_mode

    config = VehicleTopologyConfig(**raw)
    return config
