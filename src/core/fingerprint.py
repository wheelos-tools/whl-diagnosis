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
硬件指纹管理：记录并比对硬件 SN 变更
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

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
    """
    检查硬件指纹是否变更。

    Returns:
        None 如果未变更或首次记录
        str  变更描述信息（如 "front_camera SN changed: CAM-001 → CAM-999"）
    """
    fp = load_fingerprint()
    previous = fp.get(device_role)
    change_msg = None

    if previous and previous.get("serial_number") != current_serial:
        change_msg = (
            f"⚠️ 硬件变更检测: {device_role} SN 从 "
            f"'{previous['serial_number']}' 变为 '{current_serial}'"
        )
        logger.warning(change_msg)

    fp[device_role] = {
        "serial_number": current_serial,
        "last_seen": datetime.now().isoformat(),
        "info": device_info or {},
    }
    save_fingerprint(fp)
    return change_msg
