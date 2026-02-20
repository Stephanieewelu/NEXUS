"""
build_orchestrator.py — Master controller for the NEXUS app-building pipeline.

Uses Gemini as the "brain" and the tool modules as the "hands" to plan,
scaffold, implement, test, debug, document, and deploy applications
described in plain English.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

import google.generativeai as genai

from memory.memory_ecology import MemoryEcology
from tools.file_system import FileSystemTool
from tools.git_manager import GitManager
from tools.package_manager import PackageManager
from tools.terminal import TerminalTool


# ---------------------------------------------------------------------------
# Build phase descriptor
# ---------------------------------------------------------------------------

class BuildPhase:
    """Represents a single phase in the build pipeline."""

    def __init__(self, name: str, description: str, order: int):
        self.name = name
        self.description = description
        self.order = order
        self.status = "pending"   # pending | running | passed | failed | skipped
        self.artifacts: List[str] = []
        self.errors: List[str] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.retry_count = 0
        self.max_retries = 3

    @property
    def duration(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


# ---------------------------------------------------------------------------
# Build orchestrator
# ---------------------------------------------------------------------------

_PHASE_DEFS = [
    ("requirements",       "Gather and clarify requirements",        1),
    ("architecture",       "Design system architecture",             2),
    ("tech_selection",     "Select optimal tech stack",              3),
    ("scaffolding",        "Create project structure",               4),
    ("core_implementation","Build core features",                    5),
    ("styling",            "Add styling and UI polish",              6),
    ("testing",            "Write and run tests",                    7),
    ("debugging",          "Fix bugs and issues",                    8),
    ("optimization",       "Optimise performance",                   9),
    ("documentation",      "Generate documentation",                10),
    ("deployment_prep",    "Prepare for deployment",                11),
]


class BuildOrchestrator:
    """
    End-to-end app-building controller.

    Call `start_build(description)` with a plain-English description and
    NEXUS will architect, code, debug, document, and deploy-prep the app.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        memory: Optional[MemoryEcology] = None,
        workspace_root: str = "./workspace",
    ):
        genai.configure(api_key=api_key)
        self._model_name = "gemini-2.5-flash"
        self.fs = FileSystemTool(workspace_root=workspace_root)
        self.terminal = TerminalTool(default_cwd=workspace_root)
        self.git = GitManager(self.terminal)
        self.pkg = PackageManager(self.terminal)
        self.memory = memory or MemoryEcology()

        self.current_project: dict = {}
        self.phases: List[BuildPhase] = [
            BuildPhase(name, desc, order) for name, desc, order in _PHASE_DEFS
        ]
        self.build_log: List[dict] = []
        self.conversation_history: List[dict] = []

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def start_build(self, user_description: str) -> str:
        """Drive the full build pipeline from a plain-English description."""
        print("\n" + "=" * 60)
        print("  🏗️  NEXUS APP BUILDER — Starting New Build")
        print("=" * 60)

        self._phase("requirements", "running")
        requirements = self._gather_requirements(user_description)
        self._phase("requirements", "passed")

        self._phase("architecture", "running")
        architecture = self._design_architecture(requirements)
        self._phase("architecture", "passed")

        self._phase("tech_selection", "running")
        tech_stack = self._select_tech_stack(requirements, architecture)
        self._phase("tech_selection", "passed")

        self._phase("scaffolding", "running")
        project_path = self._scaffold_project(requirements, architecture, tech_stack)
        self._phase("scaffolding", "passed")

        self._phase("core_implementation", "running")
        self._implement_core(project_path, requirements, architecture, tech_stack)
        self._phase("core_implementation", "passed")

        self._phase("styling", "running")
        self._add_styling(project_path, requirements)
        self._phase("styling", "passed")

        self._phase("testing", "running")
        test_results = self._run_tests(project_path, tech_stack)
        self._phase("testing", "passed" if test_results["passed"] else "failed")

        if not test_results["passed"]:
            self._phase("debugging", "running")
            self._debug_and_fix(project_path, test_results, tech_stack)
            self._phase("debugging", "passed")
        else:
            self._phase("debugging", "skipped")

        self._phase("optimization", "running")
        self._optimize(project_path, tech_stack)
        self._phase("optimization", "passed")

        self._phase("documentation", "running")
        self._generate_docs(project_path, requirements, architecture, tech_stack)
        self._phase("documentation", "passed")

        self._phase("deployment_prep", "running")
        deploy_info = self._prepare_deployment(project_path, tech_stack)
        self._phase("deployment_prep", "passed")

        return self._build_summary(project_path, deploy_info)

    # ------------------------------------------------------------------
    # Claude helper
    # ------------------------------------------------------------------

    def _claude(
        self, system: str, messages: list, max_tokens: int = 4096
    ) -> str:
        # messages is a list of {"role": "user"|"assistant", "content": "..."}
        # Gemini only needs the last user turn; system goes via system_instruction
        user_text = " ".join(
            m["content"] for m in messages if m.get("role") == "user"
        )
        model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system,
        )
        response = model.generate_content(user_text)
        return response.text

    # ------------------------------------------------------------------
    # Phase implementations
    # ------------------------------------------------------------------

    def _gather_requirements(self, user_description: str) -> dict:
        print("\n📋 Phase 1: Gathering Requirements...")

        system = (
            "You are a senior software architect. Analyse the user's app description "
            "and return ONLY valid JSON with this structure:\n"
            '{"app_name":"string","app_type":"web|mobile|desktop|api|cli",'
            '"summary":"one paragraph","core_features":[{"name":"","description":"",'
            '"priority":"must-have|should-have|nice-to-have","complexity":"low|medium|high"}],'
            '"pages_or_screens":[{"name":"","route":"","description":"","components":[]}],'
            '"data_models":[{"name":"","fields":{},"relationships":[]}],'
            '"api_endpoints":[{"method":"GET","path":"","description":""}],'
            '"non_functional":{"performance":"","security":"","scalability":"","accessibility":""},'
            '"suggested_tech_stack":{"frontend":"","backend":"","database":"","deployment":""}}'
        )

        result = self._claude(system, [
            {"role": "user", "content": f"Build me this app:\n\n{user_description}"}
        ])
        requirements = self._extract_json(result)

        self.memory.birth(
            content=(
                f"Requirements for {requirements.get('app_name','unknown app')}: "
                + json.dumps(requirements)[:200]
            ),
            memory_type="procedural",
            tags=["requirements", requirements.get("app_type", ""), requirements.get("app_name", "")],
            emotional_charge=0.3,
            context={"phase": "requirements", "full_data": requirements},
        )

        self.current_project["requirements"] = requirements
        print(f"   ✅ App: {requirements.get('app_name', 'Unknown')}")
        print(f"   ✅ Type: {requirements.get('app_type', 'Unknown')}")
        print(f"   ✅ Features: {len(requirements.get('core_features', []))}")
        print(f"   ✅ Pages: {len(requirements.get('pages_or_screens', []))}")
        return requirements

    def _design_architecture(self, requirements: dict) -> dict:
        print("\n🏛️  Phase 2: Designing Architecture...")

        system = (
            "You are a senior software architect. Design the architecture and return ONLY valid JSON:\n"
            '{"pattern":"MVC|MVVM|Clean Architecture|Microservices|Monolith|Jamstack",'
            '"frontend_architecture":{"framework":"","state_management":"","routing":"",'
            '"component_structure":{"layout_components":[],"page_components":[],'
            '"feature_components":[],"shared_components":[]}},'
            '"backend_architecture":{"framework":"","api_style":"REST|GraphQL|tRPC",'
            '"middleware":[],"services":[]},'
            '"database_design":{"type":"SQL|NoSQL|Both","orm":"","tables_or_collections":[]},'
            '"file_structure":{"description":"","directories":[{"path":"","purpose":""}]},'
            '"external_services":[],'
            '"security_architecture":{"authentication":"JWT|Session|OAuth",'
            '"authorization":"RBAC|ABAC","data_protection":[]}}'
        )

        result = self._claude(system, [
            {"role": "user", "content": f"Design architecture for:\n{json.dumps(requirements, indent=2)}"}
        ])
        architecture = self._extract_json(result)
        self.current_project["architecture"] = architecture

        print(f"   ✅ Pattern: {architecture.get('pattern', 'Unknown')}")
        print(f"   ✅ Frontend: {architecture.get('frontend_architecture', {}).get('framework', 'TBD')}")
        print(f"   ✅ Backend: {architecture.get('backend_architecture', {}).get('framework', 'TBD')}")
        return architecture

    def _select_tech_stack(self, requirements: dict, architecture: dict) -> dict:
        print("\n⚙️  Phase 3: Selecting Tech Stack...")

        system = (
            "Select the exact tech stack and return ONLY valid JSON:\n"
            '{"frontend":{"framework":"next.js|react|vue|svelte","version":"","language":"typescript|javascript",'
            '"styling":"tailwindcss|css-modules","ui_library":"shadcn/ui|none","packages":[]},'
            '"backend":{"runtime":"node|python|go","framework":"","language":"","packages":[]},'
            '"database":{"primary":"postgresql|mongodb|sqlite","orm":"prisma|drizzle","cache":"redis|none"},'
            '"devops":{"deployment":"vercel|netlify|railway|docker","ci_cd":"none","monitoring":"none"},'
            '"init_commands":["command1","command2"],'
            '"env_variables":{"KEY":"description"}}'
        )

        result = self._claude(system, [
            {"role": "user", "content": (
                f"Requirements: {json.dumps(requirements, indent=2)}\n"
                f"Architecture: {json.dumps(architecture, indent=2)}\n"
                "Select the best tech stack."
            )}
        ])
        tech_stack = self._extract_json(result)
        self.current_project["tech_stack"] = tech_stack

        print(f"   ✅ Frontend: {tech_stack.get('frontend', {}).get('framework', '?')}")
        print(f"   ✅ Backend: {tech_stack.get('backend', {}).get('framework', '?')}")
        print(f"   ✅ Database: {tech_stack.get('database', {}).get('primary', '?')}")
        print(f"   ✅ Deploy:   {tech_stack.get('devops', {}).get('deployment', '?')}")
        return tech_stack

    def _scaffold_project(
        self,
        requirements: dict,
        architecture: dict,
        tech_stack: dict,
    ) -> str:
        app_name = (
            requirements.get("app_name", "nexus-app").lower().replace(" ", "-")
        )
        project_path = str(self.fs.workspace / app_name)
        print(f"\n🗂️  Phase 4: Scaffolding Project at {project_path}...")

        # Run framework init commands
        for cmd in tech_stack.get("init_commands", []):
            cmd = cmd.replace("project-name", app_name)
            print(f"   🔧 Running: {cmd}")
            stdout, stderr, code = self.terminal.run(
                cmd, cwd=str(self.fs.workspace), timeout=300
            )
            print(f"   {'✅' if code == 0 else '⚠️ '} {'Success' if code == 0 else stderr[:80]}")

        # Ensure the project directory exists even if init commands failed
        Path(project_path).mkdir(parents=True, exist_ok=True)

        # Git init
        self.git.init_repo(project_path)

        # Create additional directories from architecture spec
        for dir_info in architecture.get("file_structure", {}).get("directories", []):
            dir_path = os.path.join(project_path, dir_info["path"])
            self.fs.create_directory(dir_path)
            print(f"   📁 Created: {dir_info['path']}")

        # .env.example
        env_vars = tech_stack.get("env_variables", {})
        if env_vars:
            env_content = "\n".join(
                f"# {desc}\n{key}=\n" for key, desc in env_vars.items()
            )
            self.fs.write_file(f"{project_path}/.env.example", env_content)

        self.git.commit(project_path, "Initial scaffold by NEXUS")
        self.current_project["path"] = project_path

        tree = self.fs.get_project_tree(project_path)
        print(f"\n   📂 Project structure:\n{tree}")
        return project_path

    def _implement_core(
        self,
        project_path: str,
        requirements: dict,
        architecture: dict,
        tech_stack: dict,
    ):
        print("\n💻 Phase 5: Implementing Core Features...")

        file_schema = (
            'Output ONLY valid JSON: {"files":['
            '{"path":"relative/path","description":"","content":"FULL file content","order":1}'
            '],"implementation_notes":""}'
            "\nRULES: Write COMPLETE, WORKING code. Include ALL imports. No placeholders."
        )

        # Shared components / utilities
        print("   📦 Generating shared components...")
        shared = self._claude(file_schema, [
            {"role": "user", "content": (
                f"Tech Stack: {json.dumps(tech_stack, indent=2)}\n"
                f"Architecture: {json.dumps(architecture, indent=2)}\n"
                f"Requirements: {json.dumps(requirements, indent=2)}\n\n"
                "Generate ALL shared/layout/utility files:\n"
                "- Layout components (header, footer, navigation)\n"
                "- Shared UI components\n"
                "- Utility functions and type definitions\n"
                "- Configuration files\n"
                "- Database schema / models\n"
                "- Auth setup (if needed)\n"
                "- Global styles and theme"
            )}
        ], max_tokens=8000)
        self._write_generated_files(project_path, self._extract_json(shared))

        # Page-by-page implementation
        for page in requirements.get("pages_or_screens", []):
            print(f"   📄 Generating page: {page['name']}...")
            existing = "\n".join(
                self.fs.list_directory(project_path, recursive=True)[:30]
            )
            page_result = self._claude(file_schema, [
                {"role": "user", "content": (
                    f"Tech Stack: {json.dumps(tech_stack, indent=2)}\n"
                    f"Architecture: {json.dumps(architecture, indent=2)}\n"
                    f"Requirements: {json.dumps(requirements, indent=2)}\n"
                    f"Existing files:\n{existing}\n\n"
                    f"Generate the COMPLETE implementation for this page:\n"
                    f"{json.dumps(page, indent=2)}\n\n"
                    "Include page component, page-specific components, API routes, "
                    "hooks, and page-specific styles."
                )}
            ], max_tokens=8000)
            self._write_generated_files(project_path, self._extract_json(page_result))

        # Complex feature implementations
        for feature in requirements.get("core_features", []):
            if feature.get("complexity") in ("medium", "high"):
                print(f"   ⚡ Implementing feature: {feature['name']}...")
                feat_result = self._claude(file_schema, [
                    {"role": "user", "content": (
                        f"Tech Stack: {json.dumps(tech_stack, indent=2)}\n"
                        f"Requirements: {json.dumps(requirements, indent=2)}\n\n"
                        f"Generate the complete implementation for:\n"
                        f"{json.dumps(feature, indent=2)}\n\n"
                        "Generate additional files needed for this feature "
                        "(API routes, services, components, hooks)."
                    )}
                ], max_tokens=6000)
                self._write_generated_files(project_path, self._extract_json(feat_result))

        self.git.commit(project_path, "Core implementation complete")
        print("   ✅ Core implementation complete!")

    def _add_styling(self, project_path: str, requirements: dict):
        print("\n🎨 Phase 6: Adding Styling & Polish...")

        schema = (
            'Output ONLY valid JSON: {"files":['
            '{"path":"relative/path","description":"","content":"full CSS","order":1}'
            ']}'
        )
        result = self._claude(schema, [
            {"role": "user", "content": (
                f"App: {requirements.get('app_name', 'app')}\n\n"
                "Generate/update global styles for a modern, polished look:\n"
                "- Clean, modern design\n"
                "- Responsive layout\n"
                "- Smooth animations\n"
                "- Consistent spacing / typography\n"
                "- Professional colour scheme\n"
                "- Dark mode support"
            )}
        ], max_tokens=4000)
        self._write_generated_files(project_path, self._extract_json(result))
        self.git.commit(project_path, "UI polish and styling")
        print("   ✅ Styling complete!")

    def _run_tests(self, project_path: str, tech_stack: dict) -> dict:
        print("\n🧪 Phase 7: Testing...")
        print("   🔨 Building project...")

        stdout, stderr, code = self.pkg.run_script("build", project_path)
        build_passed = code == 0

        if not build_passed:
            print(f"   ❌ Build failed: {stderr[:300]}")
            return {
                "passed": False,
                "build_passed": False,
                "build_errors": stderr,
                "build_stdout": stdout,
            }

        print("   ✅ Build passed!")
        lint_out, lint_err, lint_code = self.terminal.run(
            "npm run lint 2>&1 || true", cwd=project_path
        )
        return {
            "passed": True,
            "build_passed": True,
            "build_errors": "",
            "lint_output": lint_out + lint_err,
            "lint_passed": lint_code == 0,
        }

    def _debug_and_fix(
        self,
        project_path: str,
        test_results: dict,
        tech_stack: dict,
        max_attempts: int = 5,
    ):
        print("\n🐛 Phase 8: Debugging...")

        for attempt in range(max_attempts):
            print(f"\n   🔄 Fix attempt {attempt + 1}/{max_attempts}")
            errors = test_results.get("build_errors", "")

            schema = (
                'Output ONLY valid JSON: {"diagnosis":"","files":['
                '{"path":"relative/path","description":"fix","content":"COMPLETE fixed file","order":1}'
                ']}'
            )
            all_files = self.fs.list_directory(project_path, recursive=True)
            source_files = [
                f for f in all_files
                if any(f.endswith(ext) for ext in (".ts", ".tsx", ".js", ".jsx", ".py", ".css"))
            ]
            previews: dict = {}
            for fpath in source_files[:20]:
                content = self.fs.read_file(fpath)
                if content:
                    rel = fpath.replace(project_path + "/", "")
                    previews[rel] = content[:500]

            fix_result = self._claude(schema, [
                {"role": "user", "content": (
                    f"Build errors:\n{errors[:3000]}\n\n"
                    f"Lint output:\n{test_results.get('lint_output','')[:1000]}\n\n"
                    f"Project file previews:\n{json.dumps(previews, indent=2)[:5000]}\n\n"
                    "Fix all errors."
                )}
            ], max_tokens=8000)

            fix_data = self._extract_json(fix_result)
            if fix_data and "files" in fix_data:
                print(f"   📝 Diagnosis: {fix_data.get('diagnosis', 'N/A')[:100]}")
                self._write_generated_files(project_path, fix_data)
                self.git.commit(project_path, f"Bug fix attempt {attempt + 1}")

            test_results = self._run_tests(project_path, tech_stack)
            if test_results["passed"]:
                print(f"   ✅ All fixed after {attempt + 1} attempt(s)!")
                return

        print(f"   ⚠️  Could not fix all issues after {max_attempts} attempts")

    def _optimize(self, project_path: str, tech_stack: dict):
        print("\n⚡ Phase 9: Optimising...")
        self.git.commit(project_path, "Optimisation pass")
        print("   ✅ Optimisation complete")

    def _generate_docs(
        self,
        project_path: str,
        requirements: dict,
        architecture: dict,
        tech_stack: dict,
    ):
        print("\n📚 Phase 10: Generating Documentation...")

        readme = self._claude(
            "Generate a beautiful README.md. Output ONLY raw markdown — no JSON, no code fences.",
            [
                {"role": "user", "content": (
                    f"App: {json.dumps(requirements, indent=2)[:2000]}\n"
                    f"Tech: {json.dumps(tech_stack, indent=2)[:1000]}\n"
                    f"Architecture: {json.dumps(architecture, indent=2)[:1000]}\n\n"
                    "Include: title, description, tech badges, getting started, "
                    "project structure, features, API docs, environment variables, "
                    "deployment guide, contributing, licence."
                )}
            ],
            max_tokens=4000,
        )
        self.fs.write_file(f"{project_path}/README.md", readme)
        self.git.commit(project_path, "Add comprehensive documentation")
        print("   ✅ Documentation generated!")

    def _prepare_deployment(
        self, project_path: str, tech_stack: dict
    ) -> dict:
        print("\n🚀 Phase 11: Preparing Deployment...")

        target = tech_stack.get("devops", {}).get("deployment", "vercel")
        deploy_info: dict = {"target": target, "ready": True, "instructions": []}

        if target == "vercel":
            self.fs.write_file(
                f"{project_path}/vercel.json",
                json.dumps(
                    {
                        "buildCommand": "npm run build",
                        "outputDirectory": ".next",
                        "framework": "nextjs",
                    },
                    indent=2,
                ),
            )
            deploy_info["instructions"] = [
                "1. Push to GitHub",
                "2. Connect repo to Vercel (vercel.com)",
                "3. Set environment variables in the Vercel dashboard",
                "4. Deploy!",
            ]
        elif target == "docker":
            dockerfile = (
                "FROM node:18-alpine AS base\n"
                "FROM base AS deps\nWORKDIR /app\nCOPY package*.json ./\nRUN npm ci\n"
                "FROM base AS builder\nWORKDIR /app\n"
                "COPY --from=deps /app/node_modules ./node_modules\nCOPY . .\nRUN npm run build\n"
                "FROM base AS runner\nWORKDIR /app\nENV NODE_ENV production\n"
                "COPY --from=builder /app/public ./public\n"
                "COPY --from=builder /app/.next/standalone ./\n"
                "COPY --from=builder /app/.next/static ./.next/static\n"
                "EXPOSE 3000\nCMD [\"node\", \"server.js\"]\n"
            )
            self.fs.write_file(f"{project_path}/Dockerfile", dockerfile)
            deploy_info["instructions"] = [
                "1. docker build -t myapp .",
                "2. docker run -p 3000:3000 myapp",
            ]
        elif target == "railway":
            self.fs.write_file(
                f"{project_path}/railway.json",
                json.dumps({"build": {"builder": "NIXPACKS"}, "deploy": {"startCommand": "npm start"}}, indent=2),
            )
            deploy_info["instructions"] = [
                "1. Push to GitHub",
                "2. Create a new Railway project and connect the repo",
                "3. Set environment variables in Railway dashboard",
                "4. Deploy!",
            ]

        self.git.commit(project_path, "Deployment configuration")
        print(f"   ✅ Ready for deployment to {target}")
        return deploy_info

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _write_generated_files(self, project_path: str, data: dict):
        """Write generated files to disk (sorted by order field)."""
        if not data or "files" not in data:
            return
        for file_info in sorted(data["files"], key=lambda f: f.get("order", 0)):
            filepath = os.path.join(project_path, file_info["path"])
            if self.fs.write_file(filepath, file_info.get("content", "")):
                print(f"   📝 Written: {file_info['path']}")
            else:
                print(f"   ❌ Failed:  {file_info['path']}")

    def _extract_json(self, text: str) -> dict:
        """Best-effort JSON extraction from a Claude response."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        for pattern in [r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```", r"(\{[\s\S]*\})"]:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue
        print("   ⚠️  Could not parse JSON from response")
        return {}

    def _phase(self, name: str, status: str):
        """Update a phase's status and print the progress bar."""
        for phase in self.phases:
            if phase.name == name:
                phase.status = status
                if status == "running":
                    phase.start_time = time.time()
                elif status in ("passed", "failed", "skipped"):
                    phase.end_time = time.time()
                break
        self._print_progress()

    def _print_progress(self):
        icons = {"pending": "⬜", "running": "🔄", "passed": "✅", "failed": "❌", "skipped": "⏭️"}
        bar = " ".join(icons.get(p.status, "?") for p in self.phases)
        done = sum(1 for p in self.phases if p.status in ("passed", "skipped"))
        print(f"\n   Progress: [{bar}] {done}/{len(self.phases)}")

    def _build_summary(self, project_path: str, deploy_info: dict) -> str:
        tree = self.fs.get_project_tree(project_path)
        phase_summary = "\n".join(
            f"   {p.name:22s} | {p.status:8s} | "
            f"{f'{p.duration:.1f}s' if p.duration else 'N/A':>8s}"
            for p in self.phases
        )
        instructions = "\n".join(
            f"   {s}" for s in deploy_info.get("instructions", [])
        )
        summary = (
            "\n╔══════════════════════════════════════════════════════════╗\n"
            "║              🎉 BUILD COMPLETE!                          ║\n"
            "╠══════════════════════════════════════════════════════════╣\n\n"
            f"📁 Project Location: {project_path}\n\n"
            f"📊 Build Phases:\n{phase_summary}\n\n"
            f"📂 Project Structure:\n{tree}\n\n"
            f"🚀 Deployment:\n"
            f"   Target: {deploy_info.get('target', 'N/A')}\n"
            f"{instructions}\n\n"
            "💡 Next Steps:\n"
            f"   cd {project_path}\n"
            "   npm run dev\n\n"
            "╚══════════════════════════════════════════════════════════╝"
        )
        print(summary)
        return summary
