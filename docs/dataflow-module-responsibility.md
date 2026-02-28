# Dataflow and Module Responsibility

## End-to-End Dataflow

1. Entry
   - CLI: `src/cli.py`
   - API: `src/api/server.py`
2. Orchestration
   - Workflow: `src/execution/workflow.py`
   - Resolve requested probes from `PROBE_CATALOG`
   - Build runtime config and execution metadata
3. Execution
   - Engine: `src/execution/engine.py`
   - Run probes by topological layers (same-layer parallel, dependency-safe)
4. Probe Runtime
   - Probes: `src/probe/*.py`
   - Return unified `DiagResult` records
5. Reporting and Export
   - Console/JSON reporter: `src/output/reporter.py`
   - Prometheus export: `src/output/metrics.py`
   - Optional report persistence and diff: `src/output/history.py`

---

## Module Responsibility Matrix

### `src/config`
- `loader.py`
  - Owns topology schema models and strict validation
  - Applies environment-variable overrides
  - Produces typed runtime configuration

### `src/execution`
- `interface.py`
  - Defines `DiagResult`, probe lifecycle contracts, status/severity enums
- `probe_catalog.py`
  - Single source of truth for probe registration and naming
- `workflow.py`
  - Glue layer from input params to registered engine run
  - Returns `(results, metadata, unknown_modules)`
- `engine.py`
  - Dependency graph resolution
  - Layered parallel execution
  - Timeout isolation and crash-to-error conversion

### `src/probe`
- `*_probe.py`
  - Domain-specific diagnostics (network, camera, GPU, GNSS, LiDAR, CAN, system)
  - No orchestration logic; only probe responsibilities

### `src/output`
- `reporter.py`
  - Human-readable and machine-readable report generation
- `metrics.py`
  - Prometheus-format metric lines
- `history.py`
  - Report storage/list/load and summary diff helpers

### `src/knowledge`
- `error_codes.py`
  - Error-code knowledge base and remediation mapping

### `src/state`
- `fingerprint.py`
  - Hardware serial fingerprint record and change detection

### `src/observability`
- `logger.py`
  - Logging setup and formatting

---

## Compatibility Layer

- `src/core/*.py` are thin compatibility shims that re-export from new package locations.
- New code should import directly from `src/config`, `src/execution`, `src/probe`, `src/output`, `src/knowledge`, `src/state`, and `src/observability`.

---

## Import Guidelines (Recommended)

- Prefer:
  - `from src.execution.workflow import run_diagnostics`
  - `from src.execution.interface import DiagResult, Status`
  - `from src.output.reporter import JsonReporter`
  - `from src.probe.network_probe import NetworkLinkProbe`
- Avoid adding new dependencies on legacy `src.core.*` shim modules.
