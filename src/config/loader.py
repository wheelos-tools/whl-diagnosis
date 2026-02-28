from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import List

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DiagnosisMode(str, Enum):
    DEFAULT = "default"
    DIAGNOSTIC = "diagnostic"
    STRESS = "stress"


class MiddlewareType(str, Enum):
    ROS2 = "ros2"
    CYBER_RT = "cyber_rt"


class ThresholdsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ptp_offset_ns: int = Field(
        default=500, ge=10, le=100000, description="PTP offset threshold (ns)"
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


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_path: str = "/data"
    min_free_gb: int = Field(default=50, ge=1)


class InfrastructureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_gpu_count: int = Field(default=1, ge=0)
    expected_cpu_cores: int = Field(default=8, ge=1)
    storage: StorageConfig = Field(default_factory=StorageConfig)


class PTPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interface: str = "eth0"
    master_ip: str = ""
    domain: int = Field(default=0, ge=0, le=127)
    expected_gm_identity: str = ""

    @field_validator("interface")
    @classmethod
    def validate_interface(cls, value: str) -> str:
        if not value.isidentifier() and not all(
            char.isalnum() or char in "-_." for char in value
        ):
            raise ValueError(f"Invalid network interface name: {value}")
        return value


class GNSSConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pps_device: str = "/dev/pps0"
    nmea_device: str = "/dev/ttyUSB0"
    nmea_baud: int = Field(default=115200, ge=4800)


class TimeSyncConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ptp: PTPConfig = Field(default_factory=PTPConfig)
    gnss: GNSSConfig = Field(default_factory=GNSSConfig)


class CameraConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    device: str
    serial_number: str = ""
    expected_fps: int = Field(default=30, ge=1, le=120)
    resolution: str = "1920x1080"

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, value: str) -> str:
        parts = value.split("x")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise ValueError(f"Invalid resolution format: {value}, expected WxH")
        return value


class LiDARConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str = "generic"
    port: int = Field(ge=1, le=65535)
    expected_packets_per_second: int = Field(default=754, ge=1)
    sample_duration_s: float = Field(default=2.0, ge=0.5, le=30.0)


class CANMessageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    expected_hz: float = Field(ge=0.1)

    @field_validator("id")
    @classmethod
    def validate_can_id(cls, value: str) -> str:
        try:
            parsed = int(value, 16) if value.startswith("0x") else int(value)
            if not (0 <= parsed <= 0x1FFFFFFF):
                raise ValueError
        except (ValueError, TypeError):
            raise ValueError(f"Invalid CAN ID: {value}")
        return value


class CANInterfaceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    bitrate: int = Field(default=500000, ge=10000, le=8000000)
    expected_messages: List[CANMessageConfig] = Field(default_factory=list)


class CANConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interfaces: List[CANInterfaceConfig] = Field(default_factory=list)


class SensorsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cameras: List[CameraConfig] = Field(default_factory=list)
    lidars: List[LiDARConfig] = Field(default_factory=list)
    can: CANConfig = Field(default_factory=CANConfig)


class NetworkInterfaceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    role: str = "data"
    expected_speed: int = Field(default=1000, description="Expected link speed in Mbps")
    expected_mtu: int = Field(default=1500, ge=68, le=9216)


class NetworkConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interfaces: List[NetworkInterfaceConfig] = Field(default_factory=list)


class ProcessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    expected: bool = True


class TopicConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    expected_hz: float = Field(ge=0.1)
    max_latency_ms: float = Field(default=100.0, ge=0)


class MiddlewareConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: MiddlewareType = MiddlewareType.ROS2
    critical_processes: List[ProcessConfig] = Field(default_factory=list)
    critical_topics: List[TopicConfig] = Field(default_factory=list)



from typing import Dict

class AliasConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    match_by: str
    value: str


from typing import Dict

class AliasConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    match_by: str
    value: str

class VehicleTopologyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vehicle_type: str = "unknown"
    vehicle_id: str = Field(default="", description="Unique vehicle identifier")
    description: str = ""
    probe_dependencies: Dict[str, List[str]] = Field(default_factory=dict)
    aliases: Dict[str, AliasConfig] = Field(default_factory=dict)
    probe_dependencies: Dict[str, List[str]] = Field(default_factory=dict)
    aliases: Dict[str, AliasConfig] = Field(default_factory=dict)
    config_version: str = ""
    diagnosis_mode: DiagnosisMode = DiagnosisMode.DEFAULT
    startup_check: bool = False
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)
    infrastructure: InfrastructureConfig = Field(default_factory=InfrastructureConfig)
    time_sync: TimeSyncConfig = Field(default_factory=TimeSyncConfig)
    sensors: SensorsConfig = Field(default_factory=SensorsConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    middleware: MiddlewareConfig = Field(default_factory=MiddlewareConfig)



def translate_aliases(config_dict: dict) -> dict:
    import json
    import subprocess
    aliases = config_dict.get("aliases", {})
    if not aliases:
        return config_dict
        
    resolved_map = {}
    for alias_name, alias_cfg in aliases.items():
        match_by = alias_cfg.get("match_by")
        val = alias_cfg.get("value")
        
        # Simple udev/sysfs mock resolver
        if match_by == "mac_address":
            try:
                ip_out = subprocess.check_output("ip -j link", shell=True, text=True)
                links = json.loads(ip_out)
                for link in links:
                    if link.get("address", "").lower() == val.lower():
                        resolved_map[alias_name] = link["ifname"]
                        break
            except Exception:
                pass
        elif match_by == "usb_serial":
            # Mocking /dev/video* resolution for cameras
            try:
                # Naive mock for now, assuming val implies some physical mapping
                resolved_map[alias_name] = f"/dev/video_by_serial_{val}"
            except Exception:
                pass
                
    if not resolved_map:
        return config_dict

    # Recursively traverse dict and replace ${alias_name}
    def _replace_recursive(obj):
        if isinstance(obj, dict):
            return {k: _replace_recursive(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_replace_recursive(v) for v in obj]
        elif isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            inner_name = obj[2:-1]
            return resolved_map.get(inner_name, obj)
        return obj
        
    return _replace_recursive(config_dict)

def load_config(path: str | Path) -> VehicleTopologyConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as file:
        raw = yaml.safe_load(file) or {}

    env_vehicle_id = os.environ.get("AD_DIAG_VEHICLE_ID")
    if env_vehicle_id:
        raw["vehicle_id"] = env_vehicle_id

    env_mode = os.environ.get("AD_DIAG_MODE")
    if env_mode:
        raw["diagnosis_mode"] = env_mode

    raw = translate_aliases(raw)
    return VehicleTopologyConfig(**raw)
