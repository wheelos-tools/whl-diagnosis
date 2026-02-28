
## 🖥️ Quick Start (Web Dashboard Recommended)

git clone https://github.com/wheelos-tools/whl-diagnosis.git

### 1. 安装与环境准备

#### 方式一：通过源码安装（推荐，支持开发模式）
```bash
git clone https://github.com/wheelos-tools/whl-diagnosis.git
cd whl-diagnosis
python3 -m pip install -e .
```

#### 方式二：构建并安装 wheel 包
```bash
# 需 Python >=3.9，推荐使用虚拟环境
python3 -m pip install --upgrade build
python3 -m build
# 生成 dist/whl_diagnosis-*.whl 后
python3 -m pip install dist/whl_diagnosis-*.whl
```

> 本项目采用 [PEP 517/518](https://peps.python.org/pep-0517/) 标准，所有依赖和元数据均在 pyproject.toml 统一管理。

如需启用 LLM 自动分析功能：
```bash
python3 -m pip install openai
```

如需启用 LLM 自动分析功能：
```bash
pip install openai
```

### 2. 自动生成车辆硬件配置

```bash
whl-diag discover --out-file config/my_vehicle.yaml
```

### 3. 启动 Web 诊断服务

```bash
# 推荐：Web Dashboard 一键诊断
whl-diag serve -c config/my_vehicle.yaml --port 7777
# 浏览器访问 http://localhost:7777
```

页面支持：
- 配置文件路径自定义
- 一键“开始诊断/刷新”按钮
- 实时显示诊断进度与状态
- 诊断结果表格与统计卡片

### 4. 命令行极简诊断（可选）

```bash
whl-diag run -c config/my_vehicle.yaml
# 输出为极简 RAW 格式，适合自动化脚本/日志采集
```

### 5. 🧠 LLM 智能分析（可选）

```bash
export LLM_API_KEY="your-api-key"
export LLM_BASE_URL="https://api.openai.com/v1" # 或自定义API
export LLM_MODEL="gpt-4o" # 或其它模型

whl-diag run -c config/my_vehicle.yaml --output llm --analyze --out-file AI_Bug_Report.md
# 查看 AI_Bug_Report.md 获取详细分析与修复建议
```

----
whl-diag run -c config/my_vehicle.yaml
```

### 4. 🧠 Run End-to-End LLM Diagnostic Triage

By adding `--output llm` and `--analyze`, the framework will capture failing evidence strings, collect contextual subsystem `dmesg` logs, and prompt an LLM to debug the vehicle:

```bash
export LLM_API_KEY="your-api-key"
export LLM_BASE_URL="https://api.openai.com/v1" # or alternative API
export LLM_MODEL="gpt-4o" # or other models

whl-diag run -c config/my_vehicle.yaml --output llm --analyze --out-file AI_Bug_Report.md
```

Take a look inside `AI_Bug_Report.md`, and you will see comprehensive logs followed by the AI's step-by-step remediation guide!

---

## 🛠 Probe Architecture

Probes are categorized into layers:
*   **L0 Hardware/Phy**: PCIe, NIC, USB linkages.
*   **L1 OS/System**: Thermal throttling, MTU configurations.
*   **L2 Network/Time**: PTP Sync, PPS status.
*   **L3 Middleware**: ROS2/CyberRT latencies, SHM.

### Defining DAG Dependencies

Edit your `config/vehicle_topology.yaml` to wire dynamic cross-probe dependencies, or hardcode them flexibly directly within the python class!

```python
class LiDARProbe(IDiagnosticProbe):
    depends_on = ["Network Link Probe", "PTP Sync Probe"]
```

If `Network Link Probe` fails, the `LiDARProbe` bypasses the 15-second polling timeout and correctly skips!
