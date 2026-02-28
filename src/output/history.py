import json
from pathlib import Path
from typing import Dict, List


HISTORY_DIR = Path("/var/lib/ad-diag/history")


def save_report(report: Dict) -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    ts = report.get("generated_at", "unknown-time").replace(":", "-")
    vehicle_id = report.get("vehicle_id", "unknown")
    out = HISTORY_DIR / f"{vehicle_id}_{ts}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    return out


def list_reports(limit: int = 20) -> List[Path]:
    if not HISTORY_DIR.exists():
        return []
    files = sorted(
        HISTORY_DIR.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return files[:limit]


def load_report(path: Path) -> Dict:
    return json.loads(path.read_text())


def summary_diff(previous: Dict, current: Dict) -> Dict:
    previous_summary = previous.get("summary", {})
    current_summary = current.get("summary", {})
    keys = ["total", "pass", "warn", "fail", "error", "skip"]
    return {
        key: {
            "previous": previous_summary.get(key, 0),
            "current": current_summary.get(key, 0),
            "delta": current_summary.get(key, 0) - previous_summary.get(key, 0),
        }
        for key in keys
    }
