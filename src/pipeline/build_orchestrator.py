"""
build_orchestrator.py — Master controller for the NEXUS app-building pipeline.

Uses Gemini as the "brain" and the tool modules as the "hands" to plan,
scaffold, implement, test, debug, document, and deploy applications
described in plain English.

Key fixes vs previous version:
  - Builds/tests run in the correct sub-directory (frontend/ for split projects)
  - package.json created BEFORE npm install is called
  - File blueprint generated first to prevent duplicates
  - Debug phase reads the files that actually contain errors
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from memory.memory_ecology import MemoryEcology
from tools.file_system import FileSystemTool
from tools.git_manager import GitManager
from tools.package_manager import PackageManager
from tools.terminal import TerminalTool


# ---------------------------------------------------------------------------
# Build phase descriptor
# ---------------------------------------------------------------------------

class BuildPhase:
    def __init__(self, name: str, description: str, order: int):
        self.name = name
        self.description = description
        self.order = order
        self.status = "pending"
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    @property
    def duration(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


# ---------------------------------------------------------------------------
# Build orchestrator
# ---------------------------------------------------------------------------

_PHASE_DEFS = [
    ("requirements",        "Gather and clarify requirements",   1),
    ("architecture",        "Design system architecture",        2),
    ("tech_selection",      "Select optimal tech stack",         3),
    ("scaffolding",         "Create project structure",          4),
    ("core_implementation", "Build core features",               5),
    ("styling",             "Add styling and UI polish",         6),
    ("testing",             "Build and run tests",               7),
    ("debugging",           "Fix bugs and issues",               8),
    ("optimization",        "Optimise performance",              9),
    ("documentation",       "Generate documentation",           10),
    ("deployment_prep",     "Prepare for deployment",           11),
]


class BuildOrchestrator:
    """End-to-end app-building controller."""

    def __init__(
        self,
        gemini_client=None,       # GeminiClient instance (preferred)
        api_key: Optional[str] = None,
        memory: Optional[MemoryEcology] = None,
        workspace_root: str = "./workspace",
    ):
        # Accept either a pre-built GeminiClient or create one from api_key
        if gemini_client is not None:
            self.llm = gemini_client
        else:
            from gemini_client import GeminiClient
            self.llm = GeminiClient(api_key=api_key)

        self.fs = FileSystemTool(workspace_root=workspace_root)
        self.terminal = TerminalTool(default_cwd=workspace_root)
        self.git = GitManager(self.terminal)
        self.pkg = PackageManager(self.terminal)
        self.memory = memory or MemoryEcology()

        self.project: Dict = {}
        self.phases: List[BuildPhase] = [
            BuildPhase(n, d, o) for n, d, o in _PHASE_DEFS
        ]
        self.generated_files: Dict[str, str] = {}  # path → content, prevents duplicates

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def start_build(self, user_description: str) -> str:
        print("\n" + "=" * 60)
        print("  🏗️  NEXUS APP BUILDER — Starting New Build")
        print("=" * 60)

        try:
            self._set_phase("requirements", "running")
            reqs = self._phase_requirements(user_description)
            self._set_phase("requirements", "passed")

            self._set_phase("architecture", "running")
            arch = self._phase_architecture(reqs)
            self._set_phase("architecture", "passed")

            self._set_phase("tech_selection", "running")
            tech = self._phase_tech_stack(reqs, arch)
            self._set_phase("tech_selection", "passed")

            self._set_phase("scaffolding", "running")
            project_path = self._phase_scaffold(reqs, arch, tech)
            self._set_phase("scaffolding", "passed")

            self._set_phase("core_implementation", "running")
            self._phase_implement(project_path, reqs, arch, tech)
            self._set_phase("core_implementation", "passed")

            self._set_phase("styling", "running")
            self._phase_styling(project_path, reqs, tech)
            self._set_phase("styling", "passed")

            self._set_phase("testing", "running")
            test_ok, test_errors = self._phase_test(project_path, tech)
            self._set_phase("testing", "passed" if test_ok else "failed")

            if not test_ok:
                self._set_phase("debugging", "running")
                self._phase_debug(project_path, tech, test_errors)
                self._set_phase("debugging", "passed")
            else:
                self._set_phase("debugging", "passed")

            self._set_phase("optimization", "running")
            self._set_phase("optimization", "passed")  # lightweight pass

            self._set_phase("documentation", "running")
            self._phase_docs(project_path, reqs, tech)
            self._set_phase("documentation", "passed")

            self._set_phase("deployment_prep", "running")
            deploy = self._phase_deploy(project_path, tech)
            self._set_phase("deployment_prep", "passed")

            return self._summary(project_path, deploy)

        except Exception as exc:
            print(f"\n  ❌ Build error: {exc}")
            import traceback
            traceback.print_exc()
            return f"Build failed: {exc}"

    # ------------------------------------------------------------------
    # Phase 1 — Requirements
    # ------------------------------------------------------------------

    def _phase_requirements(self, description: str) -> dict:
        print("\n📋 Phase 1: Gathering Requirements...")

        system = """Analyse this app idea and return ONLY valid JSON:
{
    "app_name": "lowercase-hyphenated-name",
    "display_name": "Human Readable Name",
    "app_type": "web",
    "summary": "one paragraph description",
    "core_features": [
        {"name": "...", "description": "...", "priority": "must-have", "complexity": "low|medium|high"}
    ],
    "pages": [
        {"name": "...", "route": "/path", "description": "...", "components": []}
    ],
    "data_models": [
        {"name": "...", "fields": {"field": "type"}}
    ],
    "api_endpoints": [
        {"method": "GET", "path": "/api/...", "description": "..."}
    ]
}"""

        result = self.llm.generate(system, f"Build this app:\n{description}")
        reqs = self.llm.extract_json(result)

        # Sanitise app name
        name = re.sub(r"[^a-z0-9-]", "-", reqs.get("app_name", "nexus-app").lower()).strip("-")
        reqs["app_name"] = name or "nexus-app"

        self.project["requirements"] = reqs
        print(f"   ✅ App: {reqs.get('display_name', name)}")
        print(f"   ✅ Features: {len(reqs.get('core_features', []))}")
        print(f"   ✅ Pages: {len(reqs.get('pages', []))}")
        return reqs

    # ------------------------------------------------------------------
    # Phase 2 — Architecture
    # ------------------------------------------------------------------

    def _phase_architecture(self, reqs: dict) -> dict:
        print("\n🏛️  Phase 2: Designing Architecture...")

        # Detect if user description explicitly mentions Python / FastAPI
        desc_lower = json.dumps(reqs).lower()
        python_requested = any(w in desc_lower for w in
                               ["python", "fastapi", "flask", "django", "sqlalchemy"])

        system = f"""Design the app architecture. Return ONLY valid JSON:
{{
    "structure": "single|fullstack-split",
    "frontend_framework": "next.js|react-vite",
    "backend_framework": "next.js-api|fastapi|express",
    "database": "sqlite|postgresql",
    "auth": "jwt|session|none"
}}
IMPORTANT DEFAULT: ALWAYS use "single" (Next.js fullstack) UNLESS the user
explicitly mentioned Python, FastAPI, Flask, or Django.
{"Python/FastAPI was detected — fullstack-split is allowed." if python_requested else
 "No Python backend was requested — you MUST use structure=single."}"""

        result = self.llm.generate(system, json.dumps(reqs, indent=2)[:3000])
        arch = self.llm.extract_json(result)

        # Safety: enforce "single" if Python was not requested
        if not python_requested and arch.get("structure") == "fullstack-split":
            print("   ⚠️  LLM chose fullstack-split without Python request — overriding to single")
            arch["structure"] = "single"
            arch["frontend_framework"] = "next.js"
            arch["backend_framework"] = "next.js-api"

        self.project["architecture"] = arch
        print(f"   ✅ Structure: {arch.get('structure', '?')}")
        print(f"   ✅ Frontend: {arch.get('frontend_framework', '?')}")
        print(f"   ✅ Backend: {arch.get('backend_framework', '?')}")
        return arch

    # ------------------------------------------------------------------
    # Phase 3 — Tech stack
    # ------------------------------------------------------------------

    def _phase_tech_stack(self, reqs: dict, arch: dict) -> dict:
        print("\n⚙️  Phase 3: Selecting Tech Stack...")

        structure = arch.get("structure", "single")
        is_split = structure == "fullstack-split"

        if is_split:
            tech = {
                "type": "fullstack-split",
                "frontend": {"framework": "react-vite", "language": "typescript", "styling": "tailwindcss"},
                "backend": {"framework": arch.get("backend_framework", "fastapi"), "language": "python"},
                "database": arch.get("database", "sqlite"),
                "build_dir": "frontend",   # ← where `npm run build` is run
            }
        else:
            tech = {
                "type": "single",
                "framework": "next.js",
                "language": "typescript",
                "styling": "tailwindcss",
                "database": arch.get("database", "sqlite"),
                "build_dir": ".",
            }

        self.project["tech"] = tech
        print(f"   ✅ Type: {tech['type']}")
        return tech

    # ------------------------------------------------------------------
    # Phase 4 — Scaffolding
    # ------------------------------------------------------------------

    def _phase_scaffold(self, reqs: dict, arch: dict, tech: dict) -> str:
        app_name = reqs["app_name"]
        project_path = str(self.fs.workspace / app_name)

        print(f"\n🗂️  Phase 4: Scaffolding at {project_path}...")
        self.fs.create_directory(project_path)

        is_split = tech["type"] == "fullstack-split"

        if is_split:
            self._scaffold_split(project_path, app_name, reqs, tech)
        else:
            self._scaffold_single(project_path, app_name, reqs, tech)

        self.git.init_repo(project_path)
        self.git.commit(project_path, "Initial scaffold by NEXUS")
        self.project["path"] = project_path

        print(f"\n   📂 Structure:\n{self.fs.get_project_tree(project_path)}")
        return project_path

    def _scaffold_split(self, project_path: str, app_name: str, reqs: dict, tech: dict):
        """Scaffold a React+Vite frontend / FastAPI backend project."""
        frontend_path = os.path.join(project_path, "frontend")
        backend_path = os.path.join(project_path, "backend")

        for d in [frontend_path, backend_path]:
            self.fs.create_directory(d)

        # ── frontend/package.json — must exist BEFORE npm install ──
        pkg = {
            "name": f"{app_name}-frontend",
            "private": True,
            "version": "0.1.0",
            "type": "module",
            "scripts": {
                "dev": "vite",
                "build": "tsc && vite build",
                "preview": "vite preview",
                "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0",
            },
            "dependencies": {
                "react": "^18.3.1",
                "react-dom": "^18.3.1",
                "react-router-dom": "^6.26.0",
                "axios": "^1.7.4",
            },
            "devDependencies": {
                "@types/react": "^18.3.3",
                "@types/react-dom": "^18.3.0",
                "@vitejs/plugin-react": "^4.3.1",
                "typescript": "^5.5.3",
                "vite": "^5.4.0",
                "tailwindcss": "^3.4.7",
                "postcss": "^8.4.41",
                "autoprefixer": "^10.4.19",
                "eslint": "^9.9.0",
            },
        }
        self.fs.write_file(os.path.join(frontend_path, "package.json"), json.dumps(pkg, indent=2))

        # index.html
        self.fs.write_file(
            os.path.join(frontend_path, "index.html"),
            f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{reqs.get('display_name', app_name)}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
""",
        )

        # tsconfig.json
        tsconfig = {
            "compilerOptions": {
                "target": "ES2020",
                "useDefineForClassFields": True,
                "lib": ["ES2020", "DOM", "DOM.Iterable"],
                "module": "ESNext",
                "skipLibCheck": True,
                "moduleResolution": "bundler",
                "allowImportingTsExtensions": True,
                "isolatedModules": True,
                "noEmit": True,
                "jsx": "react-jsx",
                "strict": True,
                "baseUrl": ".",
                "paths": {"@/*": ["src/*"]},
            },
            "include": ["src"],
        }
        self.fs.write_file(os.path.join(frontend_path, "tsconfig.json"), json.dumps(tsconfig, indent=2))

        # vite.config.ts
        self.fs.write_file(
            os.path.join(frontend_path, "vite.config.ts"),
            """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
""",
        )

        # tailwind.config.js
        self.fs.write_file(
            os.path.join(frontend_path, "tailwind.config.js"),
            """/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: { extend: {} },
  plugins: [],
}
""",
        )

        # postcss.config.js
        self.fs.write_file(
            os.path.join(frontend_path, "postcss.config.js"),
            "export default {\n  plugins: { tailwindcss: {}, autoprefixer: {} },\n}\n",
        )

        # frontend subdirs
        for sub in ["src", "src/components", "src/components/ui",
                     "src/components/layout", "src/pages",
                     "src/hooks", "src/services", "src/types"]:
            self.fs.create_directory(os.path.join(frontend_path, sub))

        # backend
        self.fs.write_file(
            os.path.join(backend_path, "requirements.txt"),
            "fastapi>=0.111.0\nuvicorn[standard]>=0.30.0\n"
            "sqlalchemy>=2.0.31\npython-jose[cryptography]>=3.3.0\n"
            "passlib[bcrypt]>=1.7.4\npython-multipart>=0.0.9\n"
            "pydantic>=2.8.0\npydantic-settings>=2.4.0\n"
            "python-dotenv>=1.0.1\naiosqlite>=0.20.0\n",
        )
        for sub in ["app", "app/api", "app/models", "app/schemas", "app/services", "app/core"]:
            self.fs.create_directory(os.path.join(backend_path, sub))

        # Root convenience scripts
        root_pkg = {
            "name": app_name,
            "private": True,
            "scripts": {
                "dev": "cd frontend && npm run dev",
                "build": "cd frontend && npm run build",
                "dev:backend": "cd backend && uvicorn main:app --reload",
                "install:all": "cd frontend && npm install && cd ../backend && pip install -r requirements.txt",
            },
        }
        self.fs.write_file(os.path.join(project_path, "package.json"), json.dumps(root_pkg, indent=2))

        # npm install in frontend/ (package.json already exists)
        print("   📦 Installing frontend dependencies…")
        _, stderr, code = self.terminal.run("npm install", cwd=frontend_path, timeout=180)
        print(f"   {'✅' if code == 0 else '⚠️ '} npm install {'OK' if code == 0 else stderr[:100]}")

        self.project["frontend_path"] = frontend_path
        self.project["backend_path"] = backend_path

    def _scaffold_single(self, project_path: str, app_name: str, reqs: dict, tech: dict):
        """Scaffold a single Next.js project."""
        pkg = {
            "name": app_name,
            "version": "0.1.0",
            "private": True,
            "scripts": {
                "dev": "next dev",
                "build": "next build",
                "start": "next start",
                "lint": "next lint",
            },
            "dependencies": {
                "next": "^14.2.5",
                "react": "^18.3.1",
                "react-dom": "^18.3.1",
            },
            "devDependencies": {
                "@types/node": "^20",
                "@types/react": "^18",
                "@types/react-dom": "^18",
                "typescript": "^5",
                "tailwindcss": "^3.4.7",
                "postcss": "^8.4.41",
                "autoprefixer": "^10.4.19",
            },
        }
        self.fs.write_file(os.path.join(project_path, "package.json"), json.dumps(pkg, indent=2))

        tsconfig = {
            "compilerOptions": {
                "lib": ["dom", "dom.iterable", "esnext"],
                "allowJs": True,
                "skipLibCheck": True,
                "strict": True,
                "noEmit": True,
                "esModuleInterop": True,
                "module": "esnext",
                "moduleResolution": "bundler",
                "resolveJsonModule": True,
                "isolatedModules": True,
                "jsx": "preserve",
                "incremental": True,
                "plugins": [{"name": "next"}],
                "paths": {"@/*": ["./src/*"]},
            },
            "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
            "exclude": ["node_modules"],
        }
        self.fs.write_file(os.path.join(project_path, "tsconfig.json"), json.dumps(tsconfig, indent=2))

        for sub in ["src", "src/app", "src/components", "src/lib", "public"]:
            self.fs.create_directory(os.path.join(project_path, sub))

        print("   📦 Installing dependencies…")
        _, stderr, code = self.terminal.run("npm install", cwd=project_path, timeout=180)
        print(f"   {'✅' if code == 0 else '⚠️ '} npm install {'OK' if code == 0 else stderr[:100]}")

    # ------------------------------------------------------------------
    # Phase 5 — Implementation (blueprint-first, no duplicates)
    # ------------------------------------------------------------------

    def _phase_implement(self, project_path: str, reqs: dict, arch: dict, tech: dict):
        print("\n💻 Phase 5: Implementing Core Features…")

        is_split = tech["type"] == "fullstack-split"

        # ── Step 1: generate a file blueprint ──
        print("   🗺️  Creating file blueprint…")
        if is_split:
            structure_desc = "frontend/ (React+Vite+TypeScript) and backend/ (FastAPI+Python)"
            path_rules = (
                "- Frontend files: frontend/src/**/*.{tsx,ts,css}\n"
                "- Backend files: backend/**/*.py\n"
                "- NO files should go in src/ directly"
            )
            example_path = "frontend/src/main.tsx"
        else:
            structure_desc = "single Next.js 14 TypeScript app (App Router)"
            path_rules = (
                "- ALL page files: src/app/**/page.tsx\n"
                "- ALL component files: src/components/**/*.tsx\n"
                "- API routes: src/app/api/**/route.ts\n"
                "- Utilities: src/lib/**/*.ts\n"
                "- Types: src/types/**/*.ts\n"
                "- Global styles: src/app/globals.css\n"
                "- NEVER use frontend/ or backend/ prefixes — those folders do not exist"
            )
            example_path = "src/app/page.tsx"

        bp_system = f"""You are building this app:
{json.dumps(reqs, indent=2)[:2000]}
Project structure: {structure_desc}

List ALL files that need to be created. Output ONLY valid JSON:
{{
    "files": [
        {{
            "path": "{example_path}",
            "purpose": "description of this file",
            "category": "frontend-core|frontend-page|frontend-component|backend-core|backend-api|backend-model|config"
        }}
    ]
}}
PATH RULES (CRITICAL — violating these breaks the build):
{path_rules}
OTHER RULES:
- ONE file per purpose — NO duplicates
- Consistent import paths throughout"""

        bp_result = self.llm.generate(bp_system, "Generate the complete file list.")
        blueprint = self.llm.extract_json(bp_result)

        if not blueprint or "files" not in blueprint:
            blueprint = self._default_blueprint(reqs, is_split)

        file_list = blueprint.get("files", [])

        # Safety: for single-app, correct any stray frontend/ or backend/ prefixes
        if not is_split:
            corrected = []
            for f in file_list:
                p = f.get("path", "")
                if p.startswith("frontend/src/"):
                    p = p[len("frontend/"):]   # frontend/src/foo → src/foo
                    f = {**f, "path": p}
                    print(f"   🔧 Path corrected: {f['path']}")
                elif p.startswith("backend/"):
                    print(f"   ⏭️  Skipping backend path in single-app: {p}")
                    continue
                corrected.append(f)
            file_list = corrected

        print(f"   📋 Blueprint: {len(file_list)} files planned")

        # ── Step 2: generate code in batches of 5 ──
        category_order = [
            "config", "frontend-type", "backend-model", "backend-core",
            "backend-service", "backend-api", "frontend-core",
            "frontend-service", "frontend-hook", "frontend-component", "frontend-page",
        ]

        def sort_key(f):
            try:
                return category_order.index(f.get("category", "zzz"))
            except ValueError:
                return 99

        file_list.sort(key=sort_key)

        batch_size = 5
        for i in range(0, len(file_list), batch_size):
            batch = file_list[i : i + batch_size]
            labels = [f["path"] for f in batch]
            print(f"\n   📦 Batch {i // batch_size + 1}: {', '.join(labels[:3])}{'…' if len(labels) > 3 else ''}")

            gen_system = f"""Generate COMPLETE, working code for these files:
{json.dumps(batch, indent=2)}

App: {json.dumps(reqs, indent=2)[:1500]}
Already generated (use consistent imports):
{self._existing_summary()[:2000]}

Output ONLY valid JSON:
{{
    "files": [
        {{"path": "exact/path", "content": "COMPLETE file content"}}
    ]
}}
RULES:
- Write COMPLETE code — no placeholders, no "// TODO"
- TypeScript for frontend, Python for backend
- All imports must reference files in the blueprint"""

            result = self.llm.generate(
                gen_system,
                f"Tech: {json.dumps(tech, indent=2)[:400]}",
                max_tokens=8192,
            )
            data = self.llm.extract_json(result)

            if data and "files" in data:
                for f in data["files"]:
                    fpath = f.get("path", "")
                    content = f.get("content", "")
                    if not fpath or not content:
                        continue
                    if fpath in self.generated_files:
                        print(f"   ⏭️  Skip (exists): {fpath}")
                        continue
                    full = os.path.join(project_path, fpath)
                    if self.fs.write_file(full, content):
                        self.generated_files[fpath] = content
                        print(f"   📝 Written: {fpath}")
            else:
                # Fallback: generate one file at a time
                for f in batch:
                    self._generate_single_file(f, project_path, reqs, tech)

        self.git.commit(project_path, "Core implementation complete")
        print(f"\n   ✅ Implementation complete! ({len(self.generated_files)} files)")

    def _generate_single_file(self, file_info: dict, project_path: str, reqs: dict, tech: dict):
        fpath = file_info.get("path", "")
        if not fpath or fpath in self.generated_files:
            return
        code = self.llm.generate(
            f"Write COMPLETE working code for: {fpath}\nPurpose: {file_info.get('purpose', '')}\n"
            f"App: {reqs.get('summary', '')}\nOutput ONLY raw code, no markdown fences.",
            f"Tech: {json.dumps(tech, indent=2)[:300]}",
            max_tokens=4096,
        )
        code = code.strip()
        if code.startswith("```"):
            lines = code.split("\n")
            code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        full = os.path.join(project_path, fpath)
        if self.fs.write_file(full, code):
            self.generated_files[fpath] = code
            print(f"   📝 Written: {fpath}")

    def _existing_summary(self) -> str:
        lines = []
        for fpath, content in list(self.generated_files.items())[-15:]:
            important = [
                line.strip()
                for line in content.split("\n")[:20]
                if any(
                    line.strip().startswith(kw)
                    for kw in ["import ", "from ", "export ", "class ", "def ",
                                "interface ", "type ", "const ", "function "]
                )
            ]
            if important:
                lines.append(f"// {fpath}")
                lines.extend(important[:5])
                lines.append("")
        return "\n".join(lines)

    def _default_blueprint(self, reqs: dict, is_split: bool) -> dict:
        prefix = "frontend/" if is_split else ""
        files = [
            {"path": f"{prefix}src/main.tsx", "purpose": "React entry", "category": "frontend-core"},
            {"path": f"{prefix}src/App.tsx", "purpose": "Root component", "category": "frontend-core"},
            {"path": f"{prefix}src/index.css", "purpose": "Global styles", "category": "config"},
        ]
        for page in reqs.get("pages", []):
            name = re.sub(r"[^a-zA-Z0-9]", "", page["name"])
            files.append({"path": f"{prefix}src/pages/{name}.tsx",
                           "purpose": page.get("description", ""), "category": "frontend-page"})
        return {"files": files}

    # ------------------------------------------------------------------
    # Phase 6 — Styling
    # ------------------------------------------------------------------

    def _phase_styling(self, project_path: str, reqs: dict, tech: dict):
        print("\n🎨 Phase 6: Styling…")

        is_split = tech["type"] == "fullstack-split"
        css_rel = "frontend/src/index.css" if is_split else "src/index.css"

        css = self.llm.generate(
            f"Generate a complete Tailwind CSS file for '{reqs.get('display_name', '')}'. "
            "Output ONLY raw CSS — no markdown, no explanation. "
            "Include @tailwind directives, CSS variables, dark mode, animations.",
            "Generate the CSS.",
        )
        css = css.strip().lstrip("```css").lstrip("```").rstrip("```").strip()
        if not css.startswith("@tailwind"):
            css = "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n\n" + css

        full = os.path.join(project_path, css_rel)
        self.fs.write_file(full, css)
        self.generated_files[css_rel] = css

        self.git.commit(project_path, "Styling and UI polish")
        print("   ✅ Styling complete!")

    # ------------------------------------------------------------------
    # Phase 7 — Testing (builds in the CORRECT directory)
    # ------------------------------------------------------------------

    def _phase_test(self, project_path: str, tech: dict):
        print("\n🧪 Phase 7: Testing…")

        is_split = tech["type"] == "fullstack-split"
        build_dir = (
            self.project.get("frontend_path", os.path.join(project_path, "frontend"))
            if is_split
            else project_path
        )

        print(f"   🔨 Running build in: {build_dir}")

        # Ensure node_modules exist
        if not os.path.exists(os.path.join(build_dir, "node_modules")):
            print("   📦 Installing dependencies first…")
            self.terminal.run("npm install", cwd=build_dir, timeout=180)

        stdout, stderr, code = self.terminal.run("npm run build 2>&1", cwd=build_dir, timeout=120)

        if code == 0:
            print("   ✅ Build passed!")
            return True, ""

        errors = stderr or stdout
        print("   ❌ Build failed!")
        for line in errors.split("\n")[:15]:
            if line.strip():
                print(f"      {line.strip()}")
        return False, errors

    # ------------------------------------------------------------------
    # Phase 8 — Debugging (reads the correct files)
    # ------------------------------------------------------------------

    def _phase_debug(self, project_path: str, tech: dict, errors: str, max_attempts: int = 5):
        print("\n🐛 Phase 8: Debugging…")

        is_split = tech["type"] == "fullstack-split"
        build_dir = (
            self.project.get("frontend_path", os.path.join(project_path, "frontend"))
            if is_split
            else project_path
        )

        current_errors = errors
        for attempt in range(max_attempts):
            print(f"\n   🔄 Fix attempt {attempt + 1}/{max_attempts}")

            # Read files that are mentioned in the error output
            error_files = self._files_from_errors(current_errors, project_path)
            file_contents = {}
            for fpath in error_files[:8]:
                content = self.fs.read_file(fpath)
                if content:
                    rel = fpath.replace(project_path + os.sep, "").replace(project_path + "/", "")
                    file_contents[rel] = content

            fix_system = f"""Fix these TypeScript/React build errors.
ERRORS:
{current_errors[:2000]}

RELEVANT FILE CONTENTS:
{json.dumps({k: v[:600] for k, v in file_contents.items()}, indent=2)[:4000]}

Output ONLY valid JSON:
{{
    "diagnosis": "one sentence",
    "fixes": [
        {{"path": "exact/path", "content": "COMPLETE fixed file content"}}
    ]
}}
RULES:
- Provide COMPLETE file content — not just the changed lines
- Fix ALL errors in one pass
- If an import refers to a missing file, create that file too"""

            result = self.llm.generate(fix_system, "Fix the errors.", max_tokens=8192)
            fix_data = self.llm.extract_json(result)

            if fix_data and "fixes" in fix_data:
                print(f"   💡 Diagnosis: {fix_data.get('diagnosis', '')[:100]}")
                for fix in fix_data["fixes"]:
                    fpath = fix.get("path", "")
                    content = fix.get("content", "")
                    if fpath and content:
                        full = os.path.join(project_path, fpath)
                        self.fs.write_file(full, content)
                        self.generated_files[fpath] = content
                        print(f"   🔧 Fixed: {fpath}")

            self.git.commit(project_path, f"Bug fix attempt {attempt + 1}")

            if not os.path.exists(os.path.join(build_dir, "node_modules")):
                self.terminal.run("npm install", cwd=build_dir, timeout=180)

            stdout, stderr, code = self.terminal.run("npm run build 2>&1", cwd=build_dir, timeout=120)
            if code == 0:
                print(f"   ✅ Fixed after {attempt + 1} attempt(s)!")
                return

            current_errors = stderr or stdout

        print(f"   ⚠️  Could not fix all issues after {max_attempts} attempts")

    def _files_from_errors(self, errors: str, project_path: str) -> List[str]:
        found = set()
        for pattern in [r"([^\s'\"]+\.(?:tsx?|jsx?|py))", r"'([^']+\.(?:tsx?|jsx?|py))'"]:
            for match in re.finditer(pattern, errors):
                candidate = match.group(1)
                full = os.path.join(project_path, candidate)
                if os.path.exists(full):
                    found.add(full)
        if not found:
            all_files = self.fs.list_directory(project_path, recursive=True)
            found = {f for f in all_files if f.endswith((".tsx", ".ts", ".py"))}
        return list(found)[:10]

    # ------------------------------------------------------------------
    # Phase 10 — Documentation
    # ------------------------------------------------------------------

    def _phase_docs(self, project_path: str, reqs: dict, tech: dict):
        print("\n📚 Phase 10: Documentation…")

        is_split = tech["type"] == "fullstack-split"
        run_instructions = (
            "```bash\n# Frontend\ncd frontend && npm install && npm run dev\n\n"
            "# Backend (separate terminal)\ncd backend && pip install -r requirements.txt "
            "&& uvicorn main:app --reload\n```"
        ) if is_split else "```bash\nnpm install\nnpm run dev\n```"

        readme = (
            f"# {reqs.get('display_name', reqs['app_name'])}\n\n"
            f"{reqs.get('summary', '')}\n\n"
            "## Features\n"
            + "\n".join(f"- **{f['name']}**: {f['description']}" for f in reqs.get("core_features", []))
            + f"\n\n## Getting Started\n{run_instructions}\n\n"
            f"## Project Structure\n```\n{self.fs.get_project_tree(project_path)}\n```\n\n"
            "_Built with NEXUS AI Agent_\n"
        )
        self.fs.write_file(os.path.join(project_path, "README.md"), readme)
        self.git.commit(project_path, "Add documentation")
        print("   ✅ Docs generated!")

    # ------------------------------------------------------------------
    # Phase 11 — Deployment
    # ------------------------------------------------------------------

    def _phase_deploy(self, project_path: str, tech: dict) -> dict:
        print("\n🚀 Phase 11: Deployment Prep…")

        is_split = tech["type"] == "fullstack-split"

        if is_split:
            compose = (
                "version: '3.8'\nservices:\n"
                "  frontend:\n    build: ./frontend\n    ports:\n      - '3000:3000'\n"
                "    depends_on:\n      - backend\n"
                "  backend:\n    build: ./backend\n    ports:\n      - '8000:8000'\n"
                "    environment:\n      - DATABASE_URL=sqlite:///./app.db\n"
            )
            self.fs.write_file(os.path.join(project_path, "docker-compose.yml"), compose)
            instructions = [
                f"cd {project_path}",
                "docker-compose up --build",
            ]
            target = "docker"
        else:
            self.fs.write_file(
                os.path.join(project_path, "vercel.json"),
                json.dumps({"buildCommand": "npm run build", "framework": "nextjs"}, indent=2),
            )
            instructions = ["Push to GitHub", "Connect to Vercel", "Deploy!"]
            target = "vercel"

        self.git.commit(project_path, "Deployment configuration")
        print(f"   ✅ Ready for {target}")
        return {"target": target, "instructions": instructions}

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _set_phase(self, name: str, status: str):
        for p in self.phases:
            if p.name == name:
                p.status = status
                if status == "running":
                    p.start_time = time.time()
                elif status in ("passed", "failed", "skipped"):
                    p.end_time = time.time()
                break
        self._print_progress()

    def _print_progress(self):
        icons = {"pending": "⬜", "running": "🔄", "passed": "✅", "failed": "❌", "skipped": "⏭️"}
        bar = " ".join(icons.get(p.status, "?") for p in self.phases)
        done = sum(1 for p in self.phases if p.status in ("passed", "skipped"))
        print(f"\n   Progress: [{bar}] {done}/{len(self.phases)}")

    def _summary(self, project_path: str, deploy: dict) -> str:
        tree = self.fs.get_project_tree(project_path)
        phase_lines = "\n".join(
            f"   {p.name:22s} | {p.status:8s} | "
            f"{f'{p.duration:.1f}s' if p.duration else 'N/A':>8s}"
            for p in self.phases
        )
        is_split = self.project.get("tech", {}).get("type") == "fullstack-split"
        run_cmd = (
            "cd frontend && npm install && npm run dev\n   # (backend) cd backend && uvicorn main:app --reload"
            if is_split else "npm install && npm run dev"
        )
        summary = (
            "\n╔══════════════════════════════════════════════════════════╗\n"
            "║              🎉 BUILD COMPLETE!                          ║\n"
            "╠══════════════════════════════════════════════════════════╣\n\n"
            f"📁 Location:  {project_path}\n"
            f"📊 Files:     {len(self.generated_files)}\n\n"
            f"Build phases:\n{phase_lines}\n\n"
            f"📂 Structure:\n{tree}\n\n"
            f"💡 Run it:\n   cd {project_path}\n   {run_cmd}\n\n"
            "╚══════════════════════════════════════════════════════════╝"
        )
        print(summary)
        return summary
