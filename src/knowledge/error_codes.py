from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ErrorEntry:
    code: str
    description: str
    remediation: str
    doc_url: str = ""


ERROR_KNOWLEDGE_BASE: Dict[str, ErrorEntry] = {
    "INFRA_NET_LINK_DOWN": ErrorEntry(
        code="INFRA_NET_LINK_DOWN",
        description="Network interface physical link is DOWN",
        remediation=(
            "1. Check whether the Ethernet cable is loose or damaged\n"
            "2. Verify switch port LED activity\n"
            "3. Try another cable or switch port\n"
            "4. Run ethtool {iface} to confirm speed negotiation"
        ),
    ),
    "SYNC_PTP_OFFSET_HIGH": ErrorEntry(
        code="SYNC_PTP_OFFSET_HIGH",
        description="PTP clock offset exceeds acceptable threshold",
        remediation=(
            "1. Verify Grandmaster health (pmc -u -b 0 'GET TIME_STATUS_NP')\n"
            "2. Check network latency/loss (ping -c 100 {master_ip})\n"
            "3. Confirm ptp4l and phc2sys services are running\n"
            "4. Verify NIC hardware timestamp support (ethtool -T {iface})"
        ),
    ),
    "SENSOR_CAM_DEVICE_MISSING": ErrorEntry(
        code="SENSOR_CAM_DEVICE_MISSING",
        description="Expected camera device not found in /dev/video*",
        remediation=(
            "1. Check USB/MIPI/GMSL cable connections\n"
            "2. Confirm driver is loaded: lsmod | grep <driver_name>\n"
            "3. Inspect recent kernel logs: dmesg | tail -50\n"
            "4. Replug the device and retry after 5 seconds"
        ),
    ),
    "INFRA_NET_IFACE_MISSING": ErrorEntry(
        code="INFRA_NET_IFACE_MISSING",
        description="Network interface missing in system",
        remediation=(
            "1. Check physical cable and NIC connection\n"
            "2. Verify BIOS/kernel did not disable the NIC\n"
            "3. Check driver binding: lspci -k | grep -A3 Ethernet"
        ),
    ),
    "INFRA_NET_SPEED_LOW": ErrorEntry(
        code="INFRA_NET_SPEED_LOW",
        description="Negotiated link speed lower than expected",
        remediation=(
            "1. Ensure cable and switch port support target speed\n"
            "2. Run ethtool {iface} to inspect negotiation details\n"
            "3. For 10G links, validate module/fiber compatibility"
        ),
    ),
    "INFRA_NET_MTU_MISMATCH": ErrorEntry(
        code="INFRA_NET_MTU_MISMATCH",
        description="Network MTU mismatch",
        remediation=(
            "1. Ensure MTU is consistent along the full path\n"
            "2. Adjust host MTU with ip link set {iface} mtu <value>\n"
            "3. Verify switch port MTU configuration"
        ),
    ),
    "INFRA_NET_SPEED_UNKNOWN": ErrorEntry(
        code="INFRA_NET_SPEED_UNKNOWN",
        description="Network link speed not reported",
        remediation=(
            "1. Check whether driver supports ethtool\n"
            "2. Confirm NIC supports /sys/class/net/*/speed"
        ),
    ),
    "INFRA_NET_ERROR_COUNTERS": ErrorEntry(
        code="INFRA_NET_ERROR_COUNTERS",
        description="Network RX/TX errors detected",
        remediation=(
            "1. Check cable quality and port contact\n"
            "2. Review ethtool -S {iface} counters\n"
            "3. Check switch-side error counters"
        ),
    ),
    "SYNC_PTP_IFACE_MISSING": ErrorEntry(
        code="SYNC_PTP_IFACE_MISSING",
        description="PTP interface missing",
        remediation=(
            "1. Verify dedicated PTP NIC exists\n"
            "2. Verify driver is loaded\n"
            "3. Check NIC-to-switch link state"
        ),
    ),
    "SYNC_PTP_CLOCK_MISSING": ErrorEntry(
        code="SYNC_PTP_CLOCK_MISSING",
        description="PTP clock device missing",
        remediation=(
            "1. Confirm NIC supports hardware timestamping\n"
            "2. Validate ptp4l startup parameters\n"
            "3. Inspect dmesg for PTP-related errors"
        ),
    ),
    "SYNC_PTP_SERVICE_MISSING": ErrorEntry(
        code="SYNC_PTP_SERVICE_MISSING",
        description="ptp4l service not running",
        remediation=(
            "1. Start ptp4l service\n" "2. Check systemd status: systemctl status ptp4l"
        ),
    ),
    "SYNC_PTP_OFFSET_UNKNOWN": ErrorEntry(
        code="SYNC_PTP_OFFSET_UNKNOWN",
        description="Unable to parse PTP offset",
        remediation=("1. Check pmc output format\n" "2. Confirm ptp4l is running and locked"),
    ),
    "SYNC_PTP_GM_MISMATCH": ErrorEntry(
        code="SYNC_PTP_GM_MISMATCH",
        description="PTP grandmaster identity mismatch",
        remediation=("1. Verify expected GM identity configuration\n" "2. Ensure GM is online and correctly configured"),
    ),
    "SYNC_PTP_TOOL_MISSING": ErrorEntry(
        code="SYNC_PTP_TOOL_MISSING",
        description="PTP tool (pmc) not available",
        remediation=(
            "1. Install linuxptp package\n"
            "2. Ensure pmc executable is available in PATH\n"
            "3. Verify container maps /usr/sbin"
        ),
    ),
    "SENSOR_CAM_FINGERPRINT_MISMATCH": ErrorEntry(
        code="SENSOR_CAM_FINGERPRINT_MISMATCH",
        description="Camera serial number mismatch",
        remediation=(
            "1. Verify serial_number in config is correct\n"
            "2. Check harness port mapping\n"
            "3. Update hardware fingerprint records"
        ),
    ),
    "SENSOR_CAM_V4L2_UNAVAILABLE": ErrorEntry(
        code="SENSOR_CAM_V4L2_UNAVAILABLE",
        description="v4l2-ctl not available",
        remediation=("1. Install v4l-utils\n" "2. Ensure /dev/video* is mounted in container"),
    ),
    "SENSOR_CAM_FINGERPRINT_CHANGED": ErrorEntry(
        code="SENSOR_CAM_FINGERPRINT_CHANGED",
        description="Camera serial number changed",
        remediation=(
            "1. Confirm whether camera hardware was replaced\n"
            "2. Update hardware fingerprint records\n"
            "3. Verify harness port mapping"
        ),
    ),
    "SENSOR_CAM_RES_MISMATCH": ErrorEntry(
        code="SENSOR_CAM_RES_MISMATCH",
        description="Camera resolution mismatch",
        remediation=(
            "1. Set resolution via v4l2-ctl -d {dev} --set-fmt-video\n"
            "2. Verify driver support for target resolution"
        ),
    ),
    "SENSOR_CAM_FPS_LOW": ErrorEntry(
        code="SENSOR_CAM_FPS_LOW",
        description="Camera frame rate below expected threshold",
        remediation=(
            "1. Check whether USB bandwidth is occupied by other devices\n"
            "2. Verify resolution/frame-rate config: v4l2-ctl -d {dev} --all\n"
            "3. Check PCIe/USB controller for bandwidth alerts"
        ),
    ),
    "SENSOR_LIDAR_PKT_LOSS": ErrorEntry(
        code="SENSOR_LIDAR_PKT_LOSS",
        description="LiDAR UDP packet loss detected",
        remediation=(
            "1. Inspect NIC ring buffer size: ethtool -g {iface}\n"
            "2. Increase socket buffer: sysctl -w net.core.rmem_max=26214400\n"
            "3. Validate IRQ affinity: cat /proc/interrupts\n"
            "4. Ensure firewall rules are not dropping UDP packets"
        ),
    ),
    "INFRA_GPU_THROTTLE": ErrorEntry(
        code="INFRA_GPU_THROTTLE",
        description="GPU is thermal throttling",
        remediation=(
            "1. Check GPU temperature: nvidia-smi -q -d TEMPERATURE\n"
            "2. Ensure cooling fans are working\n"
            "3. Clean dust from heatsinks\n"
            "4. Verify chassis airflow is unobstructed"
        ),
    ),
}


def get_remediation(error_code: str) -> str:
    entry = ERROR_KNOWLEDGE_BASE.get(error_code)
    if entry:
        return entry.remediation
    return "Unknown error code. Please contact system engineering with the full diagnostic report."
