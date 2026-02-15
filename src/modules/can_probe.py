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
CAN 总线诊断模块

功能:
  - CAN 接口存活检测
  - 报文频率采样与校验
  - 总线负载率计算与趋势预警
  - 错误帧统计
"""

import struct
import socket
import time
import logging
from collections import defaultdict
from typing import Dict, List, Optional

from src.core.interface import IDiagnosticProbe, DiagResult, Status, Severity
from src.utils.shell_runner import run_command, read_sysfs

logger = logging.getLogger(__name__)

# Linux SocketCAN 常量
CAN_RAW = 1
CAN_FMT = "=IB3x8s"  # can_id (4B) + can_dlc (1B) + pad (3B) + data (8B)
CAN_FRAME_SIZE = struct.calcsize(CAN_FMT)


class CANProbe(IDiagnosticProbe):

    @property
    def name(self) -> str:
        return "CAN Bus Probe"

    @property
    def dependencies(self) -> List[str]:
        return []  # CAN 通常独立于以太网

    @property
    def timeout_seconds(self) -> float:
        return 60.0  # CAN 采样需要较长时间

    def run_check(self) -> List[DiagResult]:
        results = []
        can_config = self.config.get("sensors", {}).get("can", {})
        interfaces = can_config.get("interfaces", [])

        if not interfaces:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name="CAN Configuration",
                    status=Status.SKIP,
                    severity=Severity.INFO,
                    message="No CAN interfaces configured, skipping.",
                )
            )
            return results

        for iface_cfg in interfaces:
            iface_name = iface_cfg["name"]
            results.extend(self._check_interface(iface_name, iface_cfg))

        return results

    def _check_interface(self, iface: str, cfg: Dict) -> List[DiagResult]:
        results = []

        # ── 1. 接口存活检测 ──
        operstate = read_sysfs(f"/sys/class/net/{iface}/operstate")
        if operstate is None:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name=f"{iface} Existence",
                    status=Status.FAIL,
                    severity=Severity.CRITICAL,
                    message=f"CAN interface {iface} not found in system!",
                    error_code="SENSOR_CAN_IFACE_MISSING",
                )
            )
            return results

        if operstate != "up":
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name=f"{iface} State",
                    status=Status.FAIL,
                    severity=Severity.CRITICAL,
                    message=f"CAN interface {iface} state is '{operstate}', expected 'up'",
                    error_code="SENSOR_CAN_IFACE_DOWN",
                )
            )
            return results

        results.append(
            DiagResult(
                module_name=self.name,
                item_name=f"{iface} State",
                status=Status.PASS,
                severity=Severity.INFO,
                message=f"CAN interface {iface} is UP",
                metrics={"state": "up"},
            )
        )

        # ── 2. 错误帧统计 ──
        results.extend(self._check_error_counters(iface))

        # ── 3. 报文频率采样 ──
        expected_msgs = cfg.get("expected_messages", [])
        if expected_msgs:
            sample_duration = 2.0
            mode = self.config.get("diagnosis_mode", "default")
            if mode == "default":
                # default 模式下做 listen-only 采样
                freq_results = self._sample_message_frequencies(
                    iface, expected_msgs, sample_duration
                )
                results.extend(freq_results)

        # ── 4. 总线负载率 ──
        bitrate = cfg.get("bitrate", 500000)
        results.extend(self._estimate_bus_load(iface, bitrate))

        return results

    def _check_error_counters(self, iface: str) -> List[DiagResult]:
        """读取 CAN 控制器错误计数器"""
        results = []

        # 通过 ip -details -statistics link show can0 获取错误统计
        cmd_result = run_command(
            ["ip", "-details", "-statistics", "link", "show", iface]
        )

        if not cmd_result.success:
            return results

        output = cmd_result.stdout
        metrics = {}

        # 解析关键错误指标
        import re

        for pattern, key in [
            (r"bus-error\s+(\d+)", "bus_errors"),
            (r"error-warning\s+(\d+)", "error_warnings"),
            (r"error-passive\s+(\d+)", "error_passives"),
            (r"bus-off\s+(\d+)", "bus_off_count"),
            (r"restarts\s+(\d+)", "restarts"),
            (r"RX:\s+bytes\s+\d+\s+packets\s+(\d+)", "rx_packets"),
            (r"TX:\s+bytes\s+\d+\s+packets\s+(\d+)", "tx_packets"),
            (r"rx_errors\s+(\d+)", "rx_errors"),
            (r"tx_errors\s+(\d+)", "tx_errors"),
        ]:
            match = re.search(pattern, output)
            if match:
                metrics[key] = int(match.group(1))

        bus_off = metrics.get("bus_off_count", 0)
        error_passives = metrics.get("error_passives", 0)

        if bus_off > 0:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name=f"{iface} Bus-Off Events",
                    status=Status.FAIL,
                    severity=Severity.CRITICAL,
                    message=f"CAN bus-off detected {bus_off} time(s)! 总线可能已中断。",
                    metrics=metrics,
                    error_code="SENSOR_CAN_BUS_OFF",
                )
            )
        elif error_passives > 0:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name=f"{iface} Error State",
                    status=Status.WARN,
                    severity=Severity.MAJOR,
                    message=f"CAN error-passive state entered {error_passives} time(s).",
                    metrics=metrics,
                    error_code="SENSOR_CAN_ERROR_PASSIVE",
                )
            )
        else:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name=f"{iface} Error Counters",
                    status=Status.PASS,
                    severity=Severity.INFO,
                    message="No critical CAN errors detected.",
                    metrics=metrics,
                )
            )

        return results

    def _sample_message_frequencies(
        self, iface: str, expected_msgs: List[Dict], duration: float
    ) -> List[DiagResult]:
        """
        通过 SocketCAN 采样报文频率。
        listen-only 模式，不影响总线通信。
        """
        results = []
        msg_counts: Dict[int, int] = defaultdict(int)

        try:
            sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, CAN_RAW)
            sock.settimeout(0.5)
            sock.bind((iface,))
        except OSError as e:
            results.append(
                DiagResult(
                    module_name=self.name,
                    item_name=f"{iface} Socket Bind",
                    status=Status.ERROR,
                    severity=Severity.CRITICAL,
                    message=f"Cannot bind CAN socket: {e}",
                    error_code="SENSOR_CAN_SOCKET_ERROR",
                )
            )
            return results

        start = time.monotonic()
        try:
            while time.monotonic() - start < duration:
                try:
                    frame = sock.recv(CAN_FRAME_SIZE)
                    can_id, dlc, data = struct.unpack(CAN_FMT, frame)
                    # 去掉标志位，保留 11-bit 或 29-bit ID
                    can_id &= 0x1FFFFFFF
                    msg_counts[can_id] += 1
                except socket.timeout:
                    continue
        finally:
            sock.close()

        # 与预期频率对比
        for msg_cfg in expected_msgs:
            raw_id = msg_cfg["id"]
            msg_id = int(raw_id, 16) if raw_id.startswith("0x") else int(raw_id)
            msg_name = msg_cfg.get("name", raw_id)
            expected_hz = msg_cfg.get("expected_hz", 10)

            count = msg_counts.get(msg_id, 0)
            actual_hz = count / duration if duration > 0 else 0
            tolerance = 0.2  # 20% 容忍度

            if actual_hz >= expected_hz * (1 - tolerance):
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"{iface} Msg {msg_name}",
                        status=Status.PASS,
                        severity=Severity.INFO,
                        message=f"{actual_hz:.1f} Hz (expected ~{expected_hz} Hz)",
                        metrics={"actual_hz": round(actual_hz, 1), "count": count},
                    )
                )
            elif actual_hz > 0:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"{iface} Msg {msg_name}",
                        status=Status.WARN,
                        severity=Severity.MAJOR,
                        message=f"Low frequency: {actual_hz:.1f} Hz (expected ~{expected_hz} Hz)",
                        metrics={"actual_hz": round(actual_hz, 1), "count": count},
                        error_code="SENSOR_CAN_MSG_LOW_FREQ",
                    )
                )
            else:
                results.append(
                    DiagResult(
                        module_name=self.name,
                        item_name=f"{iface} Msg {msg_name}",
                        status=Status.FAIL,
                        severity=Severity.CRITICAL,
                        message=f"Message 0x{msg_id:X} not received in {duration}s!",
                        metrics={"actual_hz": 0, "count": 0},
                        error_code="SENSOR_CAN_MSG_MISSING",
                    )
                )

        return results

    def _estimate_bus_load(self, iface: str, bitrate: int) -> List[DiagResult]:
        """
        估算 CAN 总线负载率。
        采样 1 秒的流量，估算占总带宽的百分比。
        标准 CAN: 每帧 overhead ≈ 47 + 8*DLC bits (不含 stuff bits)
        """
        results = []
        sample_duration = 1.0
        total_bits = 0

        try:
            sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, CAN_RAW)
            sock.settimeout(0.2)
            sock.bind((iface,))
        except OSError:
            return results

        start = time.monotonic()
        frame_count = 0
        try:
            while time.monotonic() - start < sample_duration:
                try:
                    frame = sock.recv(CAN_FRAME_SIZE)
                    _, dlc, _ = struct.unpack(CAN_FMT, frame)
                    # 标准 CAN 帧 bit 数估算 (含 stuff bits 近似 * 1.2)
                    total_bits += int((47 + 8 * dlc) * 1.2)
                    frame_count += 1
                except socket.timeout:
                    continue
        finally:
            sock.close()

        if bitrate > 0:
            bus_load_pct = (total_bits / (bitrate * sample_duration)) * 100
        else:
            bus_load_pct = 0

        thresholds = self.config.get("thresholds", {})
        warn_pct = thresholds.get("can_bus_load_warn_pct", 70)
        fail_pct = thresholds.get("can_bus_load_fail_pct", 90)

        if bus_load_pct >= fail_pct:
            status, severity = Status.FAIL, Severity.CRITICAL
            error_code = "SENSOR_CAN_BUS_OVERLOAD"
        elif bus_load_pct >= warn_pct:
            status, severity = Status.WARN, Severity.MAJOR
            error_code = "SENSOR_CAN_BUS_HIGH_LOAD"
        else:
            status, severity = Status.PASS, Severity.INFO
            error_code = ""

        results.append(
            DiagResult(
                module_name=self.name,
                item_name=f"{iface} Bus Load",
                status=status,
                severity=severity,
                message=f"Bus load: {bus_load_pct:.1f}% ({frame_count} frames/s)",
                metrics={
                    "bus_load_pct": round(bus_load_pct, 1),
                    "frames_per_second": frame_count,
                    "total_bits": total_bits,
                },
                error_code=error_code,
            )
        )

        return results
