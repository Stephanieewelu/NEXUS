"""
build_orchestrator.py  -  Template-first NEXUS app builder.

OVERHAUL: Template-based generation eliminates the rate-limiting problem.

Old approach: 5-7 LLM calls, 20,000+ tokens per build → hits free tier in seconds.
New approach: 1 LLM call (~400 tokens) for requirements parsing, then pure Python
              templates generate all code. No LLM needed for code generation.

Architecture:
  Phase 1:  Parse requirements   (1 LLM call, ~400 tokens — or regex fallback: 0 calls)
  Phase 2:  Architecture         (0 LLM calls)
  Phase 3:  Tech stack           (0 LLM calls)
  Phase 4:  Scaffold             (0 LLM calls — creates package.json, tsconfig, npm install)
  Phase 5:  Template generation  (0 LLM calls — Python templates fill all slots)
  Phase 6:  Build + test         (0 LLM calls — runs npm run build)
  Phase 7:  Auto-fix             (0 LLM calls — pattern-based fixes)
  Phase 8:  Docs                 (0 LLM calls — generated from requirements)
  Phase 9:  Deploy prep          (0 LLM calls)

Max total: 1 LLM call = ~400 tokens. Rate limits are no longer a concern.
"""

import json
import os
import re
import shutil
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


_PHASE_DEFS = [
    ("requirements",        "Gather and clarify requirements",   1),
    ("architecture",        "Design system architecture",        2),
    ("tech_selection",      "Select optimal tech stack",         3),
    ("scaffolding",         "Create project structure",          4),
    ("core_implementation", "Build core features",               5),
    ("testing",             "Build and verify",                  6),
    ("debugging",           "Fix any build issues",              7),
    ("documentation",       "Generate documentation",            8),
    ("deployment_prep",     "Prepare for deployment",            9),
]


# ---------------------------------------------------------------------------
# Template Engine
# ---------------------------------------------------------------------------

# Color palette: name → (tailwind-prefix, bg-gradient-from, bg-gradient-to, hex, dark-hex)
_COLORS: Dict[str, tuple] = {
    "blue":   ("blue",   "from-blue-600",   "to-blue-800",   "#2563eb", "#1e40af"),
    "purple": ("purple", "from-purple-600", "to-purple-800", "#9333ea", "#6b21a8"),
    "green":  ("green",  "from-green-600",  "to-green-800",  "#16a34a", "#14532d"),
    "teal":   ("teal",   "from-teal-600",   "to-teal-800",   "#0d9488", "#134e4a"),
    "orange": ("orange", "from-orange-500", "to-orange-700", "#f97316", "#c2410c"),
    "rose":   ("rose",   "from-rose-600",   "to-rose-800",   "#e11d48", "#9f1239"),
    "indigo": ("indigo", "from-indigo-600", "to-indigo-800", "#4f46e5", "#312e81"),
}


def _col(color: str) -> tuple:
    """Get color tuple, defaulting to blue."""
    return _COLORS.get(color, _COLORS["blue"])


