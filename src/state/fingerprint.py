import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

FINGERPRINT_PATH = Path("/var/lib/ad-diag/hardware_fingerprint.json")


def load_fingerprint() -> Dict:
    if FINGERPRINT_PATH.exists():
        return json.loads(FINGERPRINT_PATH.read_text())
    return {}


def save_fingerprint(fp: Dict):
    FINGERPRINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FINGERPRINT_PATH.write_text(json.dumps(fp, indent=2, ensure_ascii=False))


def check_and_update(
    device_role: str,
    current_serial: str,
    device_info: Optional[Dict] = None,
) -> Optional[str]:
    fp = load_fingerprint()
    previous = fp.get(device_role)
    change_msg = None

    if previous and previous.get("serial_number") != current_serial:
        change_msg = (
            f"⚠️ Hardware change detected: {device_role} SN changed from "
            f"'{previous['serial_number']}' to '{current_serial}'"
        )
        logger.warning(change_msg)

    fp[device_role] = {
        "serial_number": current_serial,
        "last_seen": datetime.now().isoformat(),
        "info": device_info or {},
    }
    save_fingerprint(fp)
    return change_msg
