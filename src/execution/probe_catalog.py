from typing import Dict, Type

from .interface import IDiagnosticProbe
from src.probe.sensors.camera_probe import CameraProbe
from src.probe.network.can_probe import CANProbe
from src.probe.sensors.gnss_probe import GNSSProbe
from src.probe.compute.gpu_probe import GPUProbe
from src.probe.sensors.lidar_probe import LiDARProbe
from src.probe.network.network_probe import NetworkLinkProbe
from src.probe.network.ptp_probe import PTPProbe
from src.probe.software.system_probe import SystemProbe


PROBE_CATALOG: Dict[str, Type[IDiagnosticProbe]] = {
    "system": SystemProbe,
    "network": NetworkLinkProbe,
    "ptp": PTPProbe,
    "gnss": GNSSProbe,
    "camera": CameraProbe,
    "gpu": GPUProbe,
    "lidar": LiDARProbe,
    "can": CANProbe,
}
