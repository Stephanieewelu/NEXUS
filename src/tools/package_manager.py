"""
package_manager.py — Detect and drive npm / pip / yarn installs.
"""

import json
from pathlib import Path
from typing import List, Optional, Tuple

from tools.terminal import TerminalTool


class PackageManager:
    """Detects the package manager used by a project and wraps installs."""

    def __init__(self, terminal: TerminalTool):
        self.terminal = terminal

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect(self, project_path: str) -> str:
        """Return 'yarn', 'npm', or 'pip' based on lock-file presence."""
        p = Path(project_path)
        if (p / "yarn.lock").exists():
            return "yarn"
        if (p / "package.json").exists():
            return "npm"
        if (p / "requirements.txt").exists() or (p / "setup.py").exists():
            return "pip"
        return "npm"  # default

    # ------------------------------------------------------------------
    # Install helpers
    # ------------------------------------------------------------------

    def install_all(self, project_path: str) -> Tuple[str, str, int]:
        """Run the base install command (npm install / yarn / pip install -r)."""
        mgr = self.detect(project_path)
        if mgr == "yarn":
            cmd = "yarn install"
        elif mgr == "pip":
            cmd = "pip install -r requirements.txt"
        else:
            cmd = "npm install"
        return self.terminal.run(cmd, cwd=project_path)

    def add(
        self,
        packages: List[str],
        project_path: str,
        dev: bool = False,
    ) -> Tuple[str, str, int]:
        """Add one or more packages to the project."""
        mgr = self.detect(project_path)
        pkg_str = " ".join(packages)

        if mgr == "yarn":
            flag = "--dev" if dev else ""
            cmd = f"yarn add {flag} {pkg_str}".strip()
        elif mgr == "pip":
            cmd = f"pip install {pkg_str}"
        else:
            flag = "--save-dev" if dev else "--save"
            cmd = f"npm install {flag} {pkg_str}"

        return self.terminal.run(cmd, cwd=project_path)

    # ------------------------------------------------------------------
    # Scripts
    # ------------------------------------------------------------------

    def run_script(
        self, script_name: str, project_path: str
    ) -> Tuple[str, str, int]:
        """Run an npm/yarn script (e.g. 'build', 'test', 'lint')."""
        mgr = self.detect(project_path)
        if mgr == "yarn":
            cmd = f"yarn {script_name}"
        else:
            cmd = f"npm run {script_name}"
        return self.terminal.run(cmd, cwd=project_path, timeout=300)

    def list_scripts(self, project_path: str) -> List[str]:
        """Return the scripts defined in package.json (if any)."""
        pkg_path = Path(project_path) / "package.json"
        if not pkg_path.exists():
            return []
        try:
            data = json.loads(pkg_path.read_text(encoding="utf-8"))
            return list(data.get("scripts", {}).keys())
        except Exception:
            return []
