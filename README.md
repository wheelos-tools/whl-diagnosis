# whl-diag

Autonomous driving diagnostic tools

## Quick Start

### 1. Installation

```bash
pip install whl-diag

```

### 2. Auto-Discovery

Generate a baseline vehicle topology configuration:

```bash
whl-diag discover --out-file config/my_vehicle.yaml

```

### 3. Launch Web Service

Start the dashboard to visualize real-time progress, statistics, and results:

```bash
whl-diag serve
# Access via http://localhost:7777

```

### 4. CLI & LLM Analysis (Optional)

For automation or AI-powered root cause analysis:

```bash
# Standard CLI run
whl-diag run -c config/my_vehicle.yaml

# AI-Powered Analysis
pip install openai
export LLM_API_KEY="your-api-key"
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_MODEL="gpt-4o"

whl-diag run -c config/my_vehicle.yaml --output llm --analyze --out-file AI_Bug_Report.md

```

---

## 🧠 Probe Architecture

Diagnostics are structured into hierarchical layers to ensure systematic troubleshooting:

| Layer | Focus Areas |
| --- | --- |
| **L0 Hardware/Phy** | PCIe, NIC, USB physical linkages |
| **L1 OS/System** | Thermal throttling, CPU load, MTU configs |
| **L2 Network/Time** | PTP Sync, PPS status, Packet loss |
| **L3 Middleware** | ROS2/CyberRT latencies, Shared Memory (SHM) |

### DAG Dependency Management

Define Directed Acyclic Graph (DAG) dependencies in `config/vehicle_topology.yaml` or directly in Python classes. If a dependency fails, downstream probes are skipped to prevent "ghost" errors.

```python
class LiDARProbe(IDiagnosticProbe):
    # This probe only runs if physical link and time sync are healthy
    depends_on = ["Network Link Probe", "PTP Sync Probe"]

```
