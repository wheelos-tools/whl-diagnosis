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


import subprocess
import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


def run_command(
    args: List[str],
    timeout: float = 10.0,
    check: bool = False,
    env: Optional[dict] = None,
) -> CommandResult:
    """
    Execute external commands safely.

    Key security principles:
    1. Use list arguments, never `shell=True`
    2. Enforce timeouts to avoid blocking
    3. Log every external invocation
    """
    logger.debug(f"Running command: {' '.join(args)}")
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,  # Explicitly disable shell injection vectors
            env=env,
        )
        if check and proc.returncode != 0:
            logger.warning(f"Command failed (rc={proc.returncode}): {proc.stderr}")
        return CommandResult(proc.returncode, proc.stdout.strip(), proc.stderr.strip())
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out: {' '.join(args)}")
        return CommandResult(-1, "", "Command timed out")
    except FileNotFoundError:
        logger.error(f"Command not found: {args[0]}")
        return CommandResult(-1, "", f"Command not found: {args[0]}")


def read_sysfs(path: str) -> Optional[str]:
    """
    Read sysfs/procfs files safely.
    More efficient and safer than calling `cat` via subprocess.
    """
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except (FileNotFoundError, PermissionError, OSError) as e:
        logger.warning(f"Cannot read {path}: {e}")
        return None