class _T:
    """Template library — every method returns complete, valid TypeScript/CSS source."""

    # ── globals.css ──────────────────────────────────────────────────────────

    @staticmethod
    def globals_css(color: str) -> str:
        _, _, _, hex_val, hex_dark = _col(color)
        c = _col(color)[0]  # tailwind color name
        return f"""@tailwind base;
@tailwind components;
@tailwind utilities;

:root {{
  --primary: {hex_val};
  --primary-dark: {hex_dark};
  --foreground: #111827;
  --background: #f9fafb;
}}

* {{
  box-sizing: border-box;
}}

body {{
  color: var(--foreground);
  background: var(--background);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  min-height: 100vh;
}}

/* Utility classes that reference the primary color */
.btn-primary {{
  @apply bg-{c}-600 hover:bg-{c}-700 text-white px-6 py-2.5 rounded-xl font-medium transition-all hover:shadow-lg;
}}

.btn-outline {{
  @apply border-2 border-{c}-600 text-{c}-600 hover:bg-{c}-50 px-6 py-2.5 rounded-xl font-medium transition-all;
}}

.card {{
  @apply bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-all p-6;
}}
"""

    # ── layout.tsx ────────────────────────────────────────────────────────────

    @staticmethod
    def layout(display_name: str, summary: str) -> str:
        safe_name = display_name.replace('"', '\\"')
        safe_desc = summary[:160].replace('"', '\\"')
        return f"""import type {{ Metadata }} from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";

export const metadata: Metadata = {{
  title: "{safe_name}",
  description: "{safe_desc}",
}};

export default function RootLayout({{
  children,
}}: Readonly<{{
  children: React.ReactNode;
}}>) {{
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50">
        <Navbar />
        {{children}}
      </body>
    </html>
  );
}}
"""

    # ── Navbar.tsx ────────────────────────────────────────────────────────────

    @staticmethod
    def navbar(display_name: str, pages: list, color: str) -> str:
        c = _col(color)[0]
        safe_name = display_name.replace('"', '\\"')

        # Build nav items from pages (exclude home slug "/")
        nav_items = [{"label": "Home", "href": "/"}]
        for p in pages:
            slug = p.get("slug", "").strip().strip("/")
            if slug and slug != "/":
                nav_items.append({"label": p.get("name", slug.title()), "href": f"/{slug}"})

        items_js = json.dumps(nav_items, indent=2)

        return f""""use client";
import Link from "next/link";
import {{ useState }} from "react";

const navItems = {items_js};

export default function Navbar() {{
  const [open, setOpen] = useState(false);

  return (
    <nav className="bg-white/95 backdrop-blur-sm border-b border-gray-200 sticky top-0 z-50">
      <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
        <Link href="/" className="font-bold text-xl text-{c}-600 hover:opacity-80 transition">
          {safe_name}
        </Link>

        {{/* Desktop */}}
        <ul className="hidden md:flex gap-8 items-center">
          {{navItems.map((item) => (
            <li key={{item.href}}>
              <Link
                href={{item.href}}
                className="text-gray-600 hover:text-{c}-600 transition font-medium"
              >
                {{item.label}}
              </Link>
            </li>
          ))}}
        </ul>

        {{/* Mobile toggle */}}
        <button
          onClick={{() => setOpen(!open)}}
          className="md:hidden text-gray-500 hover:text-gray-700 p-1"
          aria-label="Toggle menu"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {{open ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M6 18L18 6M6 6l12 12" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M4 6h16M4 12h16M4 18h16" />
            )}}
          </svg>
        </button>
      </div>

      {{/* Mobile menu */}}
      {{open && (
        <div className="md:hidden bg-white border-t border-gray-100 py-2">
          {{navItems.map((item) => (
            <Link
              key={{item.href}}
              href={{item.href}}
              onClick={{() => setOpen(false)}}
              className="block px-4 py-3 text-gray-600 hover:bg-{c}-50 hover:text-{c}-600 transition font-medium"
            >
              {{item.label}}
            </Link>
          ))}}
        </div>
      )}}
    </nav>
  );
}}
"""

    # ── Home page ─────────────────────────────────────────────────────────────

    @staticmethod
    def tiktok_generate_page() -> str:
        """Interactive TikTok Digital Twin content generator — pure client-side, no API needed."""
        return '''"use client";
import { useState } from "react";

interface Persona { handle: string; niche: string; tone: string; }
interface GeneratedContent { hook: string; script: string; hashtags: string[]; caption: string; }

const NICHES = ["Comedy","Fashion","Food","Finance","Fitness","Education","Gaming","Beauty","Travel","Motivation"];
const TONES  = ["Funny","Casual","Educational","Inspirational","Storytelling","POV","Trendy"];
const FORMATS = ["Tutorial","Storytime","POV","Tips","Day in My Life","Skit","Reaction"];
const DURATIONS = ["15s","30s","60s","3min"];

function buildContent(topic: string, persona: Persona, format: string, duration: string): GeneratedContent {
  const t = topic.trim() || "my content";
  const tSlug = t.toLowerCase().replace(/[^a-z0-9]/g, "");

  const hooks: Record<string,string> = {
    Tutorial:       `POV: You\u2019ve been doing ${t} wrong this whole time 😤`,
    Storytime:      `The ${t} situation nobody warned me about... 👀`,
    POV:            `POV: You finally understand ${t} \u2728`,
    Tips:           `5 things about ${t} that changed my life 🤯`,
    "Day in My Life":`Come experience ${t} with me today 📱`,
    Skit:           `Me before ${t} vs. after 💀`,
    Reaction:       `Everyone\u2019s obsessed with ${t} \u2014 here\u2019s the truth 👀`,
  };

  const bodies: Record<string,string> = {
    Tutorial:
`Step 1: [Most surprising fact about ${t}]
Step 2: [The wrong way most people do it]
Step 3: [The right way \u2014 keep it visual]
Step 4: [Quick result or transformation]`,
    Storytime:
`[Set the scene \u2014 where were you?]
[What happened with ${t}]
[The turning point \u2014 make them lean in]
[The resolution / lesson learned]`,
    POV:
`[Put the viewer in the moment with ${t}]
[Build tension or curiosity in 5s]
[The reveal or payoff]
[Relatable reaction shot]`,
    Tips:
`Tip 1: [Quick, specific ${t} tip]
Tip 2: [Something counterintuitive]
Tip 3: [The one they screenshot]
Tip 4: [Advanced move]
Tip 5: [The share-worthy closer]`,
    "Day in My Life":
`[Morning \u2014 your ${t} routine]
[Midday \u2014 real moment or challenge]
[Evening \u2014 reflection or win]
[Outro \u2014 call viewer to action]`,
    Skit:
`[Setup: exaggerate the old way]
[Transition: "and then I discovered..."]
[Payoff: show the better way]
[Outro: quick reaction shot]`,
    Reaction:
`[Show the ${t} trend or clip]
[Your genuine first reaction]
[Break down why it works / doesn\u2019t]
[Your hot take / verdict]`,
  };

  const ctas: Record<string,string> = {
    Funny:         `Drop a 😂 if you felt that! Follow ${persona.handle} for more`,
    Casual:        `Save this! Follow ${persona.handle} for the good stuff 💯`,
    Educational:   `Follow ${persona.handle} for more tips like this 🧠`,
    Inspirational: `Share with someone who needs this 🙌`,
    Storytelling:  `Follow ${persona.handle} \u2014 this is only part 1 👀`,
    POV:           `Comment if you relate! Follow for more POVs 📱`,
    Trendy:        `Duet this & tag me! ${persona.handle} 🔥`,
  };

  const nicheHtags: Record<string,string[]> = {
    Comedy:     ["#funny","#comedy","#relatable","#lol"],
    Fashion:    ["#fashion","#ootd","#style","#outfitinspo"],
    Food:       ["#foodtok","#recipe","#cooking","#foodie"],
    Finance:    ["#moneytok","#finance","#investing","#money"],
    Fitness:    ["#fitnessmotivation","#workout","#gym","#health"],
    Education:  ["#learnontiktok","#didyouknow","#education","#facts"],
    Gaming:     ["#gaming","#gamer","#videogames","#gamertok"],
    Beauty:     ["#beauty","#makeup","#skincare","#beautytips"],
    Travel:     ["#travel","#wanderlust","#traveltok","#adventure"],
    Motivation: ["#motivation","#mindset","#success","#inspiration"],
  };

  const hook    = hooks[format]  ?? `${t} is changing everything 🔥`;
  const body    = bodies[format] ?? `[${duration} of ${persona.niche} content about ${t} \u2014 ${persona.tone} tone]`;
  const cta     = ctas[persona.tone] ?? `Follow ${persona.handle} for more ${persona.niche} content 🔔`;
  const nHtags  = nicheHtags[persona.niche] ?? ["#foryoupage","#viral","#trending"];
  const hashtags = ["#fyp","#foryoupage",...nHtags.slice(0,3),`#${tSlug||"tiktok"}`].slice(0,7);
  const caption = `${hook}\n\n${hashtags.join(" ")}`;
  const script  = `🎥 HOOK (first 3s):\n"${hook}"\n\n📝 BODY (${duration}):\n${body}\n\n🎯 CTA:\n"${cta}"`;

  return { hook, script, hashtags, caption };
}

export default function GeneratePage() {
  const [persona, setPersona]   = useState<Persona>({ handle: "@mydigitaltwin", niche: "Education", tone: "Casual" });
  const [topic, setTopic]       = useState("");
  const [format, setFormat]     = useState("Tutorial");
  const [duration, setDuration] = useState("30s");
  const [result, setResult]     = useState<GeneratedContent | null>(null);
  const [copied, setCopied]     = useState<string | null>(null);
  const [loading, setLoading]   = useState(false);

  const handleGenerate = () => {
    if (!topic.trim()) return;
    setLoading(true);
    setTimeout(() => { setResult(buildContent(topic, persona, format, duration)); setLoading(false); }, 1200);
  };

  const copy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-6xl mx-auto px-4 py-10">
        <div className="text-center mb-10">
          <h1 className="text-4xl font-bold mb-2">
            Content <span className="text-rose-500">Generator</span>
          </h1>
          <p className="text-gray-400">Create viral TikTok scripts, captions &amp; hashtags in your twin&apos;s voice</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* ── Twin persona sidebar ── */}
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
            <h2 className="text-lg font-semibold mb-4">👤 Your Twin</h2>
            <div className="mb-4">
              <label className="text-xs text-gray-400 mb-1 block">Handle</label>
              <input
                value={persona.handle}
                onChange={(e) => setPersona({ ...persona, handle: e.target.value })}
                placeholder="@yourhandle"
                className="w-full bg-gray-800 border border-gray-700 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-rose-500"
              />
            </div>
            <div className="mb-4">
              <label className="text-xs text-gray-400 mb-2 block">Niche</label>
              <div className="flex flex-wrap gap-1.5">
                {NICHES.map((n) => (
                  <button
                    key={n}
                    onClick={() => setPersona({ ...persona, niche: n })}
                    className={`text-xs px-2.5 py-1 rounded-full transition ${persona.niche === n ? "bg-rose-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"}`}
                  >{n}</button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-2 block">Tone</label>
              <div className="flex flex-wrap gap-1.5">
                {TONES.map((t) => (
                  <button
                    key={t}
                    onClick={() => setPersona({ ...persona, tone: t })}
                    className={`text-xs px-2.5 py-1 rounded-full transition ${persona.tone === t ? "bg-rose-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"}`}
                  >{t}</button>
                ))}
              </div>
            </div>
          </div>

          {/* ── Generator + results ── */}
          <div className="lg:col-span-2 space-y-5">
            <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
              <h2 className="text-lg font-semibold mb-4">🎥 Create Content</h2>
              <div className="mb-4">
                <label className="text-xs text-gray-400 mb-1 block">Topic or Idea</label>
                <input
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleGenerate()}
                  placeholder="e.g. morning routines, investing basics, easy recipes..."
                  className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-rose-500"
                />
              </div>
              <div className="grid grid-cols-2 gap-4 mb-5">
                <div>
                  <label className="text-xs text-gray-400 mb-1 block">Format</label>
                  <select value={format} onChange={(e) => setFormat(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-rose-500">
                    {FORMATS.map((f) => <option key={f}>{f}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-gray-400 mb-1 block">Duration</label>
                  <select value={duration} onChange={(e) => setDuration(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-rose-500">
                    {DURATIONS.map((d) => <option key={d}>{d}</option>)}
                  </select>
                </div>
              </div>
              <button
                onClick={handleGenerate}
                disabled={!topic.trim() || loading}
                className="w-full bg-rose-600 hover:bg-rose-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-xl transition flex items-center justify-center gap-2"
              >
                {loading ? "\u2728 Generating as your Twin..." : "\u2728 Generate as My Digital Twin"}
              </button>
            </div>

            {result && (
              <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-4">
                <h2 className="text-lg font-semibold">📤 Your Content</h2>

                {/* Script */}
                <div className="bg-gray-800 rounded-xl p-4">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs text-gray-400 uppercase tracking-wider font-medium">Script</span>
                    <button onClick={() => copy(result.script, "script")} className="text-xs text-rose-400 hover:text-rose-300 transition">
                      {copied === "script" ? "\u2705 Copied!" : "📋 Copy"}
                    </button>
                  </div>
                  <pre className="text-sm whitespace-pre-wrap text-gray-200 font-sans leading-relaxed">{result.script}</pre>
                </div>

                {/* Hashtags */}
                <div className="bg-gray-800 rounded-xl p-4">
                  <div className="flex justify-between items-center mb-3">
                    <span className="text-xs text-gray-400 uppercase tracking-wider font-medium">Hashtags</span>
                    <button onClick={() => copy(result.hashtags.join(" "), "tags")} className="text-xs text-rose-400 hover:text-rose-300 transition">
                      {copied === "tags" ? "\u2705 Copied!" : "📋 Copy All"}
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {result.hashtags.map((tag) => (
                      <span key={tag} className="bg-rose-900/40 text-rose-300 text-xs px-2.5 py-1 rounded-full border border-rose-800/50">{tag}</span>
                    ))}
                  </div>
                </div>

                {/* Caption */}
                <div className="bg-gray-800 rounded-xl p-4">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs text-gray-400 uppercase tracking-wider font-medium">Caption</span>
                    <button onClick={() => copy(result.caption, "caption")} className="text-xs text-rose-400 hover:text-rose-300 transition">
                      {copied === "caption" ? "\u2705 Copied!" : "📋 Copy"}
                    </button>
                  </div>
                  <p className="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">{result.caption}</p>
                </div>

                <button onClick={handleGenerate} className="w-full border border-rose-700 text-rose-400 hover:bg-rose-950 font-medium py-2.5 rounded-xl transition text-sm">
                  🔄 Regenerate
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
'''

    @staticmethod
    def home_page(display_name: str, tagline: str, summary: str,
                  features: list, pages: list, color: str) -> str:
        c = _col(color)[0]
        grad_from, grad_to = _col(color)[1], _col(color)[2]
        safe_name = display_name.replace('"', '\\"')
        safe_tagline = tagline.replace('"', '\\"')
        safe_summary = summary[:200].replace('"', '\\"')

        # Build features array
        feat_list = []
        default_icons = ["⚡", "🎨", "🛡️", "📱", "🔒", "🚀"]
        for i, f in enumerate(features[:6]):
            icon = f.get("icon", default_icons[i % len(default_icons)])
            name = f.get("name", f"Feature {i+1}")
            desc = f.get("desc", f.get("description", "Amazing feature"))
            feat_list.append({"icon": icon, "name": name, "desc": desc})

        if not feat_list:
            feat_list = [
                {"icon": "⚡", "name": "Lightning Fast", "desc": "Optimised for speed and performance"},
                {"icon": "🎨", "name": "Beautiful Design", "desc": "Modern, clean, and intuitive interface"},
                {"icon": "🛡️", "name": "Reliable", "desc": "Built to scale with your needs"},
            ]

        features_js = json.dumps(feat_list, indent=2)

        # Primary page CTA link
        cta_href = "/"
        for p in pages:
            slug = p.get("slug", "").strip().strip("/")
            if slug and slug != "/":
                cta_href = f"/{slug}"
                break

        return f"""import Link from "next/link";

const features = {features_js};

export default function HomePage() {{
  return (
    <>
      {{/* Hero */}}
      <section className="bg-gradient-to-br {grad_from} {grad_to} text-white py-24 px-6 text-center">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-5xl md:text-6xl font-bold mb-6 leading-tight tracking-tight">
            {safe_name}
          </h1>
          <p className="text-xl md:text-2xl opacity-90 mb-10 max-w-2xl mx-auto leading-relaxed">
            {safe_tagline}
          </p>
          <div className="flex flex-wrap justify-center gap-4">
            <Link
              href="{cta_href}"
              className="bg-white text-{c}-600 px-8 py-3.5 rounded-full font-semibold hover:shadow-xl transition-all hover:scale-105"
            >
              Get Started →
            </Link>
            <Link
              href="#features"
              className="border-2 border-white/70 text-white px-8 py-3.5 rounded-full font-semibold hover:bg-white/10 transition-all"
            >
              Learn More
            </Link>
          </div>
        </div>
      </section>

      {{/* Features */}}
      <section id="features" className="max-w-6xl mx-auto py-20 px-6">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold text-gray-900 mb-4">
            Why {safe_name}?
          </h2>
          <p className="text-gray-500 text-lg max-w-2xl mx-auto leading-relaxed">
            {safe_summary}
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {{features.map((f) => (
            <div key={{f.name}} className="card group cursor-default">
              <div className="text-4xl mb-4">{{f.icon}}</div>
              <h3 className="text-xl font-semibold text-gray-900 mb-2">{{f.name}}</h3>
              <p className="text-gray-500 leading-relaxed">{{f.desc}}</p>
            </div>
          ))}}
        </div>
      </section>

      {{/* CTA Banner */}}
      <section className="bg-gradient-to-r {grad_from} {grad_to} text-white py-16 px-6 text-center">
        <div className="max-w-2xl mx-auto">
          <h2 className="text-3xl font-bold mb-4">Ready to get started?</h2>
          <p className="opacity-85 mb-8 text-lg">
            Join thousands of users who rely on {safe_name} every day.
          </p>
          <Link
            href="{cta_href}"
            className="bg-white text-{c}-600 px-10 py-4 rounded-full font-semibold text-lg hover:shadow-xl transition-all hover:scale-105 inline-block"
          >
            Start Now →
          </Link>
        </div>
      </section>

      {{/* Footer */}}
      <footer className="bg-gray-900 text-gray-400 py-10 text-center">
        <p className="text-sm">© {{new Date().getFullYear()}} {safe_name}. Built with NEXUS.</p>
      </footer>
    </>
  );
}}
"""

    # ── CRUD list page ────────────────────────────────────────────────────────

    @staticmethod
    def crud_page(page_name: str, slug: str, color: str) -> str:
        c = _col(color)[0]
        comp = "".join(w.capitalize() for w in re.split(r"[-_ ]+", page_name) if w)
        entity = page_name.rstrip("s")  # "Tasks" → "Task"
        safe_name = page_name.replace('"', '\\"')

        return f""""use client";
import {{ useState }} from "react";

interface {comp}Item {{
  id: string;
  title: string;
  completed: boolean;
  createdAt: string;
}}

const sampleData: {comp}Item[] = [
  {{ id: "1", title: "Sample {entity} one", completed: false, createdAt: new Date().toLocaleDateString() }},
  {{ id: "2", title: "Sample {entity} two", completed: true, createdAt: new Date().toLocaleDateString() }},
  {{ id: "3", title: "Sample {entity} three", completed: false, createdAt: new Date().toLocaleDateString() }},
];

type Filter = "all" | "active" | "done";

export default function {comp}Page() {{
  const [items, setItems] = useState<{comp}Item[]>(sampleData);
  const [input, setInput] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const add = () => {{
    if (!input.trim()) return;
    setItems((prev) => [
      ...prev,
      {{ id: Date.now().toString(), title: input.trim(), completed: false, createdAt: new Date().toLocaleDateString() }},
    ]);
    setInput("");
  }};

  const toggle = (id: string) =>
    setItems((prev) => prev.map((i) => (i.id === id ? {{ ...i, completed: !i.completed }} : i)));

  const remove = (id: string) =>
    setItems((prev) => prev.filter((i) => i.id !== id));

  const filtered = items.filter((i) =>
    filter === "all" ? true : filter === "done" ? i.completed : !i.completed
  );

  const remaining = items.filter((i) => !i.completed).length;

  return (
    <main className="max-w-2xl mx-auto px-4 py-10">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-900">{safe_name}</h1>
        <span className="text-sm text-gray-400 bg-gray-100 px-3 py-1 rounded-full">
          {{remaining}} remaining
        </span>
      </div>

      {{/* Add form */}}
      <div className="flex gap-2 mb-6">
        <input
          type="text"
          value={{input}}
          onChange={{(e) => setInput(e.target.value)}}
          onKeyDown={{(e) => e.key === "Enter" && add()}}
          placeholder="Add a new {entity.lower()}..."
          className="flex-1 px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-{c}-500 focus:border-transparent bg-white"
        />
        <button
          onClick={{add}}
          className="px-5 py-2.5 bg-{c}-600 text-white rounded-xl hover:bg-{c}-700 transition font-medium"
        >
          Add
        </button>
      </div>

      {{/* Filter tabs */}}
      <div className="flex gap-1 p-1 bg-gray-100 rounded-xl mb-6">
        {{(["all", "active", "done"] as Filter[]).map((f) => (
          <button
            key={{f}}
            onClick={{() => setFilter(f)}}
            className={{`flex-1 py-1.5 rounded-lg text-sm font-medium transition capitalize ${{
              filter === f ? "bg-white shadow-sm text-gray-900" : "text-gray-500 hover:text-gray-700"
            }}`}}
          >
            {{f}}
          </button>
        ))}}
      </div>

      {{/* List */}}
      <ul className="space-y-2">
        {{filtered.length === 0 && (
          <li className="text-center text-gray-400 py-12 bg-white rounded-2xl border border-dashed border-gray-200">
            No items here. Add your first one above!
          </li>
        )}}
        {{filtered.map((item) => (
          <li
            key={{item.id}}
            className="flex items-center gap-3 p-4 bg-white border border-gray-100 rounded-xl hover:border-gray-200 group transition"
          >
            <input
              type="checkbox"
              checked={{item.completed}}
              onChange={{() => toggle(item.id)}}
              className="w-5 h-5 accent-{c}-600 cursor-pointer flex-shrink-0"
            />
            <span className={{`flex-1 ${{item.completed ? "line-through text-gray-400" : "text-gray-800"}}`}}>
              {{item.title}}
            </span>
            <span className="text-xs text-gray-300 hidden group-hover:block mr-2">
              {{item.createdAt}}
            </span>
            <button
              onClick={{() => remove(item.id)}}
              className="opacity-0 group-hover:opacity-100 text-gray-300 hover:text-red-500 transition p-1 rounded"
              aria-label="Delete"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </li>
        ))}}
      </ul>

      {{items.length > 0 && (
        <div className="mt-4 flex justify-end">
          <button
            onClick={{() => setItems((prev) => prev.filter((i) => !i.completed))}}
            className="text-sm text-gray-400 hover:text-red-500 transition"
          >
            Clear completed
          </button>
        </div>
      )}}
    </main>
  );
}}
"""

    # ── Dashboard page ────────────────────────────────────────────────────────

    @staticmethod
    def dashboard_page(page_name: str, color: str) -> str:
        c = _col(color)[0]
        comp = "".join(w.capitalize() for w in re.split(r"[-_ ]+", page_name) if w)
        safe_name = page_name.replace('"', '\\"')

        return f""""use client";
import {{ useState }} from "react";

const stats = [
  {{ label: "Total Users",    value: "1,284",  change: "+12%",  up: true,  icon: "👥" }},
  {{ label: "Revenue",        value: "$4,920", change: "+8%",   up: true,  icon: "💰" }},
  {{ label: "Active Orders",  value: "289",    change: "+24%",  up: true,  icon: "📦" }},
  {{ label: "Avg. Session",   value: "4m 32s", change: "-3%",   up: false, icon: "⏱️" }},
];

const activity = [
  {{ action: "New user registered",      time: "2 min ago",   type: "user" }},
  {{ action: "Order #1204 completed",    time: "8 min ago",   type: "order" }},
  {{ action: "Payment received $129",    time: "15 min ago",  type: "payment" }},
  {{ action: "Support ticket resolved",  time: "1 hour ago",  type: "support" }},
  {{ action: "New user registered",      time: "2 hours ago", type: "user" }},
  {{ action: "Report exported",          time: "3 hours ago", type: "report" }},
];

export default function {comp}Page() {{
  const [period, setPeriod] = useState<"day" | "week" | "month">("week");

  return (
    <main className="max-w-6xl mx-auto px-4 py-8">
      {{/* Header */}}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">{safe_name}</h1>
          <p className="text-gray-500 mt-1">
            {{new Date().toLocaleDateString("en-US", {{ weekday: "long", year: "numeric", month: "long", day: "numeric" }})}}
          </p>
        </div>
        <div className="flex gap-1 p-1 bg-gray-100 rounded-xl">
          {{(["day", "week", "month"] as const).map((p) => (
            <button
              key={{p}}
              onClick={{() => setPeriod(p)}}
              className={{`px-4 py-1.5 rounded-lg text-sm font-medium transition capitalize ${{
                period === p ? "bg-white shadow-sm text-gray-900" : "text-gray-500 hover:text-gray-700"
              }}`}}
            >
              {{p}}
            </button>
          ))}}
        </div>
      </div>

      {{/* Stats grid */}}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {{stats.map((s) => (
          <div key={{s.label}} className="card">
            <div className="flex items-start justify-between mb-3">
              <span className="text-3xl">{{s.icon}}</span>
              <span
                className={{`text-xs font-semibold px-2 py-1 rounded-full ${{
                  s.up ? "bg-green-50 text-green-600" : "bg-red-50 text-red-500"
                }}`}}
              >
                {{s.change}}
              </span>
            </div>
            <div className="text-2xl font-bold text-gray-900 mb-1">{{s.value}}</div>
            <div className="text-sm text-gray-500">{{s.label}}</div>
          </div>
        ))}}
      </div>

      {{/* Activity feed */}}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Recent Activity</h2>
          <button className="text-sm text-{c}-600 hover:text-{c}-700 font-medium">
            View all →
          </button>
        </div>
        <ul className="divide-y divide-gray-50">
          {{activity.map((item, i) => (
            <li key={{i}} className="px-6 py-4 flex items-center justify-between hover:bg-gray-50 transition">
              <div className="flex items-center gap-3">
                <div className="w-2 h-2 rounded-full bg-{c}-400 flex-shrink-0" />
                <span className="text-gray-700 text-sm">{{item.action}}</span>
              </div>
              <span className="text-xs text-gray-400 whitespace-nowrap ml-4">{{item.time}}</span>
            </li>
          ))}}
        </ul>
      </div>
    </main>
  );
}}
"""

    # ── Generic info page ─────────────────────────────────────────────────────

    @staticmethod
    def info_page(page_name: str, page_desc: str, display_name: str, color: str) -> str:
        c = _col(color)[0]
        comp = "".join(w.capitalize() for w in re.split(r"[-_ ]+", page_name) if w)
        safe_name = page_name.replace('"', '\\"')
        safe_desc = page_desc.replace('"', '\\"') if page_desc else f"Learn more about {display_name}."
        safe_app = display_name.replace('"', '\\"')

        return f"""export default function {comp}Page() {{
  return (
    <main className="max-w-4xl mx-auto px-4 py-16">
      {{/* Header */}}
      <div className="text-center mb-16">
        <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-4">{safe_name}</h1>
        <p className="text-gray-500 text-lg max-w-2xl mx-auto leading-relaxed">
          {safe_desc}
        </p>
      </div>

      {{/* Content */}}
      <div className="grid gap-8">
        <div className="card">
          <h2 className="text-2xl font-semibold text-gray-900 mb-4">About {safe_name}</h2>
          <p className="text-gray-600 leading-relaxed mb-4">
            {safe_desc}
          </p>
          <p className="text-gray-600 leading-relaxed">
            {safe_app} is designed to be fast, intuitive, and reliable.
            Every feature is carefully crafted to give you the best possible experience.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="card">
            <div className="text-3xl mb-3">🎯</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Our Mission</h3>
            <p className="text-gray-500 text-sm leading-relaxed">
              We believe great software should be accessible to everyone.
              Our mission is to provide the best {safe_name.lower()} experience possible.
            </p>
          </div>
          <div className="card">
            <div className="text-3xl mb-3">💡</div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Our Vision</h3>
            <p className="text-gray-500 text-sm leading-relaxed">
              Building the future of {safe_app.lower()}, one feature at a time.
              We&apos;re committed to continuous improvement and innovation.
            </p>
          </div>
        </div>
      </div>

      {{/* CTA */}}
      <div className="mt-16 text-center">
        <a
          href="/"
          className="inline-block bg-{c}-600 hover:bg-{c}-700 text-white px-8 py-3.5 rounded-full font-semibold transition-all hover:shadow-lg"
        >
          ← Back to Home
        </a>
      </div>
    </main>
  );
}}
"""

    # ── Contact / form page ───────────────────────────────────────────────────

    @staticmethod
    def form_page(page_name: str, page_desc: str, color: str) -> str:
        c = _col(color)[0]
        comp = "".join(w.capitalize() for w in re.split(r"[-_ ]+", page_name) if w)
        safe_name = page_name.replace('"', '\\"')
        safe_desc = page_desc.replace('"', '\\"') if page_desc else "We&apos;d love to hear from you."

        return f""""use client";
import {{ useState }} from "react";

export default function {comp}Page() {{
  const [form, setForm] = useState({{ name: "", email: "", message: "" }});
  const [sent, setSent] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {{
    e.preventDefault();
    // TODO: wire up to your backend / email service
    setSent(true);
  }};

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {{
    setForm((prev) => ({{ ...prev, [e.target.name]: e.target.value }}));
  }};

  return (
    <main className="max-w-2xl mx-auto px-4 py-16">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">{safe_name}</h1>
        <p className="text-gray-500 text-lg">{safe_desc}</p>
      </div>

      {{sent ? (
        <div className="card text-center py-12">
          <div className="text-5xl mb-4">✅</div>
          <h2 className="text-2xl font-semibold text-gray-900 mb-2">Message sent!</h2>
          <p className="text-gray-500 mb-6">We&apos;ll get back to you as soon as possible.</p>
          <button
            onClick={{() => {{ setSent(false); setForm({{ name: "", email: "", message: "" }}); }}}}
            className="btn-primary"
          >
            Send another
          </button>
        </div>
      ) : (
        <form onSubmit={{handleSubmit}} className="card space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Name</label>
            <input
              type="text"
              name="name"
              value={{form.name}}
              onChange={{handleChange}}
              required
              placeholder="Your full name"
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-{c}-500 focus:border-transparent"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Email</label>
            <input
              type="email"
              name="email"
              value={{form.email}}
              onChange={{handleChange}}
              required
              placeholder="you@example.com"
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-{c}-500 focus:border-transparent"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">Message</label>
            <textarea
              name="message"
              value={{form.message}}
              onChange={{handleChange}}
              required
              rows={{5}}
              placeholder="How can we help you?"
              className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-{c}-500 focus:border-transparent resize-none"
            />
          </div>
          <button type="submit" className="w-full btn-primary py-3 text-base rounded-xl">
            Send Message →
          </button>
        </form>
      )}}
    </main>
  );
}}
"""

    # ── Prisma DB client singleton ─────────────────────────────────────────────

    @staticmethod
    def db_client() -> str:
        return '''import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma =
  globalForPrisma.prisma ??
  new PrismaClient({ log: process.env.NODE_ENV === "development" ? ["error"] : [] });

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
'''

    # ── Prisma schema (generated from pages) ──────────────────────────────────

    @staticmethod
    def prisma_schema(pages: list) -> str:
        header = (
            'datasource db {\n  provider = "sqlite"\n  url      = env("DATABASE_URL")\n}\n\n'
            'generator client {\n  provider = "prisma-client-js"\n}\n\n'
        )
        models: list = []
        seen: set = set()
        for page in pages:
            ptype = page.get("type", "")
            name  = page.get("name", "Item")
            if ptype == "list":
                raw = name.rstrip("s") if name.lower().endswith("s") else name
                model = "".join(w.capitalize() for w in re.split(r"[-_ ]+", raw) if w)
                if model in seen:
                    continue
                seen.add(model)
                models.append(
                    f"model {model} {{\n"
                    f"  id        String   @id @default(cuid())\n"
                    f"  title     String\n"
                    f"  completed Boolean  @default(false)\n"
                    f"  createdAt DateTime @default(now())\n"
                    f"  updatedAt DateTime @updatedAt\n}}\n"
                )
            elif ptype == "tiktok_library":
                if "Content" not in seen:
                    seen.add("Content")
                    seen.add("Settings")
                    models.append(
                        "model Content {\n"
                        "  id        String   @id @default(cuid())\n"
                        "  hook      String\n"
                        "  script    String\n"
                        "  hashtags  String\n"
                        "  caption   String\n"
                        "  topic     String\n"
                        "  format    String\n"
                        "  niche     String\n"
                        "  tone      String\n"
                        "  handle    String\n"
                        "  createdAt DateTime @default(now())\n"
                        "}\n\n"
                        "model Settings {\n"
                        "  id     String @id @default(\"user\")\n"
                        "  handle String @default(\"@mydigitaltwin\")\n"
                        "  niche  String @default(\"Education\")\n"
                        "  tone   String @default(\"Casual\")\n"
                        "}\n"
                    )
        if not models:
            models.append(
                "model Item {\n"
                "  id        String   @id @default(cuid())\n"
                "  title     String\n"
                "  completed Boolean  @default(false)\n"
                "  createdAt DateTime @default(now())\n"
                "  updatedAt DateTime @updatedAt\n}\n"
            )
        return header + "\n".join(models)

    # ── API route: list + create ───────────────────────────────────────────────

    @staticmethod
    def api_list_route(model_var: str) -> str:
        return f'''import {{ NextResponse }} from "next/server";
import {{ prisma }} from "@/lib/db";

export async function GET() {{
  try {{
    const items = await (prisma as any)["{model_var}"].findMany({{ orderBy: {{ createdAt: "desc" }} }});
    return NextResponse.json(items);
  }} catch (e) {{
    return NextResponse.json({{ error: String(e) }}, {{ status: 500 }});
  }}
}}

export async function POST(req: Request) {{
  try {{
    const body = await req.json();
    if (!body.title?.trim()) return NextResponse.json({{ error: "Title required" }}, {{ status: 400 }});
    const item = await (prisma as any)["{model_var}"].create({{ data: {{ title: body.title.trim() }} }});
    return NextResponse.json(item, {{ status: 201 }});
  }} catch (e) {{
    return NextResponse.json({{ error: String(e) }}, {{ status: 500 }});
  }}
}}
'''

    # ── API route: update + delete individual item ─────────────────────────────

    @staticmethod
    def api_item_route(model_var: str) -> str:
        return f'''import {{ NextResponse }} from "next/server";
import {{ prisma }} from "@/lib/db";

export async function PATCH(
  req: Request,
  {{ params }}: {{ params: {{ id: string }} }}
) {{
  try {{
    const data = await req.json();
    const item = await (prisma as any)["{model_var}"].update({{ where: {{ id: params.id }}, data }});
    return NextResponse.json(item);
  }} catch (e) {{
    return NextResponse.json({{ error: String(e) }}, {{ status: 500 }});
  }}
}}

export async function DELETE(
  _: Request,
  {{ params }}: {{ params: {{ id: string }} }}
) {{
  try {{
    await (prisma as any)["{model_var}"].delete({{ where: {{ id: params.id }} }});
    return NextResponse.json({{ ok: true }});
  }} catch (e) {{
    return NextResponse.json({{ error: String(e) }}, {{ status: 500 }});
  }}
}}
'''

    # ── API route: TikTok content (list + save) ────────────────────────────────

    @staticmethod
    def tiktok_content_api() -> str:
        return '''import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET() {
  try {
    const items = await prisma.content.findMany({ orderBy: { createdAt: "desc" } });
    return NextResponse.json(items);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const item = await prisma.content.create({
      data: {
        hook:     body.hook     ?? "",
        script:   body.script   ?? "",
        hashtags: JSON.stringify(body.hashtags ?? []),
        caption:  body.caption  ?? "",
        topic:    body.topic    ?? "",
        format:   body.format   ?? "",
        niche:    body.niche    ?? "",
        tone:     body.tone     ?? "",
        handle:   body.handle   ?? "",
      },
    });
    return NextResponse.json(item, { status: 201 });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
'''

    # ── API route: TikTok content [id] (delete) ────────────────────────────────

    @staticmethod
    def tiktok_content_id_api() -> str:
        return '''import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function DELETE(
  _: Request,
  { params }: { params: { id: string } }
) {
  try {
    await prisma.content.delete({ where: { id: params.id } });
    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
'''

    # ── API route: TikTok settings ─────────────────────────────────────────────

    @staticmethod
    def tiktok_settings_api() -> str:
        return '''import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

export async function GET() {
  try {
    let s = await prisma.settings.findUnique({ where: { id: "user" } });
    if (!s) {
      s = await prisma.settings.create({
        data: { id: "user", handle: "@mydigitaltwin", niche: "Education", tone: "Casual" },
      });
    }
    return NextResponse.json(s);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}

export async function PUT(req: Request) {
  try {
    const data = await req.json();
    const s = await prisma.settings.upsert({
      where:  { id: "user" },
      create: { id: "user", ...data },
      update: data,
    });
    return NextResponse.json(s);
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
'''

    # ── Full-stack CRUD page (fetches from API, persists to DB) ───────────────

    @staticmethod
    def crud_page_fullstack(page_name: str, slug: str, color: str) -> str:
        c       = _col(color)[0]
        comp    = "".join(w.capitalize() for w in re.split(r"[-_ ]+", page_name) if w)
        entity  = page_name.rstrip("s") if page_name.lower().endswith("s") else page_name
        safe    = page_name.replace('"', '\\"')
        api     = f"/api/{slug}"

        return f'''"use client";
import {{ useState, useEffect }} from "react";

interface {comp}Item {{
  id: string;
  title: string;
  completed: boolean;
  createdAt: string;
}}

type Filter = "all" | "active" | "done";

export default function {comp}Page() {{
  const [items,  setItems]  = useState<{comp}Item[]>([]);
  const [input,  setInput]  = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [loading, setLoading] = useState(true);
  const [saving,  setSaving]  = useState(false);

  useEffect(() => {{
    fetch("{api}")
      .then((r) => r.json())
      .then((data) => {{ setItems(Array.isArray(data) ? data : []); setLoading(false); }})
      .catch(() => setLoading(false));
  }}, []);

  const add = async () => {{
    if (!input.trim() || saving) return;
    setSaving(true);
    const res = await fetch("{api}", {{
      method:  "POST",
      headers: {{ "Content-Type": "application/json" }},
      body:    JSON.stringify({{ title: input.trim() }}),
    }});
    if (res.ok) {{ setItems((prev) => [await res.clone().json(), ...prev]); setInput(""); }}
    setSaving(false);
  }};

  const toggle = async (id: string, completed: boolean) => {{
    setItems((prev) => prev.map((i) => (i.id === id ? {{ ...i, completed: !completed }} : i)));
    await fetch(`{api}/${{id}}`, {{
      method:  "PATCH",
      headers: {{ "Content-Type": "application/json" }},
      body:    JSON.stringify({{ completed: !completed }}),
    }});
  }};

  const remove = async (id: string) => {{
    setItems((prev) => prev.filter((i) => i.id !== id));
    await fetch(`{api}/${{id}}`, {{ method: "DELETE" }});
  }};

  const filtered  = items.filter((i) => filter === "all" ? true : filter === "done" ? i.completed : !i.completed);
  const remaining = items.filter((i) => !i.completed).length;

  return (
    <main className="max-w-2xl mx-auto px-4 py-10">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-900">{safe}</h1>
        <span className="text-sm text-gray-400 bg-gray-100 px-3 py-1 rounded-full">
          {{remaining}} remaining
        </span>
      </div>

      <div className="flex gap-2 mb-6">
        <input
          type="text"
          value={{input}}
          onChange={{(e) => setInput(e.target.value)}}
          onKeyDown={{(e) => e.key === "Enter" && add()}}
          placeholder="Add a new {entity.lower()}..."
          className="flex-1 px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-{c}-500 bg-white"
        />
        <button
          onClick={{add}}
          disabled={{!input.trim() || saving}}
          className="px-5 py-2.5 bg-{c}-600 text-white rounded-xl hover:bg-{c}-700 transition font-medium disabled:opacity-50"
        >
          {{saving ? "…" : "Add"}}
        </button>
      </div>

      <div className="flex gap-1 p-1 bg-gray-100 rounded-xl mb-6">
        {{(["all", "active", "done"] as Filter[]).map((f) => (
          <button
            key={{f}}
            onClick={{() => setFilter(f)}}
            className={{`flex-1 py-1.5 rounded-lg text-sm font-medium transition capitalize ${{
              filter === f ? "bg-white shadow-sm text-gray-900" : "text-gray-500 hover:text-gray-700"
            }}`}}
          >{{f}}</button>
        ))}}
      </div>

      {{loading ? (
        <div className="text-center py-16 text-gray-400">Loading…</div>
      ) : (
        <ul className="space-y-2">
          {{filtered.length === 0 && (
            <li className="text-center text-gray-400 py-12 bg-white rounded-2xl border border-dashed border-gray-200">
              No items yet. Add your first one above!
            </li>
          )}}
          {{filtered.map((item) => (
            <li key={{item.id}} className="flex items-center gap-3 p-4 bg-white border border-gray-100 rounded-xl hover:border-gray-200 group transition">
              <input
                type="checkbox"
                checked={{item.completed}}
                onChange={{() => toggle(item.id, item.completed)}}
                className="w-5 h-5 accent-{c}-600 cursor-pointer flex-shrink-0"
              />
              <span className={{`flex-1 ${{item.completed ? "line-through text-gray-400" : "text-gray-800"}}`}}>
                {{item.title}}
              </span>
              <span className="text-xs text-gray-300 hidden group-hover:block mr-2">
                {{new Date(item.createdAt).toLocaleDateString()}}
              </span>
              <button onClick={{() => remove(item.id)}} className="opacity-0 group-hover:opacity-100 text-gray-300 hover:text-red-500 transition p-1" aria-label="Delete">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={{2}} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </li>
          ))}}
        </ul>
      )}}

      {{items.length > 0 && !loading && (
        <div className="mt-4 flex justify-end">
          <button
            onClick={{async () => {{
              const done = items.filter((i) => i.completed);
              await Promise.all(done.map((i) => fetch(`{api}/${{i.id}}`, {{ method: "DELETE" }})));
              setItems((prev) => prev.filter((i) => !i.completed));
            }}}}
            className="text-sm text-gray-400 hover:text-red-500 transition"
          >Clear completed</button>
        </div>
      )}}
    </main>
  );
}}
'''

    # ── TikTok generate page — with Save to Library ────────────────────────────

    @staticmethod
    def tiktok_generate_page_fullstack() -> str:
        return '''"use client";
import { useState } from "react";

interface Persona { handle: string; niche: string; tone: string; }
interface GeneratedContent { hook: string; script: string; hashtags: string[]; caption: string; }

const NICHES   = ["Comedy","Fashion","Food","Finance","Fitness","Education","Gaming","Beauty","Travel","Motivation"];
const TONES    = ["Funny","Casual","Educational","Inspirational","Storytelling","POV","Trendy"];
const FORMATS  = ["Tutorial","Storytime","POV","Tips","Day in My Life","Skit","Reaction"];
const DURATIONS = ["15s","30s","60s","3min"];

function buildContent(topic: string, persona: Persona, format: string, duration: string): GeneratedContent {
  const t     = topic.trim() || "my content";
  const tSlug = t.toLowerCase().replace(/[^a-z0-9]/g, "");

  const hooks: Record<string,string> = {
    Tutorial:        `POV: You\u2019ve been doing ${t} wrong this whole time 😤`,
    Storytime:       `The ${t} situation nobody warned me about... 👀`,
    POV:             `POV: You finally understand ${t} \u2728`,
    Tips:            `5 things about ${t} that changed my life 🤯`,
    "Day in My Life":`Come experience ${t} with me today 📱`,
    Skit:            `Me before ${t} vs. after 💀`,
    Reaction:        `Everyone\u2019s obsessed with ${t} \u2014 here\u2019s the truth 👀`,
  };
  const bodies: Record<string,string> = {
    Tutorial:        `Step 1: [Most surprising fact about ${t}]\nStep 2: [The wrong way most people do it]\nStep 3: [The right way \u2014 keep it visual]\nStep 4: [Quick result or transformation]`,
    Storytime:       `[Set the scene \u2014 where were you?]\n[What happened with ${t}]\n[The turning point \u2014 make them lean in]\n[The resolution / lesson learned]`,
    POV:             `[Put the viewer in the moment with ${t}]\n[Build tension or curiosity in 5s]\n[The reveal or payoff]\n[Relatable reaction shot]`,
    Tips:            `Tip 1: [Quick, specific ${t} tip]\nTip 2: [Something counterintuitive]\nTip 3: [The one they screenshot]\nTip 4: [Advanced move]\nTip 5: [The share-worthy closer]`,
    "Day in My Life": `[Morning \u2014 your ${t} routine]\n[Midday \u2014 real moment or challenge]\n[Evening \u2014 reflection or win]\n[Outro \u2014 call viewer to action]`,
    Skit:            `[Setup: exaggerate the old way]\n[Transition: "and then I discovered..."]\n[Payoff: show the better way]\n[Outro: quick reaction shot]`,
    Reaction:        `[Show the ${t} trend or clip]\n[Your genuine first reaction]\n[Break down why it works / doesn\u2019t]\n[Your hot take / verdict]`,
  };
  const ctas: Record<string,string> = {
    Funny:          `Drop a 😂 if you felt that! Follow ${persona.handle} for more`,
    Casual:         `Save this! Follow ${persona.handle} for the good stuff 💯`,
    Educational:    `Follow ${persona.handle} for more tips like this 🧠`,
    Inspirational:  `Share with someone who needs this 🙌`,
    Storytelling:   `Follow ${persona.handle} \u2014 this is only part 1 👀`,
    POV:            `Comment if you relate! Follow for more POVs 📱`,
    Trendy:         `Duet this & tag me! ${persona.handle} 🔥`,
  };
  const nicheHtags: Record<string,string[]> = {
    Comedy:["#funny","#comedy","#relatable","#lol"],Fashion:["#fashion","#ootd","#style","#outfitinspo"],
    Food:["#foodtok","#recipe","#cooking","#foodie"],Finance:["#moneytok","#finance","#investing","#money"],
    Fitness:["#fitnessmotivation","#workout","#gym","#health"],Education:["#learnontiktok","#didyouknow","#education","#facts"],
    Gaming:["#gaming","#gamer","#videogames","#gamertok"],Beauty:["#beauty","#makeup","#skincare","#beautytips"],
    Travel:["#travel","#wanderlust","#traveltok","#adventure"],Motivation:["#motivation","#mindset","#success","#inspiration"],
  };
  const hook     = hooks[format]      ?? `${t} is changing everything 🔥`;
  const body     = bodies[format]     ?? `[${duration} of ${persona.niche} content about ${t} \u2014 ${persona.tone} tone]`;
  const cta      = ctas[persona.tone] ?? `Follow ${persona.handle} for more 🔔`;
  const nHtags   = nicheHtags[persona.niche] ?? ["#foryoupage","#viral","#trending"];
  const hashtags = ["#fyp","#foryoupage",...nHtags.slice(0,3),`#${tSlug||"tiktok"}`].slice(0,7);
  const caption  = `${hook}\n\n${hashtags.join(" ")}`;
  const script   = `🎥 HOOK (first 3s):\n"${hook}"\n\n📝 BODY (${duration}):\n${body}\n\n🎯 CTA:\n"${cta}"`;
  return { hook, script, hashtags, caption };
}

export default function GeneratePage() {
  const [persona,  setPersona]  = useState<Persona>({ handle: "@mydigitaltwin", niche: "Education", tone: "Casual" });
  const [topic,    setTopic]    = useState("");
  const [format,   setFormat]   = useState("Tutorial");
  const [duration, setDuration] = useState("30s");
  const [result,   setResult]   = useState<GeneratedContent | null>(null);
  const [copied,   setCopied]   = useState<string | null>(null);
  const [loading,  setLoading]  = useState(false);
  const [saving,   setSaving]   = useState(false);
  const [savedMsg, setSavedMsg] = useState("");

  const handleGenerate = () => {
    if (!topic.trim()) return;
    setLoading(true);
    setSavedMsg("");
    setTimeout(() => { setResult(buildContent(topic, persona, format, duration)); setLoading(false); }, 800);
  };

  const handleSave = async () => {
    if (!result) return;
    setSaving(true);
    try {
      const res = await fetch("/api/content", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...result,
          topic,
          format,
          niche:  persona.niche,
          tone:   persona.tone,
          handle: persona.handle,
        }),
      });
      setSavedMsg(res.ok ? "Saved to Library!" : "Save failed.");
    } catch { setSavedMsg("Save failed."); }
    setSaving(false);
    setTimeout(() => setSavedMsg(""), 3000);
  };

  const copy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-6xl mx-auto px-4 py-10">
        <div className="text-center mb-10">
          <h1 className="text-4xl font-bold mb-2">Content <span className="text-rose-500">Generator</span></h1>
          <p className="text-gray-400">Create viral TikTok scripts, captions &amp; hashtags in your twin&apos;s voice</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Twin persona sidebar */}
          <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
            <h2 className="text-lg font-semibold mb-4">👤 Your Twin</h2>
            <div className="mb-4">
              <label className="text-xs text-gray-400 mb-1 block">Handle</label>
              <input value={persona.handle} onChange={(e) => setPersona({ ...persona, handle: e.target.value })}
                placeholder="@yourhandle"
                className="w-full bg-gray-800 border border-gray-700 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-rose-500" />
            </div>
            <div className="mb-4">
              <label className="text-xs text-gray-400 mb-2 block">Niche</label>
              <div className="flex flex-wrap gap-1.5">
                {NICHES.map((n) => (
                  <button key={n} onClick={() => setPersona({ ...persona, niche: n })}
                    className={`text-xs px-2.5 py-1 rounded-full transition ${persona.niche === n ? "bg-rose-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"}`}
                  >{n}</button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-2 block">Tone</label>
              <div className="flex flex-wrap gap-1.5">
                {TONES.map((t) => (
                  <button key={t} onClick={() => setPersona({ ...persona, tone: t })}
                    className={`text-xs px-2.5 py-1 rounded-full transition ${persona.tone === t ? "bg-rose-600 text-white" : "bg-gray-800 text-gray-400 hover:bg-gray-700"}`}
                  >{t}</button>
                ))}
              </div>
            </div>
          </div>

          {/* Generator + results */}
          <div className="lg:col-span-2 space-y-5">
            <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
              <h2 className="text-lg font-semibold mb-4">🎥 Create Content</h2>
              <div className="mb-4">
                <label className="text-xs text-gray-400 mb-1 block">Topic or Idea</label>
                <input value={topic} onChange={(e) => setTopic(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleGenerate()}
                  placeholder="e.g. morning routines, investing basics, easy recipes..."
                  className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-rose-500" />
              </div>
              <div className="grid grid-cols-2 gap-4 mb-5">
                <div>
                  <label className="text-xs text-gray-400 mb-1 block">Format</label>
                  <select value={format} onChange={(e) => setFormat(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-rose-500">
                    {FORMATS.map((f) => <option key={f}>{f}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-gray-400 mb-1 block">Duration</label>
                  <select value={duration} onChange={(e) => setDuration(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-rose-500">
                    {DURATIONS.map((d) => <option key={d}>{d}</option>)}
                  </select>
                </div>
              </div>
              <button onClick={handleGenerate} disabled={!topic.trim() || loading}
                className="w-full bg-rose-600 hover:bg-rose-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-xl transition">
                {loading ? "\u2728 Generating as your Twin\u2026" : "\u2728 Generate as My Digital Twin"}
              </button>
            </div>

            {result && (
              <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800 space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold">📤 Your Content</h2>
                  <div className="flex items-center gap-3">
                    {savedMsg && <span className="text-xs text-green-400">{savedMsg}</span>}
                    <button onClick={handleSave} disabled={saving}
                      className="text-xs bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg transition">
                      {saving ? "Saving\u2026" : "💾 Save to Library"}
                    </button>
                  </div>
                </div>

                <div className="bg-gray-800 rounded-xl p-4">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs text-gray-400 uppercase tracking-wider font-medium">Script</span>
                    <button onClick={() => copy(result.script, "script")} className="text-xs text-rose-400 hover:text-rose-300 transition">
                      {copied === "script" ? "\u2705 Copied!" : "📋 Copy"}
                    </button>
                  </div>
                  <pre className="text-sm whitespace-pre-wrap text-gray-200 font-sans leading-relaxed">{result.script}</pre>
                </div>

                <div className="bg-gray-800 rounded-xl p-4">
                  <div className="flex justify-between items-center mb-3">
                    <span className="text-xs text-gray-400 uppercase tracking-wider font-medium">Hashtags</span>
                    <button onClick={() => copy(result.hashtags.join(" "), "tags")} className="text-xs text-rose-400 hover:text-rose-300 transition">
                      {copied === "tags" ? "\u2705 Copied!" : "📋 Copy All"}
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {result.hashtags.map((tag) => (
                      <span key={tag} className="bg-rose-900/40 text-rose-300 text-xs px-2.5 py-1 rounded-full border border-rose-800/50">{tag}</span>
                    ))}
                  </div>
                </div>

                <div className="bg-gray-800 rounded-xl p-4">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs text-gray-400 uppercase tracking-wider font-medium">Caption</span>
                    <button onClick={() => copy(result.caption, "caption")} className="text-xs text-rose-400 hover:text-rose-300 transition">
                      {copied === "caption" ? "\u2705 Copied!" : "📋 Copy"}
                    </button>
                  </div>
                  <p className="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">{result.caption}</p>
                </div>

                <button onClick={handleGenerate} className="w-full border border-rose-700 text-rose-400 hover:bg-rose-950 font-medium py-2.5 rounded-xl transition text-sm">
                  🔄 Regenerate
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
'''

    # ── TikTok library page — reads saved content from DB ─────────────────────

    @staticmethod
    def tiktok_library_page() -> str:
        return '''"use client";
import { useState, useEffect } from "react";

interface ContentItem {
  id: string;
  hook: string;
  script: string;
  hashtags: string;
  caption: string;
  topic: string;
  format: string;
  niche: string;
  tone: string;
  handle: string;
  createdAt: string;
}

export default function LibraryPage() {
  const [items,   setItems]   = useState<ContentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [copied,  setCopied]  = useState<string | null>(null);
  const [search,  setSearch]  = useState("");

  useEffect(() => {
    fetch("/api/content")
      .then((r) => r.json())
      .then((data) => { setItems(Array.isArray(data) ? data : []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const remove = async (id: string) => {
    await fetch(`/api/content/${id}`, { method: "DELETE" });
    setItems((prev) => prev.filter((i) => i.id !== id));
  };

  const copy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  };

  const tryParseHashtags = (raw: string): string[] => {
    try { return JSON.parse(raw); } catch { return raw.split(" ").filter(Boolean); }
  };

  const filtered = items.filter((i) =>
    search === "" ||
    i.topic.toLowerCase().includes(search.toLowerCase()) ||
    i.niche.toLowerCase().includes(search.toLowerCase()) ||
    i.hook.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-4xl mx-auto px-4 py-10">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold">📚 Content Library</h1>
            <p className="text-gray-400 text-sm mt-1">{items.length} saved piece{items.length !== 1 ? "s" : ""}</p>
          </div>
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="🔍 Search by topic, niche..."
            className="bg-gray-900 border border-gray-700 rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-rose-500 w-48" />
        </div>

        {loading ? (
          <div className="text-center py-20 text-gray-500">Loading your library\u2026</div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-20">
            <p className="text-5xl mb-4">{search ? "🔍" : "📹"}</p>
            <p className="text-gray-400 text-lg">{search ? "No results found." : "No saved content yet."}</p>
            <p className="text-gray-600 text-sm mt-2">{!search && "Generate content and hit \u201cSave to Library\u201d to see it here."}</p>
          </div>
        ) : (
          <div className="space-y-4">
            {filtered.map((item) => {
              const tags = tryParseHashtags(item.hashtags);
              return (
                <div key={item.id} className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <span className="text-xs text-rose-400 font-medium uppercase tracking-wider">{item.niche} \u00b7 {item.format}</span>
                      <h3 className="text-white font-semibold mt-0.5">{item.topic}</h3>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500">{new Date(item.createdAt).toLocaleDateString()}</span>
                      <button onClick={() => remove(item.id)}
                        className="text-gray-600 hover:text-red-500 transition p-1" aria-label="Delete">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </div>

                  <p className="text-gray-300 text-sm leading-relaxed mb-3 italic">&ldquo;{item.hook}&rdquo;</p>

                  <div className="flex flex-wrap gap-1.5 mb-4">
                    {tags.map((tag) => (
                      <span key={tag} className="bg-rose-900/30 text-rose-300 text-xs px-2 py-0.5 rounded-full border border-rose-800/40">{tag}</span>
                    ))}
                  </div>

                  <div className="flex gap-2">
                    <button onClick={() => copy(item.script, `script-${item.id}`)}
                      className="text-xs text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 px-3 py-1.5 rounded-lg transition">
                      {copied === `script-${item.id}` ? "\u2705 Copied!" : "📋 Copy Script"}
                    </button>
                    <button onClick={() => copy(item.caption, `caption-${item.id}`)}
                      className="text-xs text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 px-3 py-1.5 rounded-lg transition">
                      {copied === `caption-${item.id}` ? "\u2705 Copied!" : "📋 Copy Caption"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
'''


