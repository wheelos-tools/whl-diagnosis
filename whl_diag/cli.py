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

import argparse
import sys
from pathlib import Path

from whl_diag.config.loader import load_config
from whl_diag.execution.workflow import run_diagnostics
from whl_diag.output.reporter import ConsoleReporter, JsonReporter, HtmlReporter, LlmReporter, RawReporter
from whl_diag.observability.logger import setup_logger
from whl_diag.api.server import run_server


def discover_hardware(out_file):
    """Auto-discovers hardware layout and generates a baseline vehicle_topology.yaml"""
    print(f"🔍 Auto-discovering system hardware...", file=sys.stderr)
    import subprocess
    import yaml

    # 1. Discover GPUs
    gpus = 0
    try:
        lspci_out = subprocess.check_output("lspci | grep -i 'vga'", shell=True, text=True)
        gpus = len([line for line in lspci_out.strip().split('\n') if 'NVIDIA' in line or 'Intel' in line or 'AMD' in line])
    except:
        pass

    # 2. Discover Network Interfaces
    nics = []
    try:
        ip_out = subprocess.check_output("ip -br link", shell=True, text=True)
        import json
        links = json.loads(ip_out)
        for link in links:
            if link['ifname'] != 'lo' and not link['ifname'].startswith('docker') and not link['ifname'].startswith('veth'):
                nics.append({"name": link['ifname'], "role": "data", "expected_speed": 1000, "expected_mtu": link.get('mtu', 1500)})
    except:
        nics = [{"name": "eth0", "role": "ptp_sync", "expected_speed": 1000, "expected_mtu": 1500}]

    # 3. Formulate Baseline YAML
    baseline = {
        "vehicle_type": "AutoDiscovered_Platform",
        "diagnosis_mode": "default",
        "thresholds": {"ptp_offset_ns": 500, "gpu_temp_c": 85, "cpu_temp_c": 90, "min_disk_free_gb": 50},
        "infrastructure": {
            "expected_gpu_count": gpus or 1,
            "expected_cpu_cores": 8,
            "storage": {"data_path": "/data", "min_free_gb": 50}
        },
        "time_sync": {
            "ptp": {"interface": nics[0]["name"] if nics else "eth0", "domain": 0}
        },
        "sensors": {
            "cameras": [],
            "lidars": [],
            "can": {"interfaces": []}
        },
        "network": {
            "interfaces": nics
        }
    }

    yaml_str = yaml.dump(baseline, sort_keys=False, default_flow_style=False)

    if out_file:
        with open(out_file, 'w') as f:
            f.write(yaml_str)
        print(f"✅ Baseline vehicle topology saved to {out_file}", file=sys.stderr)
    else:
        print(yaml_str)

def main():
    parser = argparse.ArgumentParser(
        description="WheelOS Autonomous Driving Hardware Diagnostics"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Run command
    run_parser = subparsers.add_parser("run", help="Run diagnostics")
    run_parser.add_argument("-c", "--config", required=True, help="Path to diagnostic config YAML")
    run_parser.add_argument(
        "-m", "--mode", choices=["default", "startup", "stress"], default="default", help="Diagnosis mode"
    )
    run_parser.add_argument(
        "-o", "--output", choices=["console", "json", "html", "llm", "raw"], default="raw", help="Output format (llm = Markdown for AI context)"
    )
    run_parser.add_argument("--out-file", help="Path to save output file")
    run_parser.add_argument("--analyze", action="store_true", help="Use LLM to analyze the generated report and provide context-aware solutions (requires LLM_API_KEY).")
    run_parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start the web diagnostic API server")
    serve_parser.add_argument("-c", "--config", help="Path to diagnostic config YAML to default to in the UI")
    serve_parser.add_argument("--port", type=int, default=7777, help="Port to run server on (default: 7777)")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind")

    # Discover command
    discover_parser = subparsers.add_parser("discover", help="Auto-discover hardware and generate topology config")
    discover_parser.add_argument("--out-file", help="Path to save generated basic vehicle_topology.yaml")

    args = parser.parse_args()

    if args.command == "discover":
        discover_hardware(args.out_file)
        return

    if args.command == "serve":
        import os
        if getattr(args, "config", None):
            os.environ["AD_DIAG_CONFIG"] = args.config
        print(f"🚀 Starting AD Diagnostic Web Server on http://{args.host}:{args.port}")
        run_server(host=args.host, port=args.port)
        return

    import os
    if args.verbose:
        os.environ["AD_DIAG_LOG_LEVEL"] = "DEBUG"
    setup_logger()

    try:
        config = load_config(args.config).model_dump()
        config["_diagnosis_mode"] = args.mode

        print("🚀 Starting AD diagnostics...\n", file=sys.stderr)

        results, metadata_wf, _ = run_diagnostics(Path(args.config), args.mode)

        # Meta info
        metadata = {
            "vehicle_id": config.get("vehicle_id", "UNKNOWN"),
            "vehicle_type": config.get("vehicle_type", "UNKNOWN"),
            "diagnosis_mode": args.mode,
        }

        # Generate report
        if args.output == "json":
            reporter = JsonReporter()
        elif args.output == "html":
            reporter = HtmlReporter()
        elif args.output == "llm":
            reporter = LlmReporter()
        elif args.output == "raw":
            reporter = RawReporter()
        else:
            reporter = ConsoleReporter()

        report_txt = reporter.generate(results, metadata)

        # AI Analysis
        if getattr(args, 'analyze', False):
            print("\n🧠 Submitting report for LLM Analysis...", file=sys.stderr)
            from whl_diag.llm.analyzer import LLMAnalyzer
            analyzer = LLMAnalyzer()
            analysis_result = analyzer.analyze_report(report_txt)
            if analysis_result:
                print("✅ Analysis Data Recieved", file=sys.stderr)
                report_txt += "\n\n" + "# 🧠 AI Expert Analysis & Remediation\n\n" + analysis_result

        if args.out_file:
            with open(args.out_file, 'w') as f:
                f.write(report_txt)
            print(f"\nReport saved to: {args.out_file}", file=sys.stderr)
        else:
            print(report_txt)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
