"""
git_manager.py — Git version control for agent-built projects.
"""

from typing import Optional

from tools.terminal import TerminalTool


_GITIGNORE = """\
node_modules/
.next/
__pycache__/
*.pyc
.env
.env.local
dist/
build/
.DS_Store
venv/
"""


class GitManager:
    """Thin wrapper around common git operations."""

    def __init__(self, terminal: TerminalTool):
        self.terminal = terminal

    # ------------------------------------------------------------------
    # Repo lifecycle
    # ------------------------------------------------------------------

    def init_repo(self, project_path: str) -> bool:
        """Initialise a git repository and add a sensible .gitignore."""
        _, _, code = self.terminal.run("git init", cwd=project_path)
        if code == 0:
            gitignore_path = f"{project_path}/.gitignore"
            try:
                from pathlib import Path
                Path(gitignore_path).write_text(_GITIGNORE, encoding="utf-8")
            except Exception:
                pass
        return code == 0

    def commit(self, project_path: str, message: str) -> bool:
        """Stage all changes and commit."""
        self.terminal.run("git add -A", cwd=project_path)
        # Set a default identity in case the environment has none
        self.terminal.run(
            'git -c user.email="nexus@agent" -c user.name="NEXUS" '
            f'commit -m "{message}"',
            cwd=project_path,
        )
        return True

    def create_branch(self, project_path: str, branch_name: str) -> bool:
        """Create and check out a new branch."""
        _, _, code = self.terminal.run(
            f"git checkout -b {branch_name}", cwd=project_path
        )
        return code == 0

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def get_diff(self, project_path: str) -> str:
        stdout, _, _ = self.terminal.run("git diff", cwd=project_path)
        return stdout

    def get_log(self, project_path: str, n: int = 10) -> str:
        stdout, _, _ = self.terminal.run(
            f"git log --oneline -n {n}", cwd=project_path
        )
        return stdout

    def get_status(self, project_path: str) -> str:
        stdout, _, _ = self.terminal.run("git status --short", cwd=project_path)
        return stdout
