"""
terminal.py — Execute shell commands safely on behalf of the agent.

Includes a basic safety filter that blocks obviously destructive patterns.
All executed commands are logged.
"""

import os
import subprocess
from typing import Generator, List, Optional, Tuple


class TerminalTool:
    """Shell execution wrapper with safety filtering and history logging."""

    # Commands / patterns that are never allowed
    _DANGEROUS_PATTERNS = [
        "rm -rf /",
        "rm -rf ~",
        "mkfs",
        ":(){:|:&};:",   # Fork bomb
        "dd if=/dev",
        "chmod -R 777 /",
        "> /dev/sda",
        "wget.*|.*sh",
        "curl.*|.*sh",
    ]

    def __init__(self, default_cwd: str = "./workspace"):
        self.default_cwd = default_cwd
        self.command_history: List[dict] = []
        self.env = os.environ.copy()

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    def run(
        self,
        command: str,
        cwd: Optional[str] = None,
        timeout: int = 120,
    ) -> Tuple[str, str, int]:
        """
        Run a shell command synchronously.

        Returns:
            (stdout, stderr, return_code)
        """
        if self._is_dangerous(command):
            return "", "BLOCKED: Potentially dangerous command", -1

        working_dir = cwd or self.default_cwd

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=working_dir,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=self.env,
            )
            self.command_history.append({
                "command": command,
                "cwd": working_dir,
                "return_code": result.returncode,
                "stdout_preview": result.stdout[:200],
                "stderr_preview": result.stderr[:200],
            })
            return result.stdout, result.stderr, result.returncode

        except subprocess.TimeoutExpired:
            return "", f"Command timed out after {timeout}s", -1
        except Exception as exc:
            return "", f"Error: {exc}", -1

    def run_and_stream(
        self, command: str, cwd: Optional[str] = None
    ) -> Generator[str, None, None]:
        """Run a command and yield output lines as they arrive."""
        working_dir = cwd or self.default_cwd
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            env=self.env,
        )
        assert process.stdout is not None
        for line in process.stdout:
            yield line.rstrip()
        process.wait()

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    def install_packages(
        self,
        packages: List[str],
        manager: str = "npm",
        cwd: Optional[str] = None,
    ) -> Tuple[str, str, int]:
        """Install packages via the specified package manager."""
        if manager == "npm":
            cmd = f"npm install {' '.join(packages)}"
        elif manager == "pip":
            cmd = f"pip install {' '.join(packages)}"
        elif manager == "yarn":
            cmd = f"yarn add {' '.join(packages)}"
        else:
            return "", f"Unknown package manager: {manager}", -1
        return self.run(cmd, cwd=cwd)

    # ------------------------------------------------------------------
    # Safety
    # ------------------------------------------------------------------

    def _is_dangerous(self, command: str) -> bool:
        cmd_lower = command.lower().strip()
        return any(pattern in cmd_lower for pattern in self._DANGEROUS_PATTERNS)
