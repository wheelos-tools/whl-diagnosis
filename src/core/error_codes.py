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
自动驾驶诊断错误编码体系

编码格式: {LAYER}_{MODULE}_{SYMPTOM}
  LAYER:  INFRA / SYNC / SENSOR / MW
  MODULE: NET / CAM / LIDAR / CAN / PTP / GPU / PROC
  SYMPTOM: 自定义

示例: SYNC_PTP_OFFSET_HIGH
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ErrorEntry:
    code: str
    description: str
    remediation: str
    doc_url: str = ""


# 错��知识库 — 随着项目迭代持续积累
ERROR_KNOWLEDGE_BASE: Dict[str, ErrorEntry] = {
    "INFRA_NET_LINK_DOWN": ErrorEntry(
        code="INFRA_NET_LINK_DOWN",
        description="Network interface physical link is DOWN",
        remediation=(
            "1. 检查网线是否松动或损坏\n"
            "2. 检查交换机端口 LED 是否亮起\n"
            "3. 尝试更换网线或端口\n"
            "4. 检查 ethtool {iface} 确认速率协商"
        ),
    ),
    "SYNC_PTP_OFFSET_HIGH": ErrorEntry(
        code="SYNC_PTP_OFFSET_HIGH",
        description="PTP clock offset exceeds acceptable threshold",
        remediation=(
            "1. 确认 Grandmaster 设备正常工作 (pmc -u -b 0 'GET TIME_STATUS_NP')\n"
            "2. 检查网络是否存在高延迟或丢包 (ping -c 100 {master_ip})\n"
            "3. 确认 ptp4l 和 phc2sys 服务运行正常\n"
            "4. 检查 NIC 是否支持硬件时间戳 (ethtool -T {iface})"
        ),
    ),
    "SENSOR_CAM_DEVICE_MISSING": ErrorEntry(
        code="SENSOR_CAM_DEVICE_MISSING",
        description="Expected camera device not found in /dev/video*",
        remediation=(
            "1. 检查 USB/MIPI/GMSL 线缆连接\n"
            "2. 确认驱动已加载: lsmod | grep <driver_name>\n"
            "3. 检查 dmesg | tail -50 查看内核错误\n"
            "4. 重新插拔设备后等待 5s 再检查"
        ),
    ),
    "INFRA_NET_IFACE_MISSING": ErrorEntry(
        code="INFRA_NET_IFACE_MISSING",
        description="Network interface missing in system",
        remediation=(
            "1. 检查网线与网卡连接是否牢固\n"
            "2. 检查 BIOS/内核是否禁用网卡\n"
            "3. 检查驱动加载: lspci -k | grep -A3 Ethernet"
        ),
    ),
    "INFRA_NET_SPEED_LOW": ErrorEntry(
        code="INFRA_NET_SPEED_LOW",
        description="Negotiated link speed lower than expected",
        remediation=(
            "1. 检查线缆和交换机端口是否支持目标速率\n"
            "2. 运行 ethtool {iface} 查看协商详情\n"
            "3. 如为万兆链路，检查模块/光纤类型匹配"
        ),
    ),
    "INFRA_NET_MTU_MISMATCH": ErrorEntry(
        code="INFRA_NET_MTU_MISMATCH",
        description="Network MTU mismatch",
        remediation=(
            "1. 确认整条链路 MTU 配置一致\n"
            "2. 使用 ip link set {iface} mtu <value> 调整\n"
            "3. 检查交换机端口 MTU 配置"
        ),
    ),
    "INFRA_NET_SPEED_UNKNOWN": ErrorEntry(
        code="INFRA_NET_SPEED_UNKNOWN",
        description="Network link speed not reported",
        remediation=(
            "1. 检查驱动是否支持 ethtool\n"
            "2. 确认网卡支持 /sys/class/net/*/speed 读取"
        ),
    ),
    "INFRA_NET_ERROR_COUNTERS": ErrorEntry(
        code="INFRA_NET_ERROR_COUNTERS",
        description="Network RX/TX errors detected",
        remediation=(
            "1. 检查线缆质量与端口接触\n"
            "2. 查看 ethtool -S {iface} 统计\n"
            "3. 检查交换机端口错误计数"
        ),
    ),
    "SYNC_PTP_IFACE_MISSING": ErrorEntry(
        code="SYNC_PTP_IFACE_MISSING",
        description="PTP interface missing",
        remediation=(
            "1. 检查 PTP 专用网卡是否存在\n"
            "2. 检查驱动是否加载\n"
            "3. 检查网卡与交换机链路"
        ),
    ),
    "SYNC_PTP_CLOCK_MISSING": ErrorEntry(
        code="SYNC_PTP_CLOCK_MISSING",
        description="PTP clock device missing",
        remediation=(
            "1. 确认网卡支持硬件时间戳\n"
            "2. 检查 ptp4l 启动参数\n"
            "3. 查看 dmesg 是否有 PTP 相关错误"
        ),
    ),
    "SYNC_PTP_SERVICE_MISSING": ErrorEntry(
        code="SYNC_PTP_SERVICE_MISSING",
        description="ptp4l service not running",
        remediation=(
            "1. 启动 ptp4l 服务\n" "2. 检查 systemd 服务状态: systemctl status ptp4l"
        ),
    ),
    "SYNC_PTP_OFFSET_UNKNOWN": ErrorEntry(
        code="SYNC_PTP_OFFSET_UNKNOWN",
        description="Unable to parse PTP offset",
        remediation=("1. 检查 pmc 输出格式\n" "2. 确认 ptp4l 正常运行并已锁定"),
    ),
    "SYNC_PTP_GM_MISMATCH": ErrorEntry(
        code="SYNC_PTP_GM_MISMATCH",
        description="PTP grandmaster identity mismatch",
        remediation=("1. 检查期望 GM identity 配置\n" "2. 确认 GM 设备上线且配置正确"),
    ),
    "SYNC_PTP_TOOL_MISSING": ErrorEntry(
        code="SYNC_PTP_TOOL_MISSING",
        description="PTP tool (pmc) not available",
        remediation=(
            "1. 安装 linuxptp 工具包\n"
            "2. 确认 pmc 可执行路径在 PATH 中\n"
            "3. 检查容器环境是否映射 /usr/sbin"
        ),
    ),
    "SENSOR_CAM_FINGERPRINT_MISMATCH": ErrorEntry(
        code="SENSOR_CAM_FINGERPRINT_MISMATCH",
        description="Camera serial number mismatch",
        remediation=(
            "1. 检查配置文件中的 serial_number 是否正确\n"
            "2. 检查线束是否接错端口\n"
            "3. 更新车辆硬件指纹档案"
        ),
    ),
    "SENSOR_CAM_V4L2_UNAVAILABLE": ErrorEntry(
        code="SENSOR_CAM_V4L2_UNAVAILABLE",
        description="v4l2-ctl not available",
        remediation=("1. 安装 v4l-utils\n" "2. 确认容器环境已挂载 /dev/video*"),
    ),
    "SENSOR_CAM_FINGERPRINT_CHANGED": ErrorEntry(
        code="SENSOR_CAM_FINGERPRINT_CHANGED",
        description="Camera serial number changed",
        remediation=(
            "1. 确认是否更换过摄像头硬件\n"
            "2. 更新车辆硬件指纹档案\n"
            "3. 检查线束是否接错端口"
        ),
    ),
    "SENSOR_CAM_RES_MISMATCH": ErrorEntry(
        code="SENSOR_CAM_RES_MISMATCH",
        description="Camera resolution mismatch",
        remediation=(
            "1. 使用 v4l2-ctl -d {dev} --set-fmt-video 设置分辨率\n"
            "2. 检查驱动是否支持目标分辨率"
        ),
    ),
    "SENSOR_CAM_FPS_LOW": ErrorEntry(
        code="SENSOR_CAM_FPS_LOW",
        description="Camera frame rate below expected threshold",
        remediation=(
            "1. 检查 USB 带宽是否被其他设备占用\n"
            "2. 确认分辨率和帧率设置正确: v4l2-ctl -d {dev} --all\n"
            "3. 检查 PCIe/USB 控制器是否有 bandwidth 告警"
        ),
    ),
    "SENSOR_LIDAR_PKT_LOSS": ErrorEntry(
        code="SENSOR_LIDAR_PKT_LOSS",
        description="LiDAR UDP packet loss detected",
        remediation=(
            "1. 检查 NIC ring buffer 大小: ethtool -g {iface}\n"
            "2. 增大 socket buffer: sysctl -w net.core.rmem_max=26214400\n"
            "3. 检查 IRQ affinity 是否合理: cat /proc/interrupts\n"
            "4. 确认没有防火墙规则丢弃 UDP 包"
        ),
    ),
    "INFRA_GPU_THROTTLE": ErrorEntry(
        code="INFRA_GPU_THROTTLE",
        description="GPU is thermal throttling",
        remediation=(
            "1. 检查 GPU 温度: nvidia-smi -q -d TEMPERATURE\n"
            "2. 确认风扇正常运转\n"
            "3. 清理散热器灰尘\n"
            "4. 确认机箱通风不被堵塞"
        ),
    ),
}


def get_remediation(error_code: str) -> str:
    entry = ERROR_KNOWLEDGE_BASE.get(error_code)
    if entry:
        return entry.remediation
    return "未知错误码，请联系系统工程师并提供完整诊断报告。"
