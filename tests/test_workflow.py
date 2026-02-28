import unittest
from unittest.mock import patch

from whl_diag.execution.interface import DiagResult, Status, Severity

try:
    from whl_diag.execution.workflow import resolve_probe_classes, run_diagnostics
    WORKFLOW_IMPORT_ERROR = None
except ModuleNotFoundError as exc:
    resolve_probe_classes = None
    run_diagnostics = None
    WORKFLOW_IMPORT_ERROR = exc


@unittest.skipIf(
    WORKFLOW_IMPORT_ERROR is not None,
    f"workflow module unavailable in this environment: {WORKFLOW_IMPORT_ERROR}",
)
class WorkflowTests(unittest.TestCase):
    def test_resolve_probe_classes_unknown(self):
        classes, unknown = resolve_probe_classes(["network", "not-exist", "camera"])
        self.assertEqual(len(classes), 2)
        self.assertEqual(unknown, ["not-exist"])

    def test_run_diagnostics_returns_unknown_modules(self):
        fake_result = DiagResult(
            module_name="Fake",
            item_name="item",
            status=Status.PASS,
            severity=Severity.INFO,
            message="ok",
        )

        with patch("src.execution.workflow.load_config") as load_config_mock, patch(
            "src.execution.workflow.DiagnosticEngine"
        ) as engine_cls_mock:
            config_model = load_config_mock.return_value
            config_model.model_dump.return_value = {
                "vehicle_id": "V1",
                "vehicle_type": "demo",
                "config_version": "1.0",
            }

            engine = engine_cls_mock.return_value
            engine.run.return_value = [fake_result]

            results, metadata, unknown = run_diagnostics(
                config_path="config/vehicle_topology.yaml",
                mode="default",
                modules=["network", "unknown_module"],
            )

        self.assertEqual(results, [fake_result])
        self.assertEqual(metadata["vehicle_id"], "V1")
        self.assertEqual(unknown, ["unknown_module"])


if __name__ == "__main__":
    unittest.main()
