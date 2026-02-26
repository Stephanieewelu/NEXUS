"""
build_orchestrator.py  -  Master controller for the NEXUS app-building pipeline.

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

        # LLM health tracking — abort early when the API is consistently failing
        self._llm_calls = 0
        self._llm_failures = 0

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def start_build(self, user_description: str) -> str:
        print("\n" + "=" * 60)
        print("  🏗️  NEXUS APP BUILDER  -  Starting New Build")
        print("=" * 60)

        try:
            self._set_phase("requirements", "running")
            reqs = self._phase_requirements(user_description)
            self._set_phase("requirements", "passed")

            # Early abort: if LLM returned no features AND no pages, the API is dead
            n_features = len(reqs.get("core_features", []))
            n_pages = len(reqs.get("pages", []))
            if n_features == 0 and n_pages == 0:
                raise RuntimeError(
                    "Phase 1 produced 0 features and 0 pages - the LLM API is likely "
                    "rate-limited or unavailable. Wait a few minutes and try again."
                )

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

            build_ok = test_ok
            if not test_ok:
                self._set_phase("debugging", "running")
                build_ok = self._phase_debug(project_path, tech, test_errors)
                self._set_phase("debugging", "passed" if build_ok else "failed")
            else:
                self._set_phase("debugging", "passed")

            self.project["build_ok"] = build_ok  # propagate to summary

            self._set_phase("optimization", "running")
            self._phase_optimize(project_path, tech)
            self._set_phase("optimization", "passed")

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
    # LLM health helpers
    # ------------------------------------------------------------------

    def _track_llm_result(self, result: str) -> str:
        """Track whether an LLM call succeeded or returned empty."""
        self._llm_calls += 1
        if not result or not result.strip():
            self._llm_failures += 1
        return result

    def _check_llm_health(self, context: str = ""):
        """Raise RuntimeError if the LLM is consistently failing (>80% empty after 4+ calls)."""
        if self._llm_calls >= 4 and self._llm_failures / self._llm_calls > 0.8:
            raise RuntimeError(
                f"LLM is consistently failing ({self._llm_failures}/{self._llm_calls} calls returned empty). "
                f"The API is likely rate-limited or unavailable. "
                f"Context: {context}. Wait a few minutes and try again."
            )

    # ------------------------------------------------------------------
    # Phase 1  -  Requirements
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

        result = self._track_llm_result(
            self.llm.generate(system, f"Build this app:\n{description}")
        )
        reqs = self.llm.extract_json(result)

        # Derive app_name from display_name first (avoids LLM slug typos like "websiite")
        display = reqs.get("display_name", "")
        if display:
            derived = re.sub(r"[^a-z0-9]+", "-", display.lower()).strip("-")
            if derived:
                reqs["app_name"] = derived

        # Final sanitise: strip any remaining bad chars
        name = re.sub(r"[^a-z0-9-]", "-", reqs.get("app_name", "nexus-app").lower()).strip("-")
        reqs["app_name"] = name or "nexus-app"

        self.project["requirements"] = reqs
        print(f"   ✅ App: {reqs.get('display_name', name)}")
        print(f"   ✅ Features: {len(reqs.get('core_features', []))}")
        print(f"   ✅ Pages: {len(reqs.get('pages', []))}")
        return reqs

    # ------------------------------------------------------------------
    # Phase 2  -  Architecture
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
{"Python/FastAPI was detected  -  fullstack-split is allowed." if python_requested else
 "No Python backend was requested  -  you MUST use structure=single."}"""

        result = self._track_llm_result(
            self.llm.generate(system, json.dumps(reqs, indent=2)[:3000])
        )
        arch = self.llm.extract_json(result)

        # Safety: enforce "single" if Python was not requested
        if not python_requested and arch.get("structure") == "fullstack-split":
            print("   ⚠️  LLM chose fullstack-split without Python request  -  overriding to single")
            arch["structure"] = "single"
            arch["frontend_framework"] = "next.js"
            arch["backend_framework"] = "next.js-api"

        self.project["architecture"] = arch
        print(f"   ✅ Structure: {arch.get('structure', '?')}")
        print(f"   ✅ Frontend: {arch.get('frontend_framework', '?')}")
        print(f"   ✅ Backend: {arch.get('backend_framework', '?')}")
        return arch

    # ------------------------------------------------------------------
    # Phase 3  -  Tech stack
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
    # Phase 4  -  Scaffolding
    # ------------------------------------------------------------------

    def _phase_scaffold(self, reqs: dict, arch: dict, tech: dict) -> str:
        app_name = reqs["app_name"]
        project_path = str(self.fs.workspace / app_name)

        print(f"\n🗂️  Phase 4: Scaffolding at {project_path}...")

        # Clean stale source files from any previous build of the same app name.
        # We keep node_modules (saves re-running npm install) but wipe everything else.
        import shutil as _shutil
        if os.path.isdir(project_path):
            is_split_existing = tech["type"] == "fullstack-split"
            # Directories to wipe for a clean slate
            if is_split_existing:
                stale_dirs = ["frontend/src", "frontend/public", "backend"]
                stale_files = ["frontend/index.html", "frontend/vite.config.ts",
                               "frontend/tailwind.config.js", "frontend/postcss.config.js"]
            else:
                stale_dirs = ["src", "public"]
                stale_files = [
                    "tailwind.config.ts", "tailwind.config.js",
                    "postcss.config.mjs", "postcss.config.js",
                    "next.config.mjs", "next.config.js",
                    "vercel.json", "tsconfig.json",
                ]
            cleaned = 0
            for d in stale_dirs:
                full_d = os.path.join(project_path, d)
                if os.path.isdir(full_d):
                    _shutil.rmtree(full_d)
                    cleaned += 1
            for f in stale_files:
                full_f = os.path.join(project_path, f)
                if os.path.isfile(full_f):
                    os.remove(full_f)
                    cleaned += 1
            if cleaned:
                print(f"   🧹 Cleaned {cleaned} stale item(s) from previous build")
            # Also reset generated_files to avoid stale path cache
            self.generated_files.clear()

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

        # ── frontend/package.json  -  must exist BEFORE npm install ──
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
                "axios": "^1.7.4",
                "clsx": "^2.1.1",
                "lucide-react": "^0.400.0",
                "tailwind-merge": "^2.4.0",
                "zod": "^3.23.8",
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

        # Tailwind config
        self.fs.write_file(
            os.path.join(project_path, "tailwind.config.ts"),
            'import type { Config } from "tailwindcss";\n\n'
            "const config: Config = {\n"
            '  content: [\n    "./src/**/*.{js,ts,jsx,tsx,mdx}",\n  ],\n'
            "  theme: { extend: {} },\n"
            "  plugins: [],\n"
            "};\n"
            "export default config;\n",
        )

        # PostCSS config
        self.fs.write_file(
            os.path.join(project_path, "postcss.config.mjs"),
            "/** @type {import('postcss-load-config').Config} */\n"
            "const config = {\n"
            "  plugins: {\n"
            "    tailwindcss: {},\n"
            "    autoprefixer: {},\n"
            "  },\n"
            "};\n"
            "export default config;\n",
        )

        # next.config.js (minimal)
        self.fs.write_file(
            os.path.join(project_path, "next.config.mjs"),
            "/** @type {import('next').NextConfig} */\n"
            "const nextConfig = {};\n"
            "export default nextConfig;\n",
        )

        print("   📦 Installing dependencies…")
        _, stderr, code = self.terminal.run("npm install", cwd=project_path, timeout=180)
        print(f"   {'✅' if code == 0 else '⚠️ '} npm install {'OK' if code == 0 else stderr[:100]}")

    # ------------------------------------------------------------------
    # Phase 5  -  Implementation (blueprint-first, no duplicates)
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
                "- REQUIRED: src/app/layout.tsx  ← root layout (MUST be included, build fails without it)\n"
                "- ALL page files: src/app/**/page.tsx\n"
                "- ALL component files: src/components/**/*.tsx\n"
                "- API routes: src/app/api/**/route.ts\n"
                "- Utilities: src/lib/**/*.ts\n"
                "- Types: src/types/**/*.ts\n"
                "- Global styles: src/app/globals.css\n"
                "- NEVER create a pages/ directory  -  this is App Router, not Pages Router\n"
                "- NEVER use frontend/ or backend/ prefixes  -  those folders do not exist"
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
PATH RULES (CRITICAL  -  violating these breaks the build):
{path_rules}
OTHER RULES:
- ONE file per purpose  -  NO duplicates
- Consistent import paths throughout"""

        bp_result = self._track_llm_result(
            self.llm.generate(bp_system, "Generate the complete file list.")
        )
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

        # Fix #1: redirect src/app/components/ → src/components/ and deduplicate
        # Fix #2: enforce single canonical CSS file (src/app/globals.css)
        if not is_split:
            _APP_ONLY = {"/page.tsx", "/layout.tsx", "/route.ts", "/globals.css", "/error.tsx",
                         "/loading.tsx", "/not-found.tsx", "/template.tsx"}
            cleaned = []
            seen_paths: set = set()
            for f in file_list:
                p = f.get("path", "")
                # Redirect component files placed inside src/app/components/
                if p.startswith("src/app/components/"):
                    p = "src/components/" + p[len("src/app/components/"):]
                    f = {**f, "path": p}
                    print(f"   🔧 Component redirected to src/components/: {f['path']}")
                # Drop extra CSS files; keep only src/app/globals.css
                if p.endswith(".css") and p != "src/app/globals.css":
                    print(f"   ⏭️  CSS dedup: dropping {p} (canonical: src/app/globals.css)")
                    continue
                # Deduplicate by path
                if p in seen_paths:
                    print(f"   ⏭️  Dedup: skipping duplicate {p}")
                    continue
                seen_paths.add(p)
                cleaned.append(f)
            file_list = cleaned

        # Safety: for Next.js App Router, layout.tsx is mandatory  -  inject if missing
        if not is_split:
            has_layout = any(f.get("path") == "src/app/layout.tsx" for f in file_list)
            if not has_layout:
                file_list.insert(0, {
                    "path": "src/app/layout.tsx",
                    "purpose": "Root layout (required by Next.js App Router)",
                    "category": "frontend-core",
                })
                print("   🔧 Injected required: src/app/layout.tsx")

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

        batch_size = 3   # smaller batches = fewer tokens per call = less TPM pressure
        for i in range(0, len(file_list), batch_size):
            # Health gate: abort if LLM is consistently failing
            self._check_llm_health(f"Phase 5 batch {i // batch_size + 1}")

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
- Write COMPLETE code  -  no placeholders, no "// TODO"
- TypeScript for frontend, Python for backend
- All imports must reference files in the blueprint
- NEVER import database packages anywhere (pg, mysql2, mongodb, prisma, drizzle-orm,
  sequelize, typeorm, sqlite3, better-sqlite3, etc.)  -  use hardcoded mock data arrays
- NEVER import from '../lib/db', '../models/', '../services/db' or any database utility
  in pages or components  -  define any needed data as a const array directly in the file
- Components that use useState/useEffect MUST have "use client" as the very first line
- Page files (page.tsx) must be Server Components by default  -  move interactivity to child components
- Data for pages must come from hardcoded const arrays defined in the same file, NOT from DB imports"""

            result = self._track_llm_result(
                self.llm.generate(
                    gen_system,
                    f"Tech: {json.dumps(tech, indent=2)[:400]}",
                    max_tokens=6000,
                )
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

        # Post-batch disk guarantee: src/app/layout.tsx MUST exist AND be valid
        if not is_split:
            layout_disk = os.path.join(project_path, "src", "app", "layout.tsx")
            app_title = reqs.get("display_name", "App")
            app_desc = reqs.get("summary", "Built with NEXUS")
            _hardcoded_layout = (
                'import type { Metadata } from "next";\n'
                'import "./globals.css";\n\n'
                'export const metadata: Metadata = {\n'
                f'  title: "{app_title}",\n'
                f'  description: "{app_desc}",\n'
                "};\n\n"
                "export default function RootLayout({\n"
                "  children,\n"
                "}: Readonly<{\n"
                "  children: React.ReactNode;\n"
                "}>) {\n"
                "  return (\n"
                '    <html lang="en">\n'
                "      <body>{children}</body>\n"
                "    </html>\n"
                "  );\n"
                "}\n"
            )

            need_write = False
            if not os.path.exists(layout_disk):
                print("   🔧 Post-batch safety: writing src/app/layout.tsx (was missing)")
                need_write = True
            else:
                # Validate content: must contain 'export default' to be a valid module
                existing = self.fs.read_file(layout_disk) or ""
                if "export default" not in existing:
                    print("   🔧 Post-batch safety: layout.tsx is invalid (no export default) — rewriting")
                    need_write = True
                elif len(existing.strip()) < 50:
                    print("   🔧 Post-batch safety: layout.tsx is too short/empty — rewriting")
                    need_write = True

            if need_write:
                self.fs.write_file(layout_disk, _hardcoded_layout)
                self.generated_files["src/app/layout.tsx"] = _hardcoded_layout

            # Also ensure globals.css exists (layout.tsx imports it)
            globals_disk = os.path.join(project_path, "src", "app", "globals.css")
            if not os.path.exists(globals_disk):
                print("   🔧 Post-batch safety: writing src/app/globals.css (was missing)")
                default_css = (
                    "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n\n"
                    ":root {\n  --foreground: #171717;\n  --background: #ffffff;\n}\n\n"
                    "body {\n  color: var(--foreground);\n  background: var(--background);\n}\n"
                )
                self.fs.write_file(globals_disk, default_css)
                self.generated_files["src/app/globals.css"] = default_css

        # Phase 5.5a — 'use client' enforcement (no LLM calls)
        # Any file using React hooks MUST be a Client Component.
        # This is the #1 recurring Next.js App Router build error.
        if not is_split:
            n_client = self._fix_client_directives(project_path)
            if n_client:
                print(f"   ✅ Added 'use client' to {n_client} hook-using file(s)")

        # Phase 5.5b — import path validation + auto-fix (no LLM calls)
        if not is_split:
            bad = self._validate_imports(project_path)
            if bad:
                print(f"\n   ⚠️  {len(bad)} broken import(s) detected — attempting auto-fix...")
                n_fixed = self._fix_broken_imports(project_path, bad)
                remaining = self._validate_imports(project_path)
                if remaining:
                    print(f"   ⚠️  {len(remaining)} import(s) still broken after auto-fix:")
                    for b in remaining[:10]:
                        print(f"      {b}")
                else:
                    print(f"   ✅ All broken imports fixed ({n_fixed} file(s) updated)")

        self.git.commit(project_path, "Core implementation complete")
        print(f"\n   ✅ Implementation complete! ({len(self.generated_files)} files)")

    def _generate_single_file(self, file_info: dict, project_path: str, reqs: dict, tech: dict):
        fpath = file_info.get("path", "")
        if not fpath or fpath in self.generated_files:
            return
        code = self._track_llm_result(
            self.llm.generate(
                f"Write COMPLETE working code for: {fpath}\nPurpose: {file_info.get('purpose', '')}\n"
                f"App: {reqs.get('summary', '')}\nOutput ONLY raw code, no markdown fences.",
                f"Tech: {json.dumps(tech, indent=2)[:300]}",
                max_tokens=4096,
            )
        )
        code = code.strip()
        # CRITICAL: never write empty files — this overwrites valid scaffold files
        if not code:
            print(f"   ⚠️  LLM returned empty for {fpath} — skipping (will not overwrite)")
            return
        if code.startswith("```"):
            lines = code.split("\n")
            code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        if not code.strip():
            print(f"   ⚠️  LLM returned only fences for {fpath} — skipping")
            return
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
        if is_split:
            prefix = "frontend/"
            files = [
                {"path": f"{prefix}src/main.tsx", "purpose": "React entry", "category": "frontend-core"},
                {"path": f"{prefix}src/App.tsx", "purpose": "Root component", "category": "frontend-core"},
                {"path": f"{prefix}src/index.css", "purpose": "Global styles", "category": "config"},
            ]
            for page in reqs.get("pages", []):
                name = re.sub(r"[^a-zA-Z0-9]", "", page["name"])
                files.append({"path": f"{prefix}src/pages/{name}.tsx",
                               "purpose": page.get("description", ""), "category": "frontend-page"})
        else:
            # Next.js 14 App Router  -  layout.tsx is mandatory
            files = [
                {"path": "src/app/layout.tsx", "purpose": "Root layout (required by App Router)", "category": "frontend-core"},
                {"path": "src/app/globals.css", "purpose": "Global styles", "category": "config"},
                {"path": "src/app/page.tsx", "purpose": "Home page", "category": "frontend-page"},
            ]
            for page in reqs.get("pages", []):
                name = re.sub(r"[^a-zA-Z0-9-]", "-", page["name"]).lower().strip("-")
                if name and name != "home":
                    files.append({
                        "path": f"src/app/{name}/page.tsx",
                        "purpose": page.get("description", ""),
                        "category": "frontend-page",
                    })
        return {"files": files}

    def _validate_imports(self, project_path: str) -> list:
        """Scan all .ts/.tsx files for relative imports that don't resolve to a real file."""
        broken = []
        skip_dirs = {"node_modules", ".git", ".next", "dist", "build"}
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fname in files:
                if not fname.endswith((".tsx", ".ts")):
                    continue
                fpath = os.path.join(root, fname)
                content = self.fs.read_file(fpath) or ""
                for imp in re.findall(r'from\s+["\'](\.[^"\']+)["\']', content):
                    base = os.path.dirname(fpath)
                    resolved = os.path.normpath(os.path.join(base, imp))
                    exists = any(
                        os.path.exists(resolved + ext)
                        for ext in ["", ".ts", ".tsx", "/index.ts", "/index.tsx"]
                    )
                    if not exists:
                        rel_file = fpath.replace(project_path + os.sep, "")
                        broken.append(f"{rel_file}: missing '{imp}'")
        return broken

    def _fix_broken_imports(self, project_path: str, broken: list) -> int:
        """
        Auto-fix common broken import patterns without any LLM calls.

        Handles:
        - '../../layout' or '../layout' in page files (wrong in App Router — remove)
        - Missing components that have a close-named file in src/components/
        - Missing ./header, ./footer, ./nav stubs (create minimal component)

        Returns the number of source files modified.
        """
        # Parse broken list → {rel_path: [missing_import, ...]}
        by_file: dict = {}
        for entry in broken:
            m = re.match(r"(.+): missing '([^']+)'", entry.replace("\\", "/"))
            if m:
                rel, imp = m.group(1).strip(), m.group(2).strip()
                by_file.setdefault(rel, []).append(imp)

        comp_dir = os.path.join(project_path, "src", "components")
        # Build a lookup: slug → actual filename (without .tsx)
        comp_slugs: dict = {}
        if os.path.isdir(comp_dir):
            for f in os.listdir(comp_dir):
                if f.endswith(".tsx"):
                    slug = f[:-4].lower().replace("-", "").replace("_", "")
                    comp_slugs[slug] = f[:-4]

        modified = 0
        for rel_path, missing_imports in by_file.items():
            fpath = os.path.join(project_path, rel_path.replace("/", os.sep))
            content = self.fs.read_file(fpath)
            if not content:
                continue
            original = content

            for imp in missing_imports:
                imp_basename = imp.split("/")[-1]  # e.g. "image-generation-form"

                # ── Rule 1: Remove App Router layout re-imports ──
                # Pages NEVER import layout manually; Next.js applies it automatically
                if re.search(r"[/\\]layout$", imp) or imp in ("../layout", "../../layout"):
                    content = re.sub(
                        r'import\s+\S+\s+from\s+["\']' + re.escape(imp) + r'["\'];\s*\n?',
                        "", content,
                    )
                    # Unwrap <Layout>...</Layout> if present
                    content = re.sub(r"<Layout[^>]*>([\s\S]*?)</Layout>", r"\1", content)
                    print(f"   🔧 Auto-fix: removed layout re-import in {rel_path}")
                    continue

                # ── Rule 2: Remap missing component to nearest match ──
                if "component" in imp or "/components/" in imp or imp.startswith("../../"):
                    slug = imp_basename.lower().replace("-", "").replace("_", "")
                    match_name = comp_slugs.get(slug)
                    if not match_name:
                        # Partial match: find a component whose slug starts the same way
                        for cs, cn in comp_slugs.items():
                            if slug[:6] in cs or cs[:6] in slug:
                                match_name = cn
                                break
                    if match_name:
                        # Compute correct relative path from the source file
                        rel_comp = os.path.relpath(
                            os.path.join(comp_dir, match_name),
                            os.path.dirname(fpath),
                        ).replace("\\", "/")
                        if not rel_comp.startswith("."):
                            rel_comp = "./" + rel_comp
                        content = content.replace(f'"{imp}"', f'"{rel_comp}"')
                        content = content.replace(f"'{imp}'", f"'{rel_comp}'")
                        print(f"   🔧 Auto-fix: {imp} → {rel_comp} in {rel_path}")
                        continue
                    # No match — create minimal stub
                    comp_name = "".join(w.capitalize() for w in re.split(r"[-_]", imp_basename))
                    stub = f'"use client";\nexport default function {comp_name}() {{ return <div className="{imp_basename}"></div>; }}\n'
                    stub_path = os.path.join(comp_dir, imp_basename + ".tsx")
                    self.fs.write_file(stub_path, stub)
                    # Update import to new correct path
                    rel_comp = os.path.relpath(stub_path, os.path.dirname(fpath)).replace("\\", "/")
                    if not rel_comp.startswith("."):
                        rel_comp = "./" + rel_comp
                    content = content.replace(f'"{imp}"', f'"{rel_comp}"')
                    content = content.replace(f"'{imp}'", f"'{rel_comp}'")
                    print(f"   🔧 Auto-fix: created stub {imp_basename}.tsx")
                    continue

                # ── Rule 3: Missing ./header, ./footer etc. in layout.tsx → create stub ──
                if imp.startswith("./") and "/" not in imp[2:]:
                    stub_name = imp[2:]  # e.g. "header"
                    stub_path = os.path.join(os.path.dirname(fpath), stub_name + ".tsx")
                    if not os.path.exists(stub_path):
                        comp_name = stub_name.capitalize()
                        stub = f'export default function {comp_name}() {{ return <div className="{stub_name}"></div>; }}\n'
                        self.fs.write_file(stub_path, stub)
                        print(f"   🔧 Auto-fix: created stub {stub_name}.tsx")
                    continue

                # ── Rule 4: Missing lib/, models/, services/, utils/, hooks/ file → create stub ──
                # Covers patterns like: '../lib/db', '../models/portfolio', '../services/api'
                _util_dirs = {"lib", "models", "services", "hooks", "utils", "types", "helpers"}
                imp_parts = imp.replace("\\", "/").split("/")
                if any(p in _util_dirs for p in imp_parts):
                    base_dir = os.path.dirname(fpath)
                    resolved = os.path.normpath(os.path.join(base_dir, imp))
                    # Only create if neither .ts nor .tsx exists
                    if not os.path.exists(resolved + ".ts") and not os.path.exists(resolved + ".tsx"):
                        stub_basename = imp_basename
                        low = stub_basename.lower()
                        # DB/query stubs: return empty results to satisfy types
                        if any(kw in low for kw in ["db", "database", "prisma", "drizzle", "sql", "query", "pool"]):
                            stub_content = (
                                "// Auto-generated mock DB stub — no external DB needed for build\n"
                                "export async function query(_sql: string, _params?: unknown[]) {\n"
                                "  return [];\n"
                                "}\n"
                                "export const db = {\n"
                                "  query: async (_sql: string, _params?: unknown[]) => ({ rows: [] as unknown[] }),\n"
                                "};\n"
                                "export default db;\n"
                            )
                        elif any(kw in low for kw in ["model", "schema", "entity"]):
                            comp_name = "".join(w.capitalize() for w in re.split(r"[-_/]", stub_basename) if w)
                            stub_content = (
                                f"// Auto-generated model stub\n"
                                f"export interface {comp_name} {{\n"
                                f"  id: string;\n"
                                f"  createdAt: Date;\n"
                                f"}}\n"
                                f"export const mock{comp_name}s: {comp_name}[] = [];\n"
                                f"export default mock{comp_name}s;\n"
                            )
                        else:
                            fn_name = "".join(w.capitalize() for w in re.split(r"[-_]", stub_basename) if w)
                            stub_content = (
                                f"// Auto-generated utility stub for {imp}\n"
                                f"export function get{fn_name}() {{ return []; }}\n"
                                f"export default get{fn_name};\n"
                            )
                        os.makedirs(os.path.dirname(resolved + ".ts"), exist_ok=True)
                        self.fs.write_file(resolved + ".ts", stub_content)
                        print(f"   🔧 Auto-fix: created lib/model stub for '{imp}'")
                    continue

            if content != original:
                self.fs.write_file(fpath, content)
                modified += 1

        return modified

    def _fix_client_directives(self, project_path: str) -> int:
        """
        Add 'use client' to any .tsx/.ts file that uses React hooks but is missing the directive.
        This is the most common Next.js App Router build error: hooks in Server Components.
        API route files (route.ts) are skipped — they don't need 'use client'.
        Returns the number of files fixed.
        """
        _HOOKS = re.compile(
            r'\b(useState|useEffect|useContext|useReducer|useRef|useCallback|useMemo'
            r'|useLayoutEffect|useImperativeHandle|useTransition|useDeferredValue)\s*\('
        )
        skip_dirs = {"node_modules", ".git", ".next", "dist", "build"}
        fixed = 0
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fname in files:
                if not fname.endswith((".tsx", ".ts")):
                    continue
                fpath = os.path.join(root, fname)
                content = self.fs.read_file(fpath) or ""
                rel = fpath.replace(project_path + os.sep, "").replace("\\", "/")
                # Skip API route handlers — they run server-side, no 'use client' needed
                if fname == "route.ts" and "/api/" in rel:
                    continue
                # Already has the directive?
                if '"use client"' in content or "'use client'" in content:
                    continue
                # Uses hooks?
                if _HOOKS.search(content):
                    content = '"use client";\n' + content
                    self.fs.write_file(fpath, content)
                    self.generated_files[rel] = content
                    print(f"   🔧 'use client': added to {rel}")
                    fixed += 1
        return fixed

    # ------------------------------------------------------------------
    # Phase 6  -  Styling
    # ------------------------------------------------------------------

    def _phase_styling(self, project_path: str, reqs: dict, tech: dict):
        print("\n🎨 Phase 6: Styling…")

        is_split = tech["type"] == "fullstack-split"
        # For Next.js App Router the canonical CSS file is src/app/globals.css.
        # For Vite/split it lives at frontend/src/index.css.
        css_rel = "frontend/src/index.css" if is_split else "src/app/globals.css"

        css = self._track_llm_result(
            self.llm.generate(
                f"Generate a complete Tailwind CSS file for '{reqs.get('display_name', '')}'. "
                "Output ONLY raw CSS  -  no markdown, no explanation. "
                "Include @tailwind directives, CSS variables, dark mode, animations.",
                "Generate the CSS.",
            )
        )
        css = css.strip().lstrip("```css").lstrip("```").rstrip("```").strip()

        # Fallback: if LLM returned empty, use minimal valid Tailwind CSS
        if not css:
            print("   ⚠️  LLM returned empty CSS — using Tailwind defaults")
            css = (
                "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n\n"
                ":root {\n  --foreground: #171717;\n  --background: #ffffff;\n}\n\n"
                "body {\n  color: var(--foreground);\n  background: var(--background);\n}\n"
            )
        elif not css.startswith("@tailwind"):
            css = "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n\n" + css

        full = os.path.join(project_path, css_rel)
        self.fs.write_file(full, css)
        self.generated_files[css_rel] = css

        # Remove stray duplicate CSS files that the LLM may have written
        if not is_split:
            for stray in ["src/index.css", "src/styles/globals.css", "src/styles/index.css"]:
                stray_full = os.path.join(project_path, stray)
                if os.path.exists(stray_full):
                    os.remove(stray_full)
                    print(f"   🗑️  Removed stray CSS: {stray}")

        self.git.commit(project_path, "Styling and UI polish")
        print("   ✅ Styling complete!")

    # ------------------------------------------------------------------
    # Phase 7  -  Testing (builds in the CORRECT directory)
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
    # Phase 8  -  Debugging (reads the correct files)
    # ------------------------------------------------------------------

    def _phase_debug(self, project_path: str, tech: dict, errors: str, max_attempts: int = 5):
        print("\n🐛 Phase 8: Debugging…")

        is_split = tech["type"] == "fullstack-split"
        build_dir = (
            self.project.get("frontend_path", os.path.join(project_path, "frontend"))
            if is_split
            else project_path
        )

        # Named-error pre-check: unresolvable external DB/native modules in API routes.
        # When the LLM imports pg, mysql2, mongodb, etc. the build fails with
        # "Module not found: Can't resolve 'X'".  Rewrite every affected route to
        # use inline mock data so no external package is needed.
        _DB_PACKAGES = {"pg", "mysql2", "mongodb", "prisma", "@prisma/client",
                        "drizzle-orm", "sequelize", "typeorm", "sqlite3", "better-sqlite3"}
        _mod_not_found = re.findall(r"Can't resolve '([^']+)'", errors)
        _missing_db = [m for m in _mod_not_found if m.split("/")[0] in _DB_PACKAGES]
        if _missing_db:
            print(f"   🔧 Pre-fix: replacing DB imports ({', '.join(_missing_db)}) with mock data")
            # Find all API route files and strip the DB imports, replacing with mock arrays
            api_dir = os.path.join(project_path, "src", "app", "api")
            if os.path.isdir(api_dir):
                for root_dir, _dirs, files in os.walk(api_dir):
                    for fname in files:
                        if fname == "route.ts":
                            fpath = os.path.join(root_dir, fname)
                            content = self.fs.read_file(fpath) or ""
                            if any(pkg in content for pkg in _missing_db):
                                # Ask LLM to rewrite just this one file with mock data
                                rel = fpath.replace(project_path + os.sep, "").replace(project_path + "/", "")
                                mock_fix = self._track_llm_result(
                                    self.llm.generate(
                                        f"Rewrite this Next.js API route to use hardcoded mock data "
                                        f"instead of any database package. Output ONLY the raw TypeScript "
                                        f"file content, no markdown fences.\n\nCURRENT FILE ({rel}):\n{content[:3000]}",
                                        "Rewrite with mock data.",
                                        max_tokens=4096,
                                    )
                                )
                                mock_fix = mock_fix.strip().lstrip("```typescript").lstrip("```ts").lstrip("```").rstrip("```").strip()
                                if mock_fix and len(mock_fix) > 20:
                                    self.fs.write_file(fpath, mock_fix)
                                    print(f"   🔧 Pre-fix rewritten: {rel}")

        # Named-error pre-check: pages/components importing from lib/db, models/, etc.
        # These are non-installable relative modules that the build can't resolve.
        # Run the same auto-fix logic we use at Phase 5.5 so the LLM loop isn't needed.
        if not is_split and "Module not found" in errors:
            _missing_relative = re.findall(r"Module not found: Can't resolve '(\.\.?/[^']+)'", errors)
            if _missing_relative:
                print(f"   🔧 Pre-fix: resolving missing relative modules via auto-stub")
                broken_entries = []
                # Build broken list format expected by _fix_broken_imports
                skip_dirs = {"node_modules", ".git", ".next"}
                for root_dir, dirs, files in os.walk(project_path):
                    dirs[:] = [d for d in dirs if d not in skip_dirs]
                    for fname in files:
                        if not fname.endswith((".tsx", ".ts")):
                            continue
                        fpath = os.path.join(root_dir, fname)
                        content = self.fs.read_file(fpath) or ""
                        for imp in re.findall(r'from\s+["\'](\.[^"\']+)["\']', content):
                            if imp in _missing_relative:
                                rel_file = fpath.replace(project_path + os.sep, "").replace(project_path + "/", "")
                                broken_entries.append(f"{rel_file}: missing '{imp}'")
                if broken_entries:
                    self._fix_broken_imports(project_path, broken_entries)

        # Named-error pre-check: hooks in Server Components → add 'use client'
        # "You're importing a component that needs useState" is a top-3 build error.
        if not is_split and ("useState" in errors or "useEffect" in errors or "use client" in errors):
            n_client = self._fix_client_directives(project_path)
            if n_client:
                print(f"   🔧 Pre-fix: added 'use client' to {n_client} file(s)")

        # Named-error pre-check: missing root layout in Next.js App Router
        # The LLM habitually creates pages/_app.tsx instead of src/app/layout.tsx,
        # so we detect and fix this before any LLM round-trip.
        if "doesn't have a root layout" in errors or "does not have a root layout" in errors:
            layout_path = os.path.join(project_path, "src", "app", "layout.tsx")
            if not os.path.exists(layout_path):
                print("   🔧 Pre-fix: creating missing src/app/layout.tsx")
                layout_content = (
                    'import type { Metadata } from "next";\n'
                    'import "./globals.css";\n\n'
                    'export const metadata: Metadata = {\n'
                    '  title: "App",\n'
                    '  description: "Built with NEXUS",\n'
                    "};\n\n"
                    "export default function RootLayout({\n"
                    "  children,\n"
                    "}: {\n"
                    "  children: React.ReactNode;\n"
                    "}) {\n"
                    "  return (\n"
                    '    <html lang="en">\n'
                    "      <body>{children}</body>\n"
                    "    </html>\n"
                    "  );\n"
                    "}\n"
                )
                self.fs.write_file(layout_path, layout_content)
                self.generated_files["src/app/layout.tsx"] = layout_content

        current_errors = errors
        seen_error_hashes: set = set()
        prev_fixes: set = set()  # track which files we've already rewritten (Fix #8 cache)

        for attempt in range(max_attempts):
            # Health gate: don't burn rate limit on LLM calls if API is dead
            try:
                self._check_llm_health(f"Phase 8 attempt {attempt + 1}")
            except RuntimeError as e:
                print(f"   ⚠️  {e}")
                print("   ⏹️  Skipping remaining debug attempts to conserve API budget")
                break

            print(f"\n   🔄 Fix attempt {attempt + 1}/{max_attempts}")

            # Fix #3: detect identical errors across attempts  → switch to aggressive strategy
            err_hash = hash(current_errors[:500])
            stuck = err_hash in seen_error_hashes
            seen_error_hashes.add(err_hash)

            # Read files that are mentioned in the error output
            error_files = self._files_from_errors(current_errors, project_path)
            file_contents = {}
            for fpath in error_files[:8]:
                content = self.fs.read_file(fpath)
                if content:
                    rel = fpath.replace(project_path + os.sep, "").replace(project_path + "/", "")
                    # Fix #8: send more context when stuck, standard snippet otherwise
                    file_contents[rel] = content if stuck else content[:800]

            if stuck:
                print("   ⚠️  Same error repeated  -  switching to aggressive rewrite strategy")
                extra_rules = (
                    "IMPORTANT: previous attempts produced the same error. "
                    "You MUST take a completely different approach. "
                    "Rewrite all affected files from scratch with minimal dependencies.\n"
                )
            else:
                extra_rules = ""

            fix_system = f"""Fix these TypeScript/React build errors.
ERRORS:
{current_errors[:2000]}

RELEVANT FILE CONTENTS (full content when stuck):
{json.dumps({k: v for k, v in file_contents.items()}, indent=2)[:5000]}

Output ONLY valid JSON:
{{
    "diagnosis": "one sentence",
    "fixes": [
        {{"path": "exact/path", "content": "COMPLETE fixed file content"}}
    ]
}}
RULES:
{extra_rules}- Provide COMPLETE file content  -  not just the changed lines
- Fix ALL errors in one pass
- If an import refers to a missing file, create that file too
- This is a Next.js 14 APP ROUTER project (src/app/ directory)
- components live in src/components/ NOT src/app/components/
- NEVER create files inside pages/  -  that is the Pages Router and does NOT apply here
- If the error is "doesn't have a root layout", create src/app/layout.tsx (not pages/_app.tsx)
- NEVER import database packages (pg, mysql2, mongodb, prisma, drizzle-orm, etc.) in API routes
   -  use hardcoded mock data arrays instead
- Components using useState/useEffect MUST start with "use client" as the very first line"""

            result = self._track_llm_result(
                self.llm.generate(fix_system, "Fix the errors.", max_tokens=6000)
            )
            fix_data = self.llm.extract_json(result)

            # If LLM returned empty, skip writing to avoid overwriting good files
            if not result or not result.strip():
                print("   ⚠️  LLM returned empty — skipping this attempt")
                continue

            files_written = 0
            if fix_data and "fixes" in fix_data:
                print(f"   💡 Diagnosis: {fix_data.get('diagnosis', '')[:100]}")
                for fix in fix_data["fixes"]:
                    fpath = fix.get("path", "")
                    content = fix.get("content", "")
                    if not fpath or not content or len(content.strip()) < 10:
                        continue
                    # Correct wrong paths: LLM sometimes writes src/app/lib/ or src/app/models/
                    # which are not valid Next.js App Router paths.
                    _wrong_prefixes = [
                        ("src/app/lib/",     "src/lib/"),
                        ("src/app/models/",  "src/models/"),
                        ("src/app/services/","src/services/"),
                        ("src/app/utils/",   "src/utils/"),
                        ("src/app/types/",   "src/types/"),
                        ("src/app/hooks/",   "src/hooks/"),
                    ]
                    for wrong, right in _wrong_prefixes:
                        if fpath.startswith(wrong):
                            corrected = right + fpath[len(wrong):]
                            print(f"   🔧 Path fix: {fpath} → {corrected}")
                            fpath = corrected
                            break
                    # Protect layout.tsx: never overwrite with invalid content
                    if fpath == "src/app/layout.tsx" and "export default" not in content:
                        print(f"   ⏭️  Skip: {fpath} fix lacks 'export default' — keeping existing")
                        continue
                    # Fix #8: skip if content unchanged since last write
                    cached = self.generated_files.get(fpath, "")
                    if content.strip() == cached.strip() and fpath in prev_fixes:
                        print(f"   ⏭️  Skip (unchanged): {fpath}")
                        continue
                    full = os.path.join(project_path, fpath)
                    self.fs.write_file(full, content)
                    self.generated_files[fpath] = content
                    prev_fixes.add(fpath)
                    files_written += 1
                    print(f"   🔧 Fixed: {fpath}")

            if files_written == 0 and not stuck:
                print("   ℹ️  No new fixes this round  -  retrying with more context next attempt")

            self.git.commit(project_path, f"Bug fix attempt {attempt + 1}")

            # Run npm install if package.json was touched or node_modules is missing
            pkg_was_fixed = any(
                f.get("path", "").endswith("package.json")
                for f in (fix_data.get("fixes", []) if fix_data else [])
            )
            if pkg_was_fixed or not os.path.exists(os.path.join(build_dir, "node_modules")):
                reason = "package.json updated" if pkg_was_fixed else "node_modules missing"
                print(f"   📦 Running npm install ({reason})…")
                _, inst_err, inst_code = self.terminal.run("npm install", cwd=build_dir, timeout=180)
                if inst_code != 0:
                    print(f"   ⚠️  npm install warning: {inst_err[:100]}")

            stdout, stderr, code = self.terminal.run("npm run build 2>&1", cwd=build_dir, timeout=120)
            if code == 0:
                print(f"   ✅ Fixed after {attempt + 1} attempt(s)!")
                return True

            current_errors = stderr or stdout

        print(f"   ⚠️  Could not fix all issues after {max_attempts} attempts")
        print("   Remaining errors:")
        for line in current_errors.split("\n")[:10]:
            if line.strip():
                print(f"      {line.strip()}")
        return False

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
    # Phase 9  -  Optimization
    # ------------------------------------------------------------------

    def _phase_optimize(self, project_path: str, tech: dict):
        print("\n✨ Phase 9: Optimization…")
        is_split = tech["type"] == "fullstack-split"
        actions = 0

        if not is_split:
            import shutil

            # 1. Remove duplicate src/app/components/ (Fix #1 cleanup)
            app_comp = os.path.join(project_path, "src", "app", "components")
            if os.path.isdir(app_comp):
                shutil.rmtree(app_comp)
                print("   🗑️  Removed src/app/components/ (duplicates of src/components/)")
                actions += 1

            # 2. Remove stray CSS files (Fix #2 cleanup)
            for stray in ["src/index.css", "src/styles/globals.css", "src/styles/index.css"]:
                stray_full = os.path.join(project_path, stray)
                if os.path.exists(stray_full):
                    os.remove(stray_full)
                    print(f"   🗑️  Removed stray CSS: {stray}")
                    actions += 1

            # 3. Report broken imports (Fix #7 followup — report but don't block)
            broken = self._validate_imports(project_path)
            if broken:
                print(f"   ⚠️  {len(broken)} unresolved import(s) (may cause build errors):")
                for b in broken[:5]:
                    print(f"      {b}")
            else:
                print("   ✅ All relative imports resolve correctly")

        if actions:
            self.git.commit(project_path, "Optimization pass")
        print(f"   ✅ Optimization complete! ({actions} cleanup action(s))")

    # ------------------------------------------------------------------
    # Phase 10  -  Documentation
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
    # Phase 11  -  Deployment
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
        # Fix #4: accurately reflect whether the build succeeded
        build_ok = self.project.get("build_ok", True)
        if build_ok:
            header = "║              🎉 BUILD COMPLETE!                          ║"
            footer_note = ""
        else:
            header = "║        ⚠️  BUILD INCOMPLETE  -  manual fixes needed       ║"
            footer_note = (
                "\n⚠️  The npm build did not pass after all debug attempts.\n"
                "   Run  npm run build  inside the project folder to see\n"
                "   remaining errors and fix them manually.\n"
            )
        summary = (
            "\n╔══════════════════════════════════════════════════════════╗\n"
            f"{header}\n"
            "╠══════════════════════════════════════════════════════════╣\n\n"
            f"📁 Location:  {project_path}\n"
            f"📊 Files:     {len(self.generated_files)}\n\n"
            f"Build phases:\n{phase_lines}\n\n"
            f"📂 Structure:\n{tree}\n"
            f"{footer_note}\n"
            f"💡 Run it:\n   cd {project_path}\n   {run_cmd}\n\n"
            "╚══════════════════════════════════════════════════════════╝"
        )
        print(summary)
        return summary
