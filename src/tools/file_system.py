"""
file_system.py — Read / write / manage project files.

Gives NEXUS the ability to create and manage project files within a
sandboxed workspace root.  All operations are logged for potential rollback.
"""

import os
import shutil
import time
from pathlib import Path
from typing import List, Optional


class FileSystemTool:
    """File-system operations scoped to a workspace root directory."""

    def __init__(self, workspace_root: str = "./workspace"):
        self.workspace = Path(workspace_root)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.operations_log: List[dict] = []

    # ------------------------------------------------------------------
    # Project management
    # ------------------------------------------------------------------

    def create_project(self, project_name: str) -> Path:
        """Create a new project directory inside the workspace."""
        project_path = self.workspace / project_name
        project_path.mkdir(parents=True, exist_ok=True)
        self._log("create_project", str(project_path))
        return project_path

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def write_file(self, filepath: str, content: str) -> bool:
        """Write content to a file, creating parent directories as needed."""
        try:
            full_path = Path(filepath)
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            self._log("write_file", filepath, {"size": len(content)})
            return True
        except Exception as exc:
            self._log("write_file_error", filepath, {"error": str(exc)})
            return False

    def read_file(self, filepath: str) -> Optional[str]:
        """Read and return file contents, or None on failure."""
        try:
            return Path(filepath).read_text(encoding="utf-8")
        except Exception as exc:
            self._log("read_file_error", filepath, {"error": str(exc)})
            return None

    def delete_file(self, filepath: str) -> bool:
        """Delete a file (backs up content for potential rollback)."""
        try:
            path = Path(filepath)
            backup = path.read_text(encoding="utf-8") if path.exists() else None
            path.unlink(missing_ok=True)
            self._log("delete_file", filepath, {"backup_content": backup})
            return True
        except Exception:
            return False

    def move_file(self, src: str, dst: str) -> bool:
        """Move / rename a file."""
        try:
            shutil.move(src, dst)
            self._log("move_file", src, {"destination": dst})
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Directory operations
    # ------------------------------------------------------------------

    def create_directory(self, dirpath: str) -> bool:
        """Create a directory (and any missing parents)."""
        try:
            Path(dirpath).mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            return False

    def list_directory(
        self, dirpath: str, recursive: bool = False
    ) -> List[str]:
        """Return file paths inside a directory."""
        path = Path(dirpath)
        if not path.exists():
            return []
        if recursive:
            return [str(p) for p in path.rglob("*") if p.is_file()]
        return [str(p) for p in path.iterdir()]

    # ------------------------------------------------------------------
    # Tree visualisation
    # ------------------------------------------------------------------

    def get_project_tree(self, project_path: str) -> str:
        """Return an ASCII tree of the project structure."""
        return self._build_tree(Path(project_path))

    def _build_tree(
        self, path: Path, prefix: str = "", is_last: bool = True
    ) -> str:
        connector = "└── " if is_last else "├── "
        tree = prefix + connector + path.name + "\n"

        if path.is_dir():
            _NOISE = {"__pycache__", ".git", "node_modules", ".next", "venv", ".mypy_cache"}
            children = sorted(
                [c for c in path.iterdir() if c.name not in _NOISE],
                key=lambda p: (p.is_file(), p.name),
            )
            for i, child in enumerate(children):
                is_last_child = i == len(children) - 1
                ext = "    " if is_last else "│   "
                tree += self._build_tree(child, prefix + ext, is_last_child)

        return tree

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, operation: str, target: str, metadata: Optional[dict] = None):
        self.operations_log.append({
            "operation": operation,
            "target": target,
            "metadata": metadata or {},
            "timestamp": time.time(),
        })
