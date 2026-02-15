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
AD Diagnostic System - CLI Entry Point
用法:
    ad-diag                    # 使用默认配置运行全量诊断
    ad-diag --config custom.yaml
    ad-diag --module ptp,camera   # 只运行指定模块
    ad-diag --format json         # JSON 输出
    ad-diag --output report.json  # 保存到文件
    ad-diag --mode diagnostic     # 诊断模式（会做主动测试）
"""
import argparse
import sys
from pathlib import Path
import os

# 确保项目根目录在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.engine import DiagnosticEngine
from src.core.reporter import ConsoleReporter, JsonReporter
from src.core.config_loader import load_config
from src.modules.network_probe import NetworkLinkProbe, PTPProbe
from src.modules.camera_probe import CameraProbe
from src.modules.gpu_probe import GPUProbe
from src.modules.lidar_probe import LiDARProbe
from src.modules.gnss_probe import GNSSProbe
from src.modules.can_probe import CANProbe
from src.modules.system_probe import SystemProbe

# 模块注册表
PROBE_REGISTRY = {
    "system": SystemProbe,
    "network": NetworkLinkProbe,
    "ptp": PTPProbe,
    "gnss": GNSSProbe,
    "camera": CameraProbe,
    "gpu": GPUProbe,
    "lidar": LiDARProbe,
    "can": CANProbe,
}


def main():
    parser = argparse.ArgumentParser(
        description="🚗 Autonomous Driving Full-Stack Diagnostic System"
    )
    parser.add_argument(
        "--config",
        "-c",
        default="config/vehicle_topology.yaml",
        help="Path to vehicle topology config file",
    )
    parser.add_argument(
        "--module",
        "-m",
        default=None,
        help="Comma-separated module names to run (default: all)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["console", "json"],
        default="console",
        help="Output format",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Save report to file",
    )
    parser.add_argument(
        "--mode",
        choices=["default", "diagnostic", "stress"],
        default="default",
        help="Diagnosis mode",
    )

    args = parser.parse_args()

    # 加载配置
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        sys.exit(1)

    config_model = load_config(config_path)
    config = config_model.model_dump()
    config["_diagnosis_mode"] = args.mode
    config["diagnosis_mode"] = args.mode

    # 初始化引擎
    engine = DiagnosticEngine(config)

    # 注册模块
    if args.module:
        selected = [m.strip() for m in args.module.split(",")]
    else:
        selected = list(PROBE_REGISTRY.keys())

    for mod_name in selected:
        if mod_name in PROBE_REGISTRY:
            engine.register(PROBE_REGISTRY[mod_name])
        else:
            print(f"⚠️ Unknown module: {mod_name}, skipping")

    # 执行诊断
    results = engine.run()

    # 生成报告
    metadata = {
        "vehicle_id": config.get("vehicle_id", "unknown"),
        "vehicle_type": config.get("vehicle_type", "unknown"),
        "diagnosis_mode": args.mode,
        "config_version": config.get("config_version", ""),
        "software_version": os.environ.get("AD_DIAG_SW_VERSION", ""),
    }

    if args.format == "json":
        reporter = JsonReporter()
    else:
        reporter = ConsoleReporter()

    report = reporter.generate(results, metadata)

    if args.output:
        Path(args.output).write_text(report)
        print(f"📄 Report saved to {args.output}")
    else:
        if args.format == "json":
            print(report)


if __name__ == "__main__":
    main()
