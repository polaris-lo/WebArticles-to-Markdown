from __future__ import annotations

import shutil
import subprocess
import logging

logger = logging.getLogger(__name__)


def is_installed(cmd: str) -> bool:
    """Return True if an external CLI tool is available on PATH."""
    return shutil.which(cmd) is not None


def run_tool(cmd: list, timeout: int = 60) -> str:
    """Run an external CLI tool and return stdout.

    Raises RuntimeError with stderr content on non-zero exit.
    """
    logger.debug("Running external tool: %s", " ".join(str(c) for c in cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Exit code {result.returncode}")
    return result.stdout