# ---------------------------------------------------------------------------
# Requirement heuristics (no LLM needed)
# ---------------------------------------------------------------------------

def _heuristic_requirements(description: str) -> dict:
    """Extract structured requirements from plain text without any LLM call."""
    words = description.lower()

    # --- App name ---
    m = re.search(
        r'(?:build|create|make|develop)\s+(?:a\s+)?(?:an\s+)?([^,.\n]+?)(?:\s+app|\s+website|\s+platform|\s+tool|\s+system|$)',
        description, re.IGNORECASE,
    )
    if m:
        raw = m.group(1).strip()
    else:
        stop = {"a", "an", "the", "build", "create", "make", "develop", "app", "for",
                "with", "using", "that", "which", "is", "to", "and", "or", "in", "of", "my"}
        raw = " ".join(w for w in description.split()[:6] if w.lower() not in stop)
    display_name = raw.title()[:40] or "My App"

    # --- Color ---
    color = "blue"
    for c, tc in [("red", "rose"), ("purple", "purple"), ("green", "green"),
                  ("teal", "teal"), ("orange", "orange"), ("indigo", "indigo"), ("pink", "rose")]:
        if c in words:
            color = tc
            break

    # --- Pages ---
    pages = []
    page_kw = {
        "dashboard":  ("Dashboard",  "dashboard",  "dashboard"),
        "analytic":   ("Analytics",  "analytics",  "dashboard"),
        "metric":     ("Metrics",    "metrics",    "dashboard"),
        "task":       ("Tasks",      "tasks",      "list"),
        "todo":       ("Todos",      "todos",      "list"),
        "note":       ("Notes",      "notes",      "list"),
        "product":    ("Products",   "products",   "list"),
        "project":    ("Projects",   "projects",   "list"),
        "user":       ("Users",      "users",      "list"),
        "customer":   ("Customers",  "customers",  "list"),
        "order":      ("Orders",     "orders",     "list"),
        "item":       ("Items",      "items",      "list"),
        "blog":       ("Blog",       "blog",       "list"),
        "post":       ("Posts",      "posts",      "list"),
        "portfolio":  ("Portfolio",  "portfolio",  "info"),
        "gallery":    ("Gallery",    "gallery",    "info"),
        "about":      ("About",      "about",      "info"),
        "team":       ("Team",       "team",       "info"),
        "contact":    ("Contact",    "contact",    "form"),
        "setting":    ("Settings",   "settings",   "form"),
        "profile":    ("Profile",    "profile",    "form"),
        "search":     ("Search",     "search",     "info"),
    }
    seen_slugs: set = set()
    for kw, (name, slug, ptype) in page_kw.items():
        if kw in words and slug not in seen_slugs and len(pages) < 3:
            pages.append({"name": name, "slug": slug, "type": ptype, "description": f"{name} page"})
            seen_slugs.add(slug)

    # --- Features ---
    feat_kw = [
        ("search",       "🔍", "Smart Search",        "Find anything instantly"),
        ("filter",       "🎛️", "Smart Filters",       "Filter and sort with ease"),
        ("export",       "📤", "Export",               "Export your data anytime"),
        ("auth",         "🔒", "Authentication",      "Secure login and accounts"),
        ("notification", "🔔", "Notifications",       "Real-time alerts"),
        ("dark",         "🌙", "Dark Mode",            "Easy on the eyes"),
        ("responsive",   "📱", "Responsive",          "Works on every device"),
        ("real-time",    "⚡", "Real-time",           "Live updates instantly"),
        ("report",       "📊", "Reports",             "Insights at a glance"),
        ("api",          "🔗", "API Access",          "Integrate with anything"),
        ("drag",         "↕️", "Drag & Drop",         "Intuitive re-ordering"),
        ("import",       "📥", "Import",              "Bring in existing data"),
    ]
    features = []
    for kw, icon, name, desc in feat_kw:
        if kw in words and len(features) < 4:
            features.append({"name": name, "desc": desc, "icon": icon})

    if not features:
        features = [
            {"name": "Fast",      "desc": "Lightning fast performance",    "icon": "⚡"},
            {"name": "Beautiful", "desc": "Modern and clean design",       "icon": "🎨"},
            {"name": "Reliable",  "desc": "Built to scale with you",       "icon": "🛡️"},
        ]

    app_name = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-") or "nexus-app"
    tagline = f"The best {display_name} experience, built for you."

    # --- Platform-specific overrides ---
    app_type = "generic"
    if "tiktok" in words or "tik tok" in words:
        app_type = "tiktok_digital_twin"
        color = "rose"
        display_name = (
            "TikTok Digital Twin" if ("twin" in words or "digital" in words)
            else "TikTok Creator Studio"
        )
        app_name = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-")
        tagline = "Your AI digital twin — create viral TikTok content in your voice"
        features = [
            {"name": "AI Script Generator", "desc": "Generate hooks, scripts & CTAs in your voice", "icon": "🤖"},
            {"name": "Smart Hashtags",      "desc": "Data-driven hashtag bundles for max reach",    "icon": "🎯"},
            {"name": "Digital Twin",        "desc": "Your AI persona trained on your content style", "icon": "👤"},
            {"name": "Content Calendar",    "desc": "Plan and schedule your TikTok pipeline",        "icon": "📅"},
            {"name": "Caption Writer",      "desc": "Magnetic captions that drive clicks & follows", "icon": "✍️"},
            {"name": "Trend Alerts",        "desc": "Spot viral trends that match your niche",       "icon": "📈"},
        ]
        pages = [
            {"name": "Generate", "slug": "generate", "type": "tiktok_generate", "description": "AI content generator"},
            {"name": "My Twin",  "slug": "twin",     "type": "info",            "description": "Digital twin settings"},
            {"name": "Library",  "slug": "library",  "type": "tiktok_library",  "description": "Saved content library"},
            {"name": "Analytics","slug": "analytics","type": "dashboard",       "description": "Performance analytics"},
        ]

    return {
        "app_name":     app_name,
        "display_name": display_name,
        "tagline":      tagline,
        "summary":      description[:200],
        "color":        color,
        "features":     features,
        "pages":        pages,
        "app_type":     app_type,
        # Compatibility fields for old code paths
        "core_features": [{"name": f["name"], "description": f["desc"]} for f in features],
        "data_models":  [],
    }


