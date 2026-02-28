from typing import Dict, Type

from .interface import IDiagnosticProbe
from whl_diag.probe.sensors.camera_probe import CameraProbe
from whl_diag.probe.network.can_probe import CANProbe
from whl_diag.probe.sensors.gnss_probe import GNSSProbe
from whl_diag.probe.compute.gpu_probe import GPUProbe
from whl_diag.probe.sensors.lidar_probe import LiDARProbe
from whl_diag.probe.network.network_probe import NetworkLinkProbe
from whl_diag.probe.network.ptp_probe import PTPProbe
from whl_diag.probe.software.system_probe import SystemProbe


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
