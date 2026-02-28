import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Type

from ..config.loader import load_config
from .engine import DiagnosticEngine
from .interface import DiagResult, IDiagnosticProbe
from .probe_catalog import PROBE_CATALOG


def build_runtime_config(config_path: Path, mode: str) -> Dict:
    config_model = load_config(config_path)
    config = config_model.model_dump()
    config["_diagnosis_mode"] = mode
    config["diagnosis_mode"] = mode
    return config


def resolve_probe_classes(
    modules: Optional[Iterable[str]],
) -> Tuple[List[Type[IDiagnosticProbe]], List[str]]:
    if modules is None:
        module_names = list(PROBE_CATALOG.keys())
    else:
        module_names = [str(module_name).strip() for module_name in modules]

    classes: List[Type[IDiagnosticProbe]] = []
    unknown: List[str] = []

    for module_name in module_names:
        probe_cls = PROBE_CATALOG.get(module_name)
        if probe_cls is None:
            unknown.append(module_name)
            continue
        classes.append(probe_cls)

    return classes, unknown


def run_diagnostics(
    config_path: Path,
    mode: str = "default",
    modules: Optional[Iterable[str]] = None,
) -> Tuple[List[DiagResult], Dict, List[str]]:
    config = build_runtime_config(config_path, mode)

    engine = DiagnosticEngine(config)
    probe_classes, unknown_modules = resolve_probe_classes(modules)
    for probe_cls in probe_classes:
        engine.register(probe_cls)

    results = engine.run()
    metadata = {
        "vehicle_id": config.get("vehicle_id", "unknown"),
        "vehicle_type": config.get("vehicle_type", "unknown"),
        "diagnosis_mode": mode,
        "config_version": config.get("config_version", ""),
        "software_version": os.environ.get("AD_DIAG_SW_VERSION", ""),
    }
    return results, metadata, unknown_modules