def _detect_page_type(name: str, desc: str, features: list) -> str:
    """Guess page type from name, description, and app features."""
    combined = (name + " " + desc).lower()
    feat_text = " ".join(f.get("name", "") + " " + f.get("desc", "") for f in features).lower()

    if any(w in combined for w in ["dashboard", "analytics", "metric", "stats", "report", "overview"]):
        return "dashboard"
    if any(w in combined for w in ["contact", "send", "message", "form", "submit", "feedback"]):
        return "form"
    if any(w in combined for w in ["list", "task", "todo", "note", "item", "manage", "crud",
                                    "add", "delete", "edit", "create", "track"]):
        return "list"
    return "info"


# ---------------------------------------------------------------------------
# Build orchestrator
# ---------------------------------------------------------------------------

class BuildOrchestrator:
    """Template-first app builder — always produces a working app with max 1 LLM call."""

    def __init__(
        self,
        gemini_client=None,
        api_key: Optional[str] = None,
        memory: Optional[MemoryEcology] = None,
        workspace_root: str = "./workspace",
    ):
        if gemini_client is not None:
            self.llm = gemini_client
        else:
            from gemini_client import GeminiClient
            self.llm = GeminiClient(api_key=api_key)

        self.fs       = FileSystemTool(workspace_root=workspace_root)
        self.terminal = TerminalTool(default_cwd=workspace_root)
        self.git      = GitManager(self.terminal)
        self.pkg      = PackageManager(self.terminal)
        self.memory   = memory or MemoryEcology()

        self.project:         Dict = {}
        self.phases:          List[BuildPhase] = [BuildPhase(n, d, o) for n, d, o in _PHASE_DEFS]
        self.generated_files: Dict[str, str] = {}

        self._llm_calls    = 0
        self._llm_failures = 0

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def start_build(self, user_description: str) -> str:
        print("\n" + "=" * 60)
        print("  🏗️  NEXUS APP BUILDER  -  Starting New Build")
        print("  📋 Mode: Template-first (max 1 LLM call)")
        print("=" * 60)

        try:
            # Phase 1: Requirements (1 LLM call, or heuristic fallback)
            self._set_phase("requirements", "running")
            reqs = self._phase_requirements(user_description)
            self._set_phase("requirements", "passed")

            # Phase 2: Architecture (0 LLM calls)
            self._set_phase("architecture", "running")
            arch = self._phase_architecture(reqs)
            self._set_phase("architecture", "passed")

            # Phase 3: Tech stack (0 LLM calls)
            self._set_phase("tech_selection", "running")
            tech = self._phase_tech_stack(reqs, arch)
            self._set_phase("tech_selection", "passed")

            # Phase 4: Scaffold (0 LLM calls)
            self._set_phase("scaffolding", "running")
            project_path = self._phase_scaffold(reqs, arch, tech)
            self._set_phase("scaffolding", "passed")

            # Phase 5: Template generation (0 LLM calls)
            self._set_phase("core_implementation", "running")
            self._phase_implement(project_path, reqs, arch, tech)
            self._set_phase("core_implementation", "passed")

            # Phase 6: Build + auto-fix
            self._set_phase("testing", "running")
            build_ok, errors = self._phase_test(project_path, tech)

            if not build_ok:
                self._set_phase("debugging", "running")
                build_ok = self._phase_autofix(project_path, tech, errors)
                self._set_phase("debugging", "passed" if build_ok else "failed")
            else:
                self._set_phase("debugging", "passed")

            self.project["build_ok"] = build_ok

            # Phase 7: Docs (0 LLM calls)
            self._set_phase("documentation", "running")
            self._phase_docs(project_path, reqs, tech)
            self._set_phase("documentation", "passed")

            # Phase 8: Deploy prep (0 LLM calls)
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
    # LLM helpers
    # ------------------------------------------------------------------

    def _track_llm_result(self, result: str) -> str:
        self._llm_calls += 1
        if not result or not result.strip():
            self._llm_failures += 1
        return result

    # ------------------------------------------------------------------
    # Phase 1  -  Requirements (1 LLM call max)
    # ------------------------------------------------------------------

    def _phase_requirements(self, description: str) -> dict:
        print("\n📋 Phase 1: Parsing requirements…")

        system = """Parse this app description. Return ONLY valid JSON, nothing else:
{
    "display_name": "Title Case App Name (2-4 words)",
    "tagline": "One-line value proposition (max 10 words)",
    "color": "blue",
    "features": [{"name": "...", "desc": "...", "icon": "emoji"}],
    "pages": [{"name": "...", "slug": "url-slug", "type": "list|dashboard|form|info"}]
}
RULES:
- color: exactly one of: blue, purple, green, teal, orange, rose, indigo
- features: max 4 items, each with an emoji icon
- pages: max 3 items, NOT including home (home is always generated)
- type "list"=CRUD list, "dashboard"=stats/metrics, "form"=contact/input, "info"=static content
- Be concise — short names and descriptions only"""

        result = self._track_llm_result(
            # fail_fast=True: if rate-limited, return "" immediately (no sleeping).
            # retries=1: only one attempt — we have heuristics as instant fallback.
            self.llm.generate(system, f"App idea:\n{description}", max_tokens=512,
                              retries=1, fail_fast=True)
        )
        parsed = self.llm.extract_json(result) if result else {}

        if not parsed or not parsed.get("display_name"):
            print("   ✅ Using heuristic parser (0 wait, 0 LLM calls)")
            reqs = _heuristic_requirements(description)
        else:
            # Normalise the compact LLM response into the standard format
            reqs = {
                "display_name": parsed.get("display_name", "My App"),
                "tagline":      parsed.get("tagline", ""),
                "color":        parsed.get("color", "blue"),
                "features":     parsed.get("features", []),
                "pages":        parsed.get("pages", []),
                "summary":      description[:200],
                # Compatibility
                "core_features": [
                    {"name": f.get("name", ""), "description": f.get("desc", "")}
                    for f in parsed.get("features", [])
                ],
                "data_models": [],
            }

        # Derive sanitised app_name from display_name
        display = reqs.get("display_name", "My App")
        app_name = re.sub(r"[^a-z0-9]+", "-", display.lower()).strip("-") or "nexus-app"
        reqs["app_name"] = app_name

        # Ensure color is valid
        if reqs.get("color", "blue") not in _COLORS:
            reqs["color"] = "blue"

        self.project["requirements"] = reqs
        print(f"   ✅ App: {reqs['display_name']}")
        print(f"   ✅ Color: {reqs['color']}")
        print(f"   ✅ Features: {len(reqs.get('features', []))}")
        print(f"   ✅ Extra pages: {len(reqs.get('pages', []))}")
        return reqs

    # ------------------------------------------------------------------
    # Phase 2  -  Architecture (0 LLM calls)
    # ------------------------------------------------------------------

    def _phase_architecture(self, reqs: dict) -> dict:
        print("\n🏛️  Phase 2: Architecture (template-based, 0 LLM calls)…")
        # Always Next.js 14 App Router — the only target our templates support
        arch = {
            "structure":          "single",
            "frontend_framework": "next.js",
            "backend_framework":  "next.js-api",
            "database":           "none",
            "auth":               "none",
        }
        self.project["architecture"] = arch
        print("   ✅ Next.js 14 App Router (single-app)")
        return arch

    # ------------------------------------------------------------------
    # Phase 3  -  Tech stack (0 LLM calls)
    # ------------------------------------------------------------------

    def _phase_tech_stack(self, reqs: dict, arch: dict) -> dict:
        print("\n⚙️  Phase 3: Tech stack (0 LLM calls)…")
        tech = {
            "type":      "single",
            "framework": "next.js",
            "language":  "typescript",
            "styling":   "tailwindcss",
            "database":  "prisma-sqlite",
            "build_dir": ".",
        }
        self.project["tech"] = tech
        print("   ✅ Next.js 14 + TypeScript + Tailwind CSS + Prisma SQLite")
        return tech

    # ------------------------------------------------------------------
    # Phase 4  -  Scaffolding (0 LLM calls)
    # ------------------------------------------------------------------

    def _phase_scaffold(self, reqs: dict, arch: dict, tech: dict) -> str:
        app_name     = reqs["app_name"]
        project_path = str(self.fs.workspace / app_name)

        print(f"\n🗂️  Phase 4: Scaffolding '{app_name}' at {project_path}…")

        # Clean stale source files but keep node_modules to skip re-install
        if os.path.isdir(project_path):
            for d in ["src", "public"]:
                full_d = os.path.join(project_path, d)
                if os.path.isdir(full_d):
                    shutil.rmtree(full_d)
            for f in ["tailwind.config.ts", "tailwind.config.js",
                      "postcss.config.mjs", "postcss.config.js",
                      "next.config.mjs", "next.config.js",
                      "vercel.json", "tsconfig.json"]:
                full_f = os.path.join(project_path, f)
                if os.path.isfile(full_f):
                    os.remove(full_f)
            self.generated_files.clear()
            print("   🧹 Cleaned stale files from previous build")

        self.fs.create_directory(project_path)
        self._scaffold_single(project_path, app_name, reqs, tech)
        self.git.init_repo(project_path)
        self.git.commit(project_path, "Initial scaffold by NEXUS")
        self.project["path"] = project_path
        return project_path

    def _scaffold_single(self, project_path: str, app_name: str, reqs: dict, tech: dict):
        """Write package.json, tsconfig, tailwind config, next.config — then npm install."""
        display = reqs.get("display_name", app_name)

        pkg = {
            "name": app_name,
            "version": "0.1.0",
            "private": True,
            "scripts": {
                "dev":         "next dev",
                "build":       "next build",
                "start":       "next start",
                "lint":        "next lint",
                "postinstall": "prisma generate",
            },
            "dependencies": {
                "next":            "^14.2.5",
                "react":           "^18.3.1",
                "react-dom":       "^18.3.1",
                "@prisma/client":  "^5.16.0",
                "clsx":            "^2.1.1",
                "lucide-react":    "^0.400.0",
                "tailwind-merge":  "^2.4.0",
            },
            "devDependencies": {
                "@types/node":     "^20",
                "@types/react":    "^18",
                "@types/react-dom":"^18",
                "typescript":      "^5",
                "tailwindcss":     "^3.4.7",
                "postcss":         "^8.4.41",
                "autoprefixer":    "^10.4.19",
                "prisma":          "^5.16.0",
            },
        }
        self.fs.write_file(os.path.join(project_path, "package.json"), json.dumps(pkg, indent=2))

        tsconfig = {
            "compilerOptions": {
                "lib":              ["dom", "dom.iterable", "esnext"],
                "allowJs":          True,
                "skipLibCheck":     True,
                "strict":           True,
                "noEmit":           True,
                "esModuleInterop":  True,
                "module":           "esnext",
                "moduleResolution": "bundler",
                "resolveJsonModule":True,
                "isolatedModules":  True,
                "jsx":              "preserve",
                "incremental":      True,
                "plugins":          [{"name": "next"}],
                "paths":            {"@/*": ["./src/*"]},
            },
            "include":  ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
            "exclude":  ["node_modules"],
        }
        self.fs.write_file(os.path.join(project_path, "tsconfig.json"), json.dumps(tsconfig, indent=2))

        # Tailwind config — include all primary color classes so Tailwind doesn't purge them
        color = reqs.get("color", "blue")
        c = _col(color)[0]
        self.fs.write_file(
            os.path.join(project_path, "tailwind.config.ts"),
            f'import type {{ Config }} from "tailwindcss";\n\n'
            f'const config: Config = {{\n'
            f'  content: ["./src/**/*.{{js,ts,jsx,tsx,mdx}}"],\n'
            f'  safelist: [\n'
            f'    // Safelist primary color so dynamic class names are not purged\n'
            f'    {{ pattern: /^(bg|text|border|ring|accent|from|to)-{c}-/ }},\n'
            f'  ],\n'
            f'  theme: {{ extend: {{}} }},\n'
            f'  plugins: [],\n'
            f'}};\n'
            f'export default config;\n',
        )

        self.fs.write_file(
            os.path.join(project_path, "postcss.config.mjs"),
            "/** @type {import('postcss-load-config').Config} */\n"
            "const config = {\n"
            "  plugins: { tailwindcss: {}, autoprefixer: {} },\n"
            "};\nexport default config;\n",
        )

        self.fs.write_file(
            os.path.join(project_path, "next.config.mjs"),
            "/** @type {import('next').NextConfig} */\n"
            "const nextConfig = {};\nexport default nextConfig;\n",
        )

        for sub in ["src", "src/app", "src/components", "src/lib", "public", "prisma"]:
            self.fs.create_directory(os.path.join(project_path, sub))

        # Write prisma schema (placeholder — real schema written in Phase 5 after pages are known)
        self.fs.write_file(
            os.path.join(project_path, "prisma", "schema.prisma"),
            'datasource db {\n  provider = "sqlite"\n  url      = env("DATABASE_URL")\n}\n\n'
            'generator client {\n  provider = "prisma-client-js"\n}\n\n'
            'model Item {\n  id        String   @id @default(cuid())\n'
            '  title     String\n  completed Boolean  @default(false)\n'
            '  createdAt DateTime @default(now())\n  updatedAt DateTime @updatedAt\n}\n',
        )
        self.fs.write_file(
            os.path.join(project_path, ".env"),
            'DATABASE_URL="file:./dev.db"\n',
        )

        print("   📦 Installing dependencies…")
        _, stderr, code = self.terminal.run("npm install", cwd=project_path, timeout=240)
        print(f"   {'✅' if code == 0 else '⚠️ '} npm install {'OK' if code == 0 else stderr[:120]}")

        # Push initial placeholder schema so Prisma client exists
        _, _, pc = self.terminal.run("npx prisma db push --accept-data-loss", cwd=project_path, timeout=120)
        print(f"   {'✅' if pc == 0 else '⚠️ '} Prisma DB initialised")

    # ------------------------------------------------------------------
    # Phase 5  -  Template generation (0 LLM calls)
    # ------------------------------------------------------------------

    def _phase_implement(self, project_path: str, reqs: dict, arch: dict, tech: dict):
        print("\n💻 Phase 5: Generating full-stack app from templates (0 LLM calls)…")

        display  = reqs.get("display_name", "My App")
        tagline  = reqs.get("tagline", f"The best {display} experience")
        summary  = reqs.get("summary", "")
        color    = reqs.get("color", "blue")
        features = reqs.get("features", [])
        pages    = reqs.get("pages", [])
        app_type = reqs.get("app_type", "generic")

        # ------------------------------------------------------------------
        # Write real Prisma schema (now that we know the pages)
        # ------------------------------------------------------------------
        schema_content = _T.prisma_schema(pages)
        schema_path = os.path.join(project_path, "prisma", "schema.prisma")
        os.makedirs(os.path.dirname(schema_path), exist_ok=True)
        self.fs.write_file(schema_path, schema_content)
        print("   📝 prisma/schema.prisma (full schema)")

        # Apply schema to DB
        _, _, pc = self.terminal.run("npx prisma db push --accept-data-loss", cwd=project_path, timeout=120)
        print(f"   {'✅' if pc == 0 else '⚠️ '} Prisma schema pushed to SQLite")

        # Core files every Next.js 14 app needs
        files: Dict[str, str] = {
            "src/app/globals.css":       _T.globals_css(color),
            "src/app/layout.tsx":        _T.layout(display, summary),
            "src/app/page.tsx":          _T.home_page(display, tagline, summary, features, pages, color),
            "src/components/Navbar.tsx": _T.navbar(display, pages, color),
            "src/lib/db.ts":             _T.db_client(),
        }

        # ------------------------------------------------------------------
        # TikTok-specific API routes (content + settings)
        # ------------------------------------------------------------------
        if app_type == "tiktok_digital_twin":
            files["src/app/api/content/route.ts"]        = _T.tiktok_content_api()
            files["src/app/api/content/[id]/route.ts"]   = _T.tiktok_content_id_api()
            files["src/app/api/settings/route.ts"]       = _T.tiktok_settings_api()

        # ------------------------------------------------------------------
        # Generate one page per entry in pages
        # ------------------------------------------------------------------
        for page in pages[:4]:
            slug = page.get("slug", "").strip().strip("/")
            if not slug:
                continue
            name  = page.get("name", slug.title())
            desc  = page.get("description", "")
            ptype = page.get("type", "") or _detect_page_type(name, desc, features)

            if ptype == "tiktok_generate":
                content = _T.tiktok_generate_page_fullstack()

            elif ptype == "tiktok_library":
                content = _T.tiktok_library_page()

            elif ptype == "list":
                # Derive model name (singular, CamelCase) and camelCase var
                raw   = name.rstrip("s") if name.lower().endswith("s") else name
                model = "".join(w.capitalize() for w in re.split(r"[-_ ]+", raw) if w)
                var   = model[0].lower() + model[1:]
                # Generate API routes for this list
                api_dir = os.path.join(project_path, "src", "app", "api", slug)
                api_id_dir = os.path.join(api_dir, "[id]")
                os.makedirs(api_dir, exist_ok=True)
                os.makedirs(api_id_dir, exist_ok=True)
                self.fs.write_file(os.path.join(api_dir, "route.ts"),    _T.api_list_route(var))
                self.fs.write_file(os.path.join(api_id_dir, "route.ts"), _T.api_item_route(var))
                print(f"   📝 src/app/api/{slug}/route.ts")
                print(f"   📝 src/app/api/{slug}/[id]/route.ts")
                content = _T.crud_page_fullstack(name, slug, color)

            elif ptype == "dashboard":
                content = _T.dashboard_page(name, color)
            elif ptype == "form":
                content = _T.form_page(name, desc, color)
            else:
                content = _T.info_page(name, desc, display, color)

            # Create sub-directory for the route
            self.fs.create_directory(os.path.join(project_path, "src", "app", slug))
            files[f"src/app/{slug}/page.tsx"] = content

        # Write all files
        for rel_path, content in files.items():
            full = os.path.join(project_path, rel_path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            if self.fs.write_file(full, content):
                self.generated_files[rel_path] = content
                print(f"   📝 {rel_path}")

        self.git.commit(project_path, "Full-stack implementation by NEXUS (Prisma + API routes)")
        print(f"\n   ✅ {len(files)} files generated (database + API routes + frontend)")

    # ------------------------------------------------------------------
    # Phase 6  -  Test (run npm build)
    # ------------------------------------------------------------------

    def _phase_test(self, project_path: str, tech: dict):
        print("\n🧪 Phase 6: Building…")

        if not os.path.exists(os.path.join(project_path, "node_modules")):
            print("   📦 Installing dependencies…")
            self.terminal.run("npm install", cwd=project_path, timeout=240)

        stdout, stderr, code = self.terminal.run("npm run build 2>&1", cwd=project_path, timeout=180)

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
    # Phase 7  -  Auto-fix (no LLM — pattern-based only)
    # ------------------------------------------------------------------

    def _phase_autofix(self, project_path: str, tech: dict, errors: str) -> bool:
        print("\n🔧 Phase 7: Auto-fixing…")
        fixed_any = False

        # Fix 1: missing 'use client' on hook-using files
        if "useState" in errors or "useEffect" in errors or "use client" in errors:
            n = self._fix_client_directives(project_path)
            if n:
                print(f"   🔧 Added 'use client' to {n} file(s)")
                fixed_any = True

        # Fix 2: missing root layout
        if "doesn't have a root layout" in errors or "does not have a root layout" in errors:
            layout_path = os.path.join(project_path, "src", "app", "layout.tsx")
            if not os.path.exists(layout_path):
                reqs = self.project.get("requirements", {})
                content = _T.layout(
                    reqs.get("display_name", "App"),
                    reqs.get("summary", "Built with NEXUS"),
                )
                self.fs.write_file(layout_path, content)
                self.generated_files["src/app/layout.tsx"] = content
                print("   🔧 Created missing src/app/layout.tsx")
                fixed_any = True

        # Fix 3: broken relative imports → create stubs
        if "Module not found" in errors:
            broken = self._validate_imports(project_path)
            if broken:
                n = self._fix_broken_imports(project_path, broken)
                if n:
                    print(f"   🔧 Fixed/stubbed {n} broken import(s)")
                    fixed_any = True

        # Fix 4: missing globals.css
        globals_path = os.path.join(project_path, "src", "app", "globals.css")
        if not os.path.exists(globals_path):
            reqs = self.project.get("requirements", {})
            css = _T.globals_css(reqs.get("color", "blue"))
            self.fs.write_file(globals_path, css)
            print("   🔧 Created missing globals.css")
            fixed_any = True

        if not fixed_any:
            print("   ℹ️  No auto-fix patterns matched — build errors may need manual review")
            return False

        self.git.commit(project_path, "Auto-fix: pattern-based corrections")

        # Re-run build
        stdout, stderr, code = self.terminal.run("npm run build 2>&1", cwd=project_path, timeout=180)
        if code == 0:
            print("   ✅ Build passed after auto-fix!")
            return True

        print("   ⚠️  Build still failing after auto-fix:")
        for line in (stderr or stdout).split("\n")[:8]:
            if line.strip():
                print(f"      {line.strip()}")
        return False

    # ------------------------------------------------------------------
    # Phase 8  -  Docs (0 LLM calls)
    # ------------------------------------------------------------------

    def _phase_docs(self, project_path: str, reqs: dict, tech: dict):
        print("\n📚 Phase 8: Generating documentation…")
        features = reqs.get("features", reqs.get("core_features", []))
        feat_md = "\n".join(
            f"- **{f.get('name', '')}**: {f.get('desc', f.get('description', ''))}"
            for f in features
        )
        readme = (
            f"# {reqs.get('display_name', reqs['app_name'])}\n\n"
            f"{reqs.get('tagline', reqs.get('summary', ''))}\n\n"
            f"## Features\n{feat_md}\n\n"
            f"## Getting Started\n"
            f"```bash\nnpm install\nnpm run dev\n```\n\n"
            f"Open [http://localhost:3000](http://localhost:3000) in your browser.\n\n"
            f"## Build\n"
            f"```bash\nnpm run build\nnpm start\n```\n\n"
            f"_Built with NEXUS — template-first AI app builder_\n"
        )
        self.fs.write_file(os.path.join(project_path, "README.md"), readme)
        self.git.commit(project_path, "Add README")
        print("   ✅ README.md written")

    # ------------------------------------------------------------------
    # Phase 9  -  Deploy prep (0 LLM calls)
    # ------------------------------------------------------------------

    def _phase_deploy(self, project_path: str, tech: dict) -> dict:
        print("\n🚀 Phase 9: Deployment prep…")
        vercel = {
            "version": 2,
            "builds": [{"src": "package.json", "use": "@vercel/next"}],
        }
        self.fs.write_file(
            os.path.join(project_path, "vercel.json"),
            json.dumps(vercel, indent=2),
        )
        self.git.commit(project_path, "Add vercel.json")
        deploy = {
            "platform":    "vercel",
            "command":     "vercel --prod",
            "docs_url":    "https://vercel.com/docs",
            "preview_url": f"https://{self.project.get('requirements', {}).get('app_name', 'app')}.vercel.app",
        }
        print(f"   ✅ Ready for Vercel — run: {deploy['command']}")
        return deploy

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _summary(self, project_path: str, deploy: dict) -> str:
        reqs     = self.project.get("requirements", {})
        build_ok = self.project.get("build_ok", True)
        name     = reqs.get("display_name", reqs.get("app_name", "App"))
        color    = reqs.get("color", "blue")
        pages    = reqs.get("pages", [])

        extra_pages = [p.get("name", "") for p in pages if p.get("slug", "").strip("/")]
        all_routes  = ["/ (home)"] + [f"/{p.get('slug', '')}" for p in pages if p.get("slug")]

        lines = [
            "\n" + "=" * 60,
            f"  🎉  Build Complete: {name}",
            "=" * 60,
            f"  📂 Location:   {project_path}",
            f"  🎨 Color:      {color}",
            f"  📄 Pages:      {', '.join(all_routes)}",
            f"  🔨 Build:      {'✅ PASSED' if build_ok else '⚠️  check errors above'}",
            "",
            "  To run locally:",
            f"    cd {project_path}",
            "    npm run dev",
            "",
            f"  To deploy:  {deploy.get('command', 'vercel --prod')}",
            "=" * 60,
        ]
        result = "\n".join(lines)
        print(result)
        return result

    # ------------------------------------------------------------------
    # Phase tracking
    # ------------------------------------------------------------------

    def _set_phase(self, name: str, status: str):
        for phase in self.phases:
            if phase.name == name:
                phase.status = status
                if status == "running":
                    phase.start_time = time.time()
                elif status in ("passed", "failed"):
                    phase.end_time = time.time()
                break

    # ------------------------------------------------------------------
    # Import validation + auto-fix helpers (unchanged from v1)
    # ------------------------------------------------------------------

    def _validate_imports(self, project_path: str) -> list:
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
                    base     = os.path.dirname(fpath)
                    resolved = os.path.normpath(os.path.join(base, imp))
                    exists   = any(
                        os.path.exists(resolved + ext)
                        for ext in ["", ".ts", ".tsx", "/index.ts", "/index.tsx"]
                    )
                    if not exists:
                        rel_file = fpath.replace(project_path + os.sep, "").replace("\\", "/")
                        broken.append(f"{rel_file}: missing '{imp}'")
        return broken

    def _fix_broken_imports(self, project_path: str, broken: list) -> int:
        by_file: Dict[str, list] = {}
        for entry in broken:
            m = re.match(r"(.+): missing '([^']+)'", entry.replace("\\", "/"))
            if m:
                rel, imp = m.group(1).strip(), m.group(2).strip()
                by_file.setdefault(rel, []).append(imp)

        comp_dir   = os.path.join(project_path, "src", "components")
        comp_slugs: Dict[str, str] = {}
        if os.path.isdir(comp_dir):
            for f in os.listdir(comp_dir):
                if f.endswith(".tsx"):
                    slug = f[:-4].lower().replace("-", "").replace("_", "")
                    comp_slugs[slug] = f[:-4]

        modified = 0
        for rel_path, missing_imports in by_file.items():
            fpath   = os.path.join(project_path, rel_path.replace("/", os.sep))
            content = self.fs.read_file(fpath)
            if not content:
                continue
            original = content

            for imp in missing_imports:
                imp_basename = imp.split("/")[-1]

                # Rule 1: remove App Router layout re-imports
                if re.search(r"[/\\]layout$", imp) or imp in ("../layout", "../../layout"):
                    content = re.sub(
                        r'import\s+\S+\s+from\s+["\']' + re.escape(imp) + r'["\'];\s*\n?',
                        "", content,
                    )
                    content = re.sub(r"<Layout[^>]*>([\s\S]*?)</Layout>", r"\1", content)
                    continue

                # Rule 2: remap missing component
                if "component" in imp or "/components/" in imp or imp.startswith("../../"):
                    slug       = imp_basename.lower().replace("-", "").replace("_", "")
                    match_name = comp_slugs.get(slug) or next(
                        (cn for cs, cn in comp_slugs.items() if slug[:6] in cs or cs[:6] in slug), None
                    )
                    if match_name:
                        rel_comp = os.path.relpath(
                            os.path.join(comp_dir, match_name), os.path.dirname(fpath)
                        ).replace("\\", "/")
                        if not rel_comp.startswith("."):
                            rel_comp = "./" + rel_comp
                        content = content.replace(f'"{imp}"', f'"{rel_comp}"').replace(f"'{imp}'", f"'{rel_comp}'")
                        continue
                    # Create stub
                    comp_name = "".join(w.capitalize() for w in re.split(r"[-_]", imp_basename))
                    stub      = f'"use client";\nexport default function {comp_name}() {{ return <div className="{imp_basename}"></div>; }}\n'
                    stub_path = os.path.join(comp_dir, imp_basename + ".tsx")
                    self.fs.write_file(stub_path, stub)
                    rel_comp  = os.path.relpath(stub_path, os.path.dirname(fpath)).replace("\\", "/")
                    if not rel_comp.startswith("."):
                        rel_comp = "./" + rel_comp
                    content   = content.replace(f'"{imp}"', f'"{rel_comp}"').replace(f"'{imp}'", f"'{rel_comp}'")
                    continue

                # Rule 3: simple local imports → create stub
                if imp.startswith("./") and "/" not in imp[2:]:
                    stub_name = imp[2:]
                    stub_path = os.path.join(os.path.dirname(fpath), stub_name + ".tsx")
                    if not os.path.exists(stub_path):
                        comp_name = stub_name.capitalize()
                        self.fs.write_file(stub_path,
                            f'export default function {comp_name}() {{ return <div className="{stub_name}"></div>; }}\n')
                    continue

                # Rule 4: lib/models/services stubs
                _util_dirs = {"lib", "models", "services", "hooks", "utils", "types", "helpers"}
                imp_parts  = imp.replace("\\", "/").split("/")
                if any(p in _util_dirs for p in imp_parts):
                    base_dir = os.path.dirname(fpath)
                    resolved = os.path.normpath(os.path.join(base_dir, imp))
                    if not os.path.exists(resolved + ".ts") and not os.path.exists(resolved + ".tsx"):
                        low = imp_basename.lower()
                        fn  = "".join(w.capitalize() for w in re.split(r"[-_]", imp_basename) if w)
                        if any(kw in low for kw in ["db", "database", "prisma", "sql"]):
                            stub_content = (
                                "export async function query(_sql: string, _p?: unknown[]) { return []; }\n"
                                "export const db = { query: async (_s: string) => ({ rows: [] as unknown[] }) };\n"
                                "export default db;\n"
                            )
                        else:
                            stub_content = f"export function get{fn}() {{ return []; }}\nexport default get{fn};\n"
                        os.makedirs(os.path.dirname(resolved + ".ts"), exist_ok=True)
                        self.fs.write_file(resolved + ".ts", stub_content)
                    continue

            if content != original:
                self.fs.write_file(fpath, content)
                modified += 1

        return modified

    def _fix_client_directives(self, project_path: str) -> int:
        _HOOKS = re.compile(
            r'\b(useState|useEffect|useContext|useReducer|useRef|useCallback|useMemo'
            r'|useLayoutEffect|useTransition|useDeferredValue)\s*\('
        )
        skip_dirs = {"node_modules", ".git", ".next", "dist", "build"}
        fixed = 0
        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fname in files:
                if not fname.endswith((".tsx", ".ts")):
                    continue
                fpath   = os.path.join(root, fname)
                content = self.fs.read_file(fpath) or ""
                rel     = fpath.replace(project_path + os.sep, "").replace("\\", "/")
                if fname == "route.ts" and "/api/" in rel:
                    continue
                if '"use client"' in content or "'use client'" in content:
                    continue
                if _HOOKS.search(content):
                    content = '"use client";\n' + content
                    self.fs.write_file(fpath, content)
                    self.generated_files[rel] = content
                    fixed += 1
        return fixed
