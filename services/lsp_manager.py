"""LSP Server Lifecycle Manager.

Manages Language Server Protocol server instances across worktrees.
Handles automatic detection, installation, health monitoring, and
graceful lifecycle management for 22 built-in language server specs
organized into four priority tiers.

Servers are lazily started on first use and automatically restarted
on crash (up to max_restarts). Configuration is loaded from
.swarmweaver/lsp.yaml with environment variable overrides.
"""

import asyncio
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from services.lsp_client import LSPClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LSPServerStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    CRASHED = "crashed"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class LSPServerSpec:
    """Specification for a language server binary."""

    language_id: str
    server_name: str
    command: str
    args: list[str] = field(default_factory=list)
    install_command: str = ""
    install_check: str = ""
    extensions: list[str] = field(default_factory=list)
    project_markers: list[str] = field(default_factory=list)
    init_options: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)
    priority: int = 1  # 1 = core, 2 = secondary, 3 = specialty, 4 = config/markup


@dataclass
class LSPServerInstance:
    """A running (or recently-stopped) language server."""

    spec: LSPServerSpec
    root_uri: str
    client: Optional[LSPClient] = None
    process: Optional[subprocess.Popen] = None
    pid: Optional[int] = None
    status: LSPServerStatus = LSPServerStatus.STOPPED
    started_at: Optional[float] = None
    restart_count: int = 0
    max_restarts: int = 3
    diagnostics: dict[str, list[dict]] = field(default_factory=dict)
    open_files: set[str] = field(default_factory=set)
    worker_id: Optional[str] = None


@dataclass
class LSPConfig:
    """Configuration for the LSP subsystem."""

    enabled: bool = True
    auto_install: bool = True
    auto_detect: bool = True
    max_servers_per_worktree: int = 6
    health_check_interval_s: float = 30.0
    request_timeout_s: float = 10.0
    diagnostics_debounce_ms: int = 500
    diagnostics_timeout_s: float = 5.0
    max_diagnostics_per_file: int = 100
    server_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    custom_servers: list[dict[str, Any]] = field(default_factory=list)
    disabled_servers: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, project_dir: Path) -> "LSPConfig":
        """Load config from .swarmweaver/lsp.yaml -> env vars -> defaults."""
        config = cls()

        # 1. Try loading from YAML config file
        yaml_path = project_dir / ".swarmweaver" / "lsp.yaml"
        if yaml_path.exists():
            try:
                import yaml  # optional dependency

                with open(yaml_path) as f:
                    data = yaml.safe_load(f) or {}
                for key in (
                    "enabled",
                    "auto_install",
                    "auto_detect",
                    "max_servers_per_worktree",
                    "health_check_interval_s",
                    "request_timeout_s",
                    "diagnostics_debounce_ms",
                    "diagnostics_timeout_s",
                    "max_diagnostics_per_file",
                    "server_overrides",
                    "custom_servers",
                    "disabled_servers",
                ):
                    if key in data:
                        setattr(config, key, data[key])
            except ImportError:
                logger.warning(
                    "PyYAML not installed; skipping lsp.yaml (pip install pyyaml)"
                )
            except Exception as exc:
                logger.warning("Failed to parse %s: %s", yaml_path, exc)

        # 2. Environment variable overrides (SWARMWEAVER_LSP_*)
        _env_bool(config, "enabled", "SWARMWEAVER_LSP_ENABLED")
        _env_bool(config, "auto_install", "SWARMWEAVER_LSP_AUTO_INSTALL")
        _env_bool(config, "auto_detect", "SWARMWEAVER_LSP_AUTO_DETECT")
        _env_int(config, "max_servers_per_worktree", "SWARMWEAVER_LSP_MAX_SERVERS")
        _env_float(config, "health_check_interval_s", "SWARMWEAVER_LSP_HEALTH_INTERVAL")
        _env_float(config, "request_timeout_s", "SWARMWEAVER_LSP_REQUEST_TIMEOUT")
        _env_int(config, "diagnostics_debounce_ms", "SWARMWEAVER_LSP_DIAG_DEBOUNCE")
        _env_float(config, "diagnostics_timeout_s", "SWARMWEAVER_LSP_DIAG_TIMEOUT")
        _env_int(config, "max_diagnostics_per_file", "SWARMWEAVER_LSP_MAX_DIAG")

        disabled_env = os.environ.get("SWARMWEAVER_LSP_DISABLED_SERVERS", "")
        if disabled_env:
            config.disabled_servers = [
                s.strip() for s in disabled_env.split(",") if s.strip()
            ]

        return config


# ---------------------------------------------------------------------------
# Env-var helpers
# ---------------------------------------------------------------------------


def _env_bool(cfg: LSPConfig, attr: str, key: str) -> None:
    val = os.environ.get(key)
    if val is not None:
        setattr(cfg, attr, val.lower() in ("1", "true", "yes"))


def _env_int(cfg: LSPConfig, attr: str, key: str) -> None:
    val = os.environ.get(key)
    if val is not None:
        try:
            setattr(cfg, attr, int(val))
        except ValueError:
            pass


def _env_float(cfg: LSPConfig, attr: str, key: str) -> None:
    val = os.environ.get(key)
    if val is not None:
        try:
            setattr(cfg, attr, float(val))
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Built-in server specifications (22 servers, 4 tiers)
# ---------------------------------------------------------------------------

BUILTIN_SERVER_SPECS: list[LSPServerSpec] = [
    # ── Tier 1: Core ──────────────────────────────────────────────────────
    LSPServerSpec(
        language_id="typescript",
        server_name="typescript-language-server",
        command="typescript-language-server",
        args=["--stdio"],
        install_command="npm install -g typescript-language-server typescript",
        install_check="typescript-language-server --version",
        extensions=[".ts", ".tsx", ".js", ".jsx"],
        project_markers=["tsconfig.json", "package.json"],
        init_options={"hostInfo": "swarmweaver"},
        settings={
            "typescript": {
                "inlayHints": {"parameterNames": {"enabled": "all"}},
                "suggest": {"completeFunctionCalls": True},
            }
        },
        capabilities={"textDocument": {"completion": True, "definition": True}},
        priority=1,
    ),
    LSPServerSpec(
        language_id="python",
        server_name="pyright",
        command="pyright-langserver",
        args=["--stdio"],
        install_command="npm install -g pyright",
        install_check="pyright-langserver --version",
        extensions=[".py", ".pyi"],
        project_markers=["pyproject.toml", "setup.py", "requirements.txt"],
        init_options={},
        settings={
            "python": {
                "analysis": {
                    "autoSearchPaths": True,
                    "useLibraryCodeForTypes": True,
                    "diagnosticMode": "openFilesOnly",
                    "typeCheckingMode": "basic",
                }
            }
        },
        capabilities={"textDocument": {"completion": True, "hover": True}},
        priority=1,
    ),
    LSPServerSpec(
        language_id="go",
        server_name="gopls",
        command="gopls",
        args=["serve"],
        install_command="go install golang.org/x/tools/gopls@latest",
        install_check="gopls version",
        extensions=[".go"],
        project_markers=["go.mod"],
        init_options={},
        settings={
            "gopls": {
                "staticcheck": True,
                "gofumpt": True,
                "analyses": {"unusedparams": True, "shadow": True},
            }
        },
        capabilities={"textDocument": {"completion": True, "references": True}},
        priority=1,
    ),
    LSPServerSpec(
        language_id="rust",
        server_name="rust-analyzer",
        command="rust-analyzer",
        args=[],
        install_command="rustup component add rust-analyzer",
        install_check="rust-analyzer --version",
        extensions=[".rs"],
        project_markers=["Cargo.toml"],
        init_options={},
        settings={
            "rust-analyzer": {
                "checkOnSave": {"command": "clippy"},
                "cargo": {"allFeatures": True},
                "procMacro": {"enable": True},
            }
        },
        capabilities={"textDocument": {"completion": True, "codeAction": True}},
        priority=1,
    ),
    # ── Tier 2: Secondary ────────────────────────────────────────────────
    LSPServerSpec(
        language_id="c",
        server_name="clangd",
        command="clangd",
        args=["--background-index", "--clang-tidy"],
        install_command="apt-get install -y clangd || brew install llvm",
        install_check="clangd --version",
        extensions=[".c", ".cpp", ".h", ".hpp", ".cc", ".cxx"],
        project_markers=["CMakeLists.txt", "compile_commands.json", "Makefile"],
        init_options={"clangdFileStatus": True},
        settings={},
        capabilities={"textDocument": {"completion": True, "semanticTokens": True}},
        priority=2,
    ),
    LSPServerSpec(
        language_id="java",
        server_name="jdtls",
        command="jdtls",
        args=[],
        install_command="brew install jdtls || sdkman install java",
        install_check="jdtls --version",
        extensions=[".java"],
        project_markers=["pom.xml", "build.gradle", "build.gradle.kts"],
        init_options={
            "bundles": [],
            "workspaceFolders": [],
        },
        settings={
            "java": {
                "configuration": {"updateBuildConfiguration": "automatic"},
                "import": {"gradle": {"enabled": True}, "maven": {"enabled": True}},
            }
        },
        capabilities={"textDocument": {"completion": True}},
        priority=2,
    ),
    LSPServerSpec(
        language_id="ruby",
        server_name="solargraph",
        command="solargraph",
        args=["stdio"],
        install_command="gem install solargraph",
        install_check="solargraph --version",
        extensions=[".rb", ".rake", ".gemspec"],
        project_markers=["Gemfile", ".ruby-version"],
        init_options={},
        settings={"solargraph": {"diagnostics": True, "formatting": True}},
        capabilities={"textDocument": {"completion": True, "definition": True}},
        priority=2,
    ),
    LSPServerSpec(
        language_id="php",
        server_name="intelephense",
        command="intelephense",
        args=["--stdio"],
        install_command="npm install -g intelephense",
        install_check="intelephense --version",
        extensions=[".php"],
        project_markers=["composer.json", "artisan"],
        init_options={"storagePath": "/tmp/intelephense"},
        settings={
            "intelephense": {
                "files": {"maxSize": 5000000},
                "environment": {"phpVersion": "8.2"},
            }
        },
        capabilities={"textDocument": {"completion": True}},
        priority=2,
    ),
    LSPServerSpec(
        language_id="kotlin",
        server_name="kotlin-language-server",
        command="kotlin-language-server",
        args=[],
        install_command="brew install kotlin-language-server || sdkman install kotlin",
        install_check="kotlin-language-server --version",
        extensions=[".kt", ".kts"],
        project_markers=["build.gradle.kts", "build.gradle"],
        init_options={},
        settings={},
        capabilities={"textDocument": {"completion": True}},
        priority=2,
    ),
    LSPServerSpec(
        language_id="swift",
        server_name="sourcekit-lsp",
        command="sourcekit-lsp",
        args=[],
        install_command="",  # Ships with Xcode / Swift toolchain
        install_check="sourcekit-lsp --help",
        extensions=[".swift"],
        project_markers=["Package.swift", "*.xcodeproj"],
        init_options={},
        settings={},
        capabilities={"textDocument": {"completion": True, "definition": True}},
        priority=2,
    ),
    # ── Tier 3: Specialty ────────────────────────────────────────────────
    LSPServerSpec(
        language_id="zig",
        server_name="zls",
        command="zls",
        args=[],
        install_command="",  # Usually installed alongside Zig
        install_check="zls --version",
        extensions=[".zig"],
        project_markers=["build.zig"],
        init_options={},
        settings={"zls": {"enable_snippets": True}},
        capabilities={"textDocument": {"completion": True}},
        priority=3,
    ),
    LSPServerSpec(
        language_id="lua",
        server_name="lua-language-server",
        command="lua-language-server",
        args=[],
        install_command="brew install lua-language-server",
        install_check="lua-language-server --version",
        extensions=[".lua"],
        project_markers=[".luarc.json", ".luarc.jsonc"],
        init_options={},
        settings={"Lua": {"diagnostics": {"globals": ["vim"]}}},
        capabilities={"textDocument": {"completion": True}},
        priority=3,
    ),
    LSPServerSpec(
        language_id="elixir",
        server_name="elixir-ls",
        command="elixir-ls",
        args=[],
        install_command="mix archive.install hex elixir_ls",
        install_check="elixir-ls --version",
        extensions=[".ex", ".exs"],
        project_markers=["mix.exs"],
        init_options={},
        settings={"elixirLS": {"dialyzerEnabled": False}},
        capabilities={"textDocument": {"completion": True}},
        priority=3,
    ),
    LSPServerSpec(
        language_id="gleam",
        server_name="gleam",
        command="gleam",
        args=["lsp"],
        install_command="brew install gleam || cargo install gleam",
        install_check="gleam --version",
        extensions=[".gleam"],
        project_markers=["gleam.toml"],
        init_options={},
        settings={},
        capabilities={"textDocument": {"completion": True}},
        priority=3,
    ),
    LSPServerSpec(
        language_id="typescript",
        server_name="deno",
        command="deno",
        args=["lsp"],
        install_command="curl -fsSL https://deno.land/install.sh | sh",
        install_check="deno --version",
        extensions=[".ts", ".js"],
        project_markers=["deno.json", "deno.jsonc"],
        init_options={"enable": True, "lint": True, "unstable": []},
        settings={"deno": {"enable": True, "lint": True}},
        capabilities={"textDocument": {"completion": True}},
        priority=3,
    ),
    # ── Tier 4: Config / Markup ──────────────────────────────────────────
    LSPServerSpec(
        language_id="yaml",
        server_name="yaml-language-server",
        command="yaml-language-server",
        args=["--stdio"],
        install_command="npm install -g yaml-language-server",
        install_check="yaml-language-server --version",
        extensions=[".yaml", ".yml"],
        project_markers=[],
        init_options={},
        settings={
            "yaml": {
                "validate": True,
                "hover": True,
                "completion": True,
                "schemas": {},
            }
        },
        capabilities={"textDocument": {"completion": True}},
        priority=4,
    ),
    LSPServerSpec(
        language_id="shellscript",
        server_name="bash-language-server",
        command="bash-language-server",
        args=["start"],
        install_command="npm install -g bash-language-server",
        install_check="bash-language-server --version",
        extensions=[".sh", ".bash", ".zsh"],
        project_markers=[],
        init_options={},
        settings={},
        capabilities={"textDocument": {"completion": True, "hover": True}},
        priority=4,
    ),
    LSPServerSpec(
        language_id="dockerfile",
        server_name="dockerfile-language-server",
        command="docker-langserver",
        args=["--stdio"],
        install_command="npm install -g dockerfile-language-server-nodejs",
        install_check="docker-langserver --version",
        extensions=[".dockerfile"],
        project_markers=["Dockerfile", "Dockerfile.*"],
        init_options={},
        settings={},
        capabilities={"textDocument": {"completion": True}},
        priority=4,
    ),
    LSPServerSpec(
        language_id="terraform",
        server_name="terraform-ls",
        command="terraform-ls",
        args=["serve"],
        install_command="brew install hashicorp/tap/terraform-ls",
        install_check="terraform-ls --version",
        extensions=[".tf", ".tfvars"],
        project_markers=["main.tf", "terraform.tfstate"],
        init_options={},
        settings={
            "terraform-ls": {
                "experimentalFeatures": {"validateOnSave": True},
            }
        },
        capabilities={"textDocument": {"completion": True}},
        priority=4,
    ),
    LSPServerSpec(
        language_id="css",
        server_name="vscode-css-languageserver",
        command="vscode-css-language-server",
        args=["--stdio"],
        install_command="npm install -g vscode-langservers-extracted",
        install_check="vscode-css-language-server --version",
        extensions=[".css", ".scss", ".less"],
        project_markers=[],
        init_options={},
        settings={
            "css": {"validate": True},
            "scss": {"validate": True},
            "less": {"validate": True},
        },
        capabilities={"textDocument": {"completion": True, "colorProvider": True}},
        priority=4,
    ),
    LSPServerSpec(
        language_id="html",
        server_name="vscode-html-languageserver",
        command="vscode-html-language-server",
        args=["--stdio"],
        install_command="npm install -g vscode-langservers-extracted",
        install_check="vscode-html-language-server --version",
        extensions=[".html", ".htm"],
        project_markers=[],
        init_options={
            "embeddedLanguages": {"css": True, "javascript": True},
        },
        settings={},
        capabilities={"textDocument": {"completion": True}},
        priority=4,
    ),
    LSPServerSpec(
        language_id="vue",
        server_name="vue-language-server",
        command="vue-language-server",
        args=["--stdio"],
        install_command="npm install -g @vue/language-server",
        install_check="vue-language-server --version",
        extensions=[".vue"],
        project_markers=["package.json"],  # requires vue in deps
        init_options={
            "typescript": {"tsdk": "node_modules/typescript/lib"},
        },
        settings={},
        capabilities={"textDocument": {"completion": True}},
        priority=4,
    ),
]

# ---------------------------------------------------------------------------
# Extension -> language ID mapping (120+ extensions)
# ---------------------------------------------------------------------------

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    # ── Python ─────────────────────────────────────────
    ".py": "python",
    ".pyi": "python",
    ".pyw": "python",
    ".pyx": "python",
    ".pxd": "python",
    # ── JavaScript / TypeScript ────────────────────────
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascriptreact",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "typescriptreact",
    # ── Go ─────────────────────────────────────────────
    ".go": "go",
    ".mod": "gomod",
    ".sum": "gosum",
    # ── Rust ───────────────────────────────────────────
    ".rs": "rust",
    # ── C / C++ ────────────────────────────────────────
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".hh": "cpp",
    ".inl": "cpp",
    # ── C# ─────────────────────────────────────────────
    ".cs": "csharp",
    ".csx": "csharp",
    # ── Java ───────────────────────────────────────────
    ".java": "java",
    ".jav": "java",
    # ── Kotlin ─────────────────────────────────────────
    ".kt": "kotlin",
    ".kts": "kotlin",
    # ── Scala ──────────────────────────────────────────
    ".scala": "scala",
    ".sc": "scala",
    ".sbt": "scala",
    # ── Ruby ───────────────────────────────────────────
    ".rb": "ruby",
    ".rake": "ruby",
    ".gemspec": "ruby",
    ".ru": "ruby",
    # ── PHP ────────────────────────────────────────────
    ".php": "php",
    ".phtml": "php",
    ".php3": "php",
    ".php4": "php",
    ".php5": "php",
    ".phps": "php",
    # ── Swift ──────────────────────────────────────────
    ".swift": "swift",
    # ── Objective-C ────────────────────────────────────
    ".m": "objective-c",
    ".mm": "objective-cpp",
    # ── Zig ────────────────────────────────────────────
    ".zig": "zig",
    # ── Lua ────────────────────────────────────────────
    ".lua": "lua",
    # ── Elixir ─────────────────────────────────────────
    ".ex": "elixir",
    ".exs": "elixir",
    ".heex": "elixir",
    ".leex": "elixir",
    # ── Erlang ─────────────────────────────────────────
    ".erl": "erlang",
    ".hrl": "erlang",
    # ── Gleam ──────────────────────────────────────────
    ".gleam": "gleam",
    # ── Dart ───────────────────────────────────────────
    ".dart": "dart",
    # ── Haskell ────────────────────────────────────────
    ".hs": "haskell",
    ".lhs": "haskell",
    # ── OCaml / ReasonML ───────────────────────────────
    ".ml": "ocaml",
    ".mli": "ocaml",
    ".re": "reason",
    ".rei": "reason",
    # ── F# ─────────────────────────────────────────────
    ".fs": "fsharp",
    ".fsi": "fsharp",
    ".fsx": "fsharp",
    # ── Elm ────────────────────────────────────────────
    ".elm": "elm",
    # ── Clojure ────────────────────────────────────────
    ".clj": "clojure",
    ".cljs": "clojure",
    ".cljc": "clojure",
    ".edn": "clojure",
    # ── Lisp / Scheme ──────────────────────────────────
    ".lisp": "lisp",
    ".lsp": "lisp",
    ".cl": "lisp",
    ".scm": "scheme",
    ".ss": "scheme",
    ".rkt": "racket",
    # ── R ──────────────────────────────────────────────
    ".r": "r",
    ".R": "r",
    ".Rmd": "rmarkdown",
    # ── Julia ──────────────────────────────────────────
    ".jl": "julia",
    # ── Perl ───────────────────────────────────────────
    ".pl": "perl",
    ".pm": "perl",
    ".t": "perl",
    # ── Shell ──────────────────────────────────────────
    ".sh": "shellscript",
    ".bash": "shellscript",
    ".zsh": "shellscript",
    ".fish": "shellscript",
    ".ksh": "shellscript",
    ".csh": "shellscript",
    ".tcsh": "shellscript",
    # ── PowerShell ─────────────────────────────────────
    ".ps1": "powershell",
    ".psm1": "powershell",
    ".psd1": "powershell",
    # ── Web / Markup ───────────────────────────────────
    ".html": "html",
    ".htm": "html",
    ".xhtml": "html",
    ".vue": "vue",
    ".svelte": "svelte",
    ".astro": "astro",
    # ── CSS ────────────────────────────────────────────
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".styl": "stylus",
    # ── Terraform / HCL ───────────────────────────────
    ".tf": "terraform",
    ".tfvars": "terraform",
    ".hcl": "hcl",
    # ── Docker ─────────────────────────────────────────
    ".dockerfile": "dockerfile",
    # ── Data / Config ──────────────────────────────────
    ".json": "json",
    ".jsonc": "jsonc",
    ".json5": "json5",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    ".properties": "properties",
    ".env": "dotenv",
    # ── XML ────────────────────────────────────────────
    ".xml": "xml",
    ".xsd": "xml",
    ".xsl": "xml",
    ".xslt": "xml",
    ".svg": "xml",
    ".plist": "xml",
    # ── Markdown / Text ────────────────────────────────
    ".md": "markdown",
    ".mdx": "mdx",
    ".rst": "restructuredtext",
    ".txt": "plaintext",
    ".tex": "latex",
    ".bib": "bibtex",
    # ── SQL ────────────────────────────────────────────
    ".sql": "sql",
    ".psql": "sql",
    ".mysql": "sql",
    # ── GraphQL / Protobuf ─────────────────────────────
    ".graphql": "graphql",
    ".gql": "graphql",
    ".proto": "protobuf",
    # ── Nix ────────────────────────────────────────────
    ".nix": "nix",
    # ── Nim ────────────────────────────────────────────
    ".nim": "nim",
    ".nims": "nim",
    # ── V ──────────────────────────────────────────────
    ".v": "v",
    # ── Crystal ────────────────────────────────────────
    ".cr": "crystal",
    # ── D ──────────────────────────────────────────────
    ".d": "d",
    # ── Ada ────────────────────────────────────────────
    ".adb": "ada",
    ".ads": "ada",
    # ── Fortran ────────────────────────────────────────
    ".f90": "fortran",
    ".f95": "fortran",
    ".f03": "fortran",
    ".f08": "fortran",
    # ── WASM ───────────────────────────────────────────
    ".wat": "wat",
    ".wast": "wat",
    # ── Solidity ───────────────────────────────────────
    ".sol": "solidity",
    # ── Makefile-like ──────────────────────────────────
    ".mk": "makefile",
    # ── CUDA ───────────────────────────────────────────
    ".cu": "cuda-cpp",
    ".cuh": "cuda-cpp",
    # ── Visual Basic ───────────────────────────────────
    ".vb": "vb",
    ".vbs": "vbscript",
    # ── Batch ──────────────────────────────────────────
    ".bat": "bat",
    ".cmd": "bat",
    # ── Puppet / Ansible ───────────────────────────────
    ".pp": "puppet",
    # ── COBOL ──────────────────────────────────────────
    ".cob": "cobol",
    ".cbl": "cobol",
}


# ---------------------------------------------------------------------------
# LSPManager
# ---------------------------------------------------------------------------


class LSPManager:
    """Manages language server lifecycles for one or more worktrees.

    Usage::

        manager = LSPManager(project_dir)
        instance = await manager.ensure_server("python", root_path)
        diagnostics = manager.get_diagnostics("/path/to/file.py")
        await manager.stop_all()
    """

    def __init__(
        self,
        project_dir: str | Path,
        config: Optional[LSPConfig] = None,
        on_event: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.config = config or LSPConfig.load(self.project_dir)
        self.on_event = on_event

        # Key: (language_id, root_path_str, worker_id)
        self._instances: dict[tuple[str, str, Optional[str]], LSPServerInstance] = {}
        self._spec_index: dict[str, list[LSPServerSpec]] = {}
        self._health_task: Optional[asyncio.Task] = None

        # Diagnostic history: records when diagnostics appear and get resolved
        self._diagnostic_history: list[dict[str, Any]] = []
        self._previous_diags: dict[str, set[str]] = {}  # uri → set of diag keys
        self._stats = {
            "total_found": 0,
            "total_resolved": 0,
            "by_worker": {},   # worker_id → {found, resolved}
            "by_severity": {1: {"found": 0, "resolved": 0}, 2: {"found": 0, "resolved": 0}},
        }

        self._build_spec_index()

    # ── Spec index ────────────────────────────────────────────────────────

    def _build_spec_index(self) -> None:
        """Build a language_id -> [spec] lookup from built-in + custom servers."""
        self._spec_index.clear()
        all_specs = list(BUILTIN_SERVER_SPECS)

        # Append custom servers from config
        for custom in self.config.custom_servers:
            try:
                spec = LSPServerSpec(**custom)
                all_specs.append(spec)
            except TypeError as exc:
                logger.warning("Invalid custom server spec: %s", exc)

        # Apply overrides
        for spec in all_specs:
            overrides = self.config.server_overrides.get(spec.server_name, {})
            for key, val in overrides.items():
                if hasattr(spec, key):
                    setattr(spec, key, val)

        # Group by language_id, sorted by priority (lower = higher priority).
        # Also index by extension-derived languages so e.g. "javascript" and
        # "javascriptreact" find the typescript-language-server.
        for spec in sorted(all_specs, key=lambda s: s.priority):
            if spec.server_name not in self.config.disabled_servers:
                self._spec_index.setdefault(spec.language_id, []).append(spec)
                # Cross-index by extension languages
                for ext in spec.extensions:
                    ext_lang = EXTENSION_TO_LANGUAGE.get(ext)
                    if ext_lang and ext_lang != spec.language_id:
                        self._spec_index.setdefault(ext_lang, []).append(spec)

    def _resolve_spec(
        self, language_id: str, root_path: Path
    ) -> Optional[LSPServerSpec]:
        """Pick the best spec for a language at a given root, respecting markers."""
        candidates = self._spec_index.get(language_id, [])
        if not candidates:
            return None

        # Prefer spec whose project_markers exist in root_path
        for spec in candidates:
            if spec.project_markers:
                for marker in spec.project_markers:
                    if (root_path / marker).exists() or list(
                        root_path.glob(marker)
                    ):
                        return spec

        # Fallback to highest-priority (first in sorted list)
        return candidates[0]

    # ── Server lifecycle ──────────────────────────────────────────────────

    async def ensure_server(
        self,
        language_id: str,
        root_path: str | Path,
        worker_id: Optional[str] = None,
    ) -> Optional[LSPServerInstance]:
        """Start a server if not already running. Returns the instance or None."""
        root_path = Path(root_path)
        key = (language_id, str(root_path), worker_id)

        # Already running?
        existing = self._instances.get(key)
        if existing and existing.status in (
            LSPServerStatus.READY,
            LSPServerStatus.STARTING,
        ):
            return existing

        # Check server cap
        active_count = sum(
            1
            for inst in self._instances.values()
            if inst.status == LSPServerStatus.READY
            and str(root_path) in inst.root_uri
        )
        if active_count >= self.config.max_servers_per_worktree:
            logger.warning(
                "Max servers (%d) reached for worktree %s; skipping %s",
                self.config.max_servers_per_worktree,
                root_path,
                language_id,
            )
            return None

        spec = self._resolve_spec(language_id, root_path)
        if spec is None:
            logger.debug("No server spec for language '%s'", language_id)
            return None

        # Dedup: if this server_name is already running for the same
        # root+worker (under a different language_id key), reuse it.
        # E.g., "javascriptreact" and "javascript" both resolve to
        # typescript-language-server — avoid spawning two processes.
        for (lid, rstr, wid), inst in self._instances.items():
            if (
                inst.spec.server_name == spec.server_name
                and rstr == str(root_path)
                and wid == worker_id
                and inst.status in (LSPServerStatus.READY, LSPServerStatus.STARTING)
            ):
                # Also register under this language_id key for future lookups
                self._instances[key] = inst
                return inst

        # Check if binary is available
        binary = shutil.which(spec.command)
        if binary is None:
            if self.config.auto_install and spec.install_command:
                print(f"[LSP] {spec.server_name} not found, auto-installing...", flush=True)
                installed = await self.auto_install(spec)
                if not installed:
                    print(f"[LSP] Failed to install {spec.server_name}", flush=True)
                    logger.error(
                        "Failed to install %s; cannot start server", spec.server_name
                    )
                    return None
                print(f"[LSP] Installed {spec.server_name} successfully", flush=True)
            else:
                print(f"[LSP] {spec.server_name} not found (auto_install disabled)", flush=True)
                logger.info(
                    "%s not found and auto_install disabled", spec.server_name
                )
                return None

        instance = LSPServerInstance(
            spec=spec,
            root_uri=root_path.as_uri(),
            worker_id=worker_id,
        )
        self._instances[key] = instance

        try:
            await self._start_server(instance)
        except Exception as exc:
            logger.error("Failed to start %s: %s", spec.server_name, exc)
            instance.status = LSPServerStatus.CRASHED
            self._emit_event("lsp_server_error", {
                "server": spec.server_name,
                "language": language_id,
                "error": str(exc),
            })
            return None

        return instance

    async def _start_server(self, instance: LSPServerInstance) -> None:
        """Spawn the server process and perform LSP initialize handshake."""
        spec = instance.spec
        instance.status = LSPServerStatus.STARTING

        cmd = [spec.command] + spec.args
        logger.info("Starting LSP server: %s", " ".join(cmd))

        # Use asyncio subprocess so LSPClient gets async stdin/stdout streams.
        # The command is from BUILTIN_SERVER_SPECS (trusted, no user input).
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        instance.process = process
        instance.pid = process.pid
        instance.started_at = time.time()

        # Diagnostic callback: store diagnostics + track history
        async def _on_diag(report) -> None:
            diag_dicts = []
            for d in report.diagnostics:
                diag_dicts.append({
                    "uri": d.uri,
                    "message": d.message,
                    "severity": d.severity,
                    "start_line": d.start_line,
                    "start_character": d.start_character,
                    "end_line": d.end_line,
                    "end_character": d.end_character,
                    "source": d.source,
                    "code": d.code,
                })

            # Track diagnostic history (found/resolved)
            self._track_diagnostic_changes(
                report.uri, diag_dicts, instance.worker_id
            )

            instance.diagnostics[report.uri] = diag_dicts
            self._emit_event("lsp_diagnostics", {
                "uri": report.uri,
                "count": len(diag_dicts),
                "server": spec.server_name,
            })

        client = LSPClient(
            process=process,
            root_uri=instance.root_uri,
            timeout_s=self.config.request_timeout_s,
            on_diagnostics=_on_diag,
        )
        instance.client = client

        # LSP initialize (client.initialize() sends both initialize and initialized)
        init_result = await client.initialize()
        if init_result is None:
            raise RuntimeError(f"LSP initialize returned None for {spec.server_name}")

        instance.status = LSPServerStatus.READY
        print(
            f"[LSP] Server ready: {spec.server_name} (PID {process.pid}, "
            f"root={instance.root_uri})",
            flush=True,
        )
        logger.info(
            "LSP server ready: %s (PID %d)", spec.server_name, process.pid
        )
        self._emit_event("lsp_server_ready", {
            "server": spec.server_name,
            "language": spec.language_id,
            "pid": process.pid,
        })

    async def stop_server(
        self,
        language_id: str,
        root_path: str | Path,
        worker_id: Optional[str] = None,
    ) -> None:
        """Gracefully shut down a single server instance."""
        key = (language_id, str(root_path), worker_id)
        instance = self._instances.get(key)
        if instance is None:
            return

        await self._shutdown_instance(instance)
        del self._instances[key]

    async def stop_all(self) -> None:
        """Shut down every managed server instance."""
        keys = list(self._instances.keys())
        for key in keys:
            instance = self._instances.get(key)
            if instance:
                await self._shutdown_instance(instance)
        self._instances.clear()

        if self._health_task and not self._health_task.done():
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None

        logger.info("All LSP servers stopped")

    async def restart_server(
        self,
        language_id: str,
        root_path: str | Path,
        worker_id: Optional[str] = None,
    ) -> Optional[LSPServerInstance]:
        """Stop and restart a server. Returns the new instance or None."""
        key = (language_id, str(root_path), worker_id)
        instance = self._instances.get(key)
        restart_count = instance.restart_count if instance else 0

        await self.stop_server(language_id, root_path, worker_id)

        new_instance = await self.ensure_server(language_id, root_path, worker_id)
        if new_instance:
            new_instance.restart_count = restart_count + 1
        return new_instance

    async def _shutdown_instance(self, instance: LSPServerInstance) -> None:
        """Send LSP shutdown/exit and terminate the process."""
        spec = instance.spec
        try:
            if instance.client and instance.status == LSPServerStatus.READY:
                await instance.client.shutdown()
        except Exception as exc:
            logger.debug("LSP shutdown error for %s: %s", spec.server_name, exc)

        if instance.process:
            try:
                instance.process.terminate()
                try:
                    await asyncio.wait_for(instance.process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    instance.process.kill()
                    await asyncio.wait_for(instance.process.wait(), timeout=2)
            except Exception:
                pass

        instance.status = LSPServerStatus.STOPPED
        self._emit_event("lsp_server_stopped", {
            "server": spec.server_name,
            "language": spec.language_id,
            "pid": instance.pid,
        })

    # ── Auto-detection ────────────────────────────────────────────────────

    def detect_languages(self, root_path: str | Path) -> list[str]:
        """Detect which languages are present in a project directory.

        Strategy:
            1. Scan for project_markers (high confidence — tsconfig.json, go.mod, etc.)
            2. Fallback: sample file extensions in the tree (up to 2000 files)
        """
        root = Path(root_path)
        detected: set[str] = set()

        # Phase 1: marker files
        for spec in BUILTIN_SERVER_SPECS:
            if spec.server_name in self.config.disabled_servers:
                continue
            for marker in spec.project_markers:
                if (root / marker).exists() or list(root.glob(marker)):
                    detected.add(spec.language_id)
                    break

        # Phase 2: extension sampling (skip hidden dirs, node_modules, etc.)
        skip_dirs = {
            ".git", ".svn", ".hg", "node_modules", "__pycache__",
            ".swarmweaver", ".venv", "venv", "target", "build", "dist",
            ".next", ".nuxt",
        }
        sampled = 0
        max_sample = 2000
        for item in root.rglob("*"):
            if sampled >= max_sample:
                break
            # Skip hidden/ignored directories
            if any(part in skip_dirs for part in item.parts):
                continue
            if item.is_file():
                sampled += 1
                lang = EXTENSION_TO_LANGUAGE.get(item.suffix.lower())
                if lang:
                    detected.add(lang)

        return sorted(detected)

    # ── Auto-install ──────────────────────────────────────────────────────

    async def auto_install(self, spec: LSPServerSpec) -> bool:
        """Attempt to install a language server binary.

        Returns True if the install succeeded (or binary already exists).
        """
        if not spec.install_command:
            logger.info("No install command for %s", spec.server_name)
            return False

        # Check if already installed
        if spec.install_check:
            try:
                result = subprocess.run(
                    spec.install_check,
                    shell=True,
                    capture_output=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    logger.info("%s already installed", spec.server_name)
                    return True
            except (subprocess.TimeoutExpired, OSError):
                pass

        logger.info("Installing %s: %s", spec.server_name, spec.install_command)
        self._emit_event("lsp_installing", {
            "server": spec.server_name,
            "command": spec.install_command,
        })

        try:
            proc = await asyncio.create_subprocess_shell(
                spec.install_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0:
                logger.info("Successfully installed %s", spec.server_name)
                self._emit_event("lsp_installed", {"server": spec.server_name})
                return True
            else:
                logger.error(
                    "Install failed for %s (exit %d): %s",
                    spec.server_name,
                    proc.returncode,
                    stderr.decode(errors="replace")[:500],
                )
                return False
        except asyncio.TimeoutError:
            logger.error("Install timed out for %s", spec.server_name)
            return False
        except Exception as exc:
            logger.error("Install error for %s: %s", spec.server_name, exc)
            return False

    # ── Health monitoring ─────────────────────────────────────────────────

    def health_check(self, instance: LSPServerInstance) -> LSPServerStatus:
        """Check if a server process is still alive and responsive."""
        if instance.process is None:
            instance.status = LSPServerStatus.STOPPED
            return instance.status

        poll = instance.process.returncode
        if poll is not None:
            logger.warning(
                "LSP server %s (PID %s) exited with code %s",
                instance.spec.server_name,
                instance.pid,
                poll,
            )
            instance.status = LSPServerStatus.CRASHED
            return instance.status

        # Process is alive
        if instance.status == LSPServerStatus.CRASHED:
            # Shouldn't happen, but correct it
            instance.status = LSPServerStatus.DEGRADED
        return instance.status

    async def run_health_loop(
        self, interval_s: Optional[float] = None
    ) -> None:
        """Periodically check servers and restart crashed ones.

        Runs until cancelled. Typically launched as an asyncio task.
        """
        interval = interval_s or self.config.health_check_interval_s
        logger.info("LSP health loop started (interval=%.1fs)", interval)

        while True:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

            for key, instance in list(self._instances.items()):
                status = self.health_check(instance)
                if status == LSPServerStatus.CRASHED:
                    if instance.restart_count < instance.max_restarts:
                        language_id, root_path, worker_id = key
                        logger.info(
                            "Restarting crashed %s (attempt %d/%d)",
                            instance.spec.server_name,
                            instance.restart_count + 1,
                            instance.max_restarts,
                        )
                        await self.restart_server(language_id, root_path, worker_id)
                    else:
                        logger.error(
                            "Server %s exceeded max restarts (%d); giving up",
                            instance.spec.server_name,
                            instance.max_restarts,
                        )
                        self._emit_event("lsp_server_abandoned", {
                            "server": instance.spec.server_name,
                            "restart_count": instance.restart_count,
                        })

    def start_health_loop(self) -> asyncio.Task:
        """Start the health check loop as a background asyncio task."""
        if self._health_task and not self._health_task.done():
            return self._health_task
        self._health_task = asyncio.create_task(self.run_health_loop())
        return self._health_task

    # ── File synchronization ──────────────────────────────────────────────

    async def notify_file_changed(
        self,
        file_path: str | Path,
        content: str,
        worker_id: Optional[str] = None,
        root_path: Optional[str | Path] = None,
    ) -> list[dict]:
        """Notify the appropriate server that a file has changed.

        Returns cached diagnostics for the file after a brief wait for the
        server to publish updated diagnostics.

        If no server is running for this file type and ``root_path`` is
        provided, a server is lazily spawned (handles greenfield projects
        where no files exist at worker-spawn time).
        """
        instance = self.get_instance_for_file(file_path, worker_id)

        # Lazy spawn: if no server exists yet for this file type, start one
        if instance is None and root_path is not None:
            lang_id = EXTENSION_TO_LANGUAGE.get(Path(file_path).suffix.lower())
            if lang_id:
                try:
                    instance = await self.ensure_server(
                        lang_id, root_path, worker_id=worker_id
                    )
                    if instance:
                        print(
                            f"[LSP] Lazy-spawned {instance.spec.server_name} for "
                            f"{lang_id} (worker={worker_id})",
                            flush=True,
                        )
                        logger.info(
                            "Lazy-spawned LSP server %s for %s",
                            instance.spec.server_name,
                            lang_id,
                        )
                except Exception as exc:
                    logger.debug("Lazy LSP spawn failed for %s: %s", lang_id, exc)

        if instance is None or instance.client is None:
            return []

        uri = Path(file_path).as_uri()
        if uri in instance.open_files:
            version = int(time.time() * 1000) % (2**31)
            await instance.client.did_change(uri, version, content)
        else:
            await self.notify_file_opened(file_path, content, worker_id=worker_id)

        # Give the server a moment to publish diagnostics
        diag_timeout = min(self.config.diagnostics_timeout_s, 2.0)
        deadline = time.monotonic() + diag_timeout
        while time.monotonic() < deadline:
            diags = instance.diagnostics.get(uri, [])
            if diags:
                return diags
            await asyncio.sleep(0.15)

        return instance.diagnostics.get(uri, [])

    async def notify_file_opened(
        self,
        file_path: str | Path,
        content: str,
        lang_id: Optional[str] = None,
        worker_id: Optional[str] = None,
    ) -> None:
        """Notify server that a file was opened."""
        file_path = Path(file_path)
        if lang_id is None:
            lang_id = EXTENSION_TO_LANGUAGE.get(file_path.suffix.lower())
        if lang_id is None:
            return

        instance = self.get_instance_for_file(file_path, worker_id)
        if instance is None or instance.client is None:
            return

        uri = file_path.as_uri()
        if uri not in instance.open_files:
            version = int(time.time() * 1000) % (2**31)
            await instance.client.did_open(uri, lang_id, version, content)
            instance.open_files.add(uri)

    async def notify_file_closed(
        self,
        file_path: str | Path,
        worker_id: Optional[str] = None,
    ) -> None:
        """Notify server that a file was closed."""
        instance = self.get_instance_for_file(file_path, worker_id)
        if instance is None or instance.client is None:
            return

        uri = Path(file_path).as_uri()
        if uri in instance.open_files:
            await instance.client.did_close(uri)
            instance.open_files.discard(uri)

    # ── Queries ───────────────────────────────────────────────────────────

    def get_instance_for_file(
        self,
        file_path: str | Path,
        worker_id: Optional[str] = None,
    ) -> Optional[LSPServerInstance]:
        """Find the running server instance that handles a given file."""
        file_path = Path(file_path)
        lang_id = EXTENSION_TO_LANGUAGE.get(file_path.suffix.lower())
        if lang_id is None:
            return None

        # Try exact key match first
        for (lid, root_str, wid), inst in self._instances.items():
            if lid == lang_id and wid == worker_id and inst.status == LSPServerStatus.READY:
                root = Path(root_str)
                try:
                    file_path.relative_to(root)
                    return inst
                except ValueError:
                    continue

        # Also check specs that cover this language via extension overlap
        # (e.g., .ts files may be handled by typescript-language-server or deno)
        for (lid, root_str, wid), inst in self._instances.items():
            if wid == worker_id and inst.status == LSPServerStatus.READY:
                if file_path.suffix in [
                    ext for ext in inst.spec.extensions
                ]:
                    root = Path(root_str)
                    try:
                        file_path.relative_to(root)
                        return inst
                    except ValueError:
                        continue

        return None

    def get_all_instances(self) -> list[LSPServerInstance]:
        """Return all managed server instances."""
        return list(self._instances.values())

    def get_diagnostics(
        self,
        file_path: str | Path | None = None,
        severity: Optional[int] = None,
        worker_id: Optional[str] = None,
    ) -> list[dict]:
        """Retrieve cached diagnostics.

        Args:
            file_path: Absolute path to a file, or None for all diagnostics.
            severity: Optional LSP DiagnosticSeverity filter (1=Error, 2=Warning, etc.)
            worker_id: Optional worker scope.

        Returns:
            List of diagnostic dicts (message, range, severity, source, code).
        """
        if file_path is None:
            return self.get_all_diagnostics(severity=severity, worker_id=worker_id)

        instance = self.get_instance_for_file(file_path, worker_id)
        if instance is None:
            return []

        uri = Path(file_path).as_uri()
        diags = instance.diagnostics.get(uri, [])

        if severity is not None:
            diags = [d for d in diags if d.get("severity") == severity]

        max_diag = self.config.max_diagnostics_per_file
        return diags[:max_diag]

    def get_all_diagnostics(
        self,
        severity: Optional[int] = None,
        worker_id: Optional[str] = None,
    ) -> list[dict]:
        """Retrieve all cached diagnostics across all server instances.

        Args:
            severity: Optional LSP DiagnosticSeverity filter (1=Error, 2=Warning, etc.)
            worker_id: Optional worker scope filter.

        Returns:
            List of diagnostic dicts with 'uri' key included.
        """
        all_diags: list[dict] = []
        for instance in self._instances.values():
            if worker_id is not None and instance.worker_id != worker_id:
                continue
            for uri, diags in instance.diagnostics.items():
                for d in diags:
                    diag = dict(d)
                    if "uri" not in diag:
                        diag["uri"] = uri
                    if severity is not None and diag.get("severity") != severity:
                        continue
                    all_diags.append(diag)
        return all_diags

    def update_diagnostics(
        self, uri: str, diagnostics: list[dict], instance: LSPServerInstance
    ) -> None:
        """Store diagnostics published by the server."""
        max_diag = self.config.max_diagnostics_per_file
        instance.diagnostics[uri] = diagnostics[:max_diag]
        self._emit_event("lsp_diagnostics", {
            "uri": uri,
            "count": len(diagnostics),
            "server": instance.spec.server_name,
        })

    # ── Config loader (static convenience) ────────────────────────────────

    @staticmethod
    def load_config(project_dir: str | Path) -> LSPConfig:
        """Load LSP configuration for a project directory."""
        return LSPConfig.load(Path(project_dir))

    # ── Internal helpers ──────────────────────────────────────────────────

    def _emit_event(self, event_type: str, data: dict) -> None:
        """Fire an event callback if one was provided."""
        if self.on_event:
            try:
                self.on_event(event_type, data)
            except Exception as exc:
                logger.debug("on_event callback error: %s", exc)

    # ── Diagnostic history tracking ──────────────────────────────

    def _diag_key(self, d: dict) -> str:
        """Stable key for a diagnostic (file + line + message)."""
        return f"{d.get('uri', '')}:{d.get('start_line', 0)}:{d.get('message', '')}"

    def _track_diagnostic_changes(
        self,
        uri: str,
        new_diags: list[dict],
        worker_id: Optional[str],
    ) -> None:
        """Compare new diagnostics against previous state to find new/resolved."""
        now = time.time()
        new_keys = {self._diag_key(d) for d in new_diags if d.get("severity") in (1, 2)}
        old_keys = self._previous_diags.get(uri, set())

        wid = worker_id or "main"
        if wid not in self._stats["by_worker"]:
            self._stats["by_worker"][wid] = {"found": 0, "resolved": 0}

        # New diagnostics (appeared)
        appeared = new_keys - old_keys
        for key in appeared:
            sev = 1  # default
            msg = ""
            for d in new_diags:
                if self._diag_key(d) == key:
                    sev = d.get("severity", 1)
                    msg = d.get("message", "")
                    break
            self._diagnostic_history.append({
                "event": "found",
                "uri": uri,
                "key": key,
                "severity": sev,
                "message": msg,
                "worker_id": wid,
                "timestamp": now,
            })
            self._stats["total_found"] += 1
            self._stats["by_worker"][wid]["found"] += 1
            if sev in self._stats["by_severity"]:
                self._stats["by_severity"][sev]["found"] += 1

        # Resolved diagnostics (disappeared)
        resolved = old_keys - new_keys
        for key in resolved:
            self._diagnostic_history.append({
                "event": "resolved",
                "uri": uri,
                "key": key,
                "worker_id": wid,
                "timestamp": now,
            })
            self._stats["total_resolved"] += 1
            self._stats["by_worker"][wid]["resolved"] += 1
            # Try to find severity from history
            for h in reversed(self._diagnostic_history):
                if h.get("key") == key and h.get("event") == "found":
                    sev = h.get("severity", 1)
                    if sev in self._stats["by_severity"]:
                        self._stats["by_severity"][sev]["resolved"] += 1
                    break

        self._previous_diags[uri] = new_keys

        # Cap history length to avoid unbounded growth
        if len(self._diagnostic_history) > 5000:
            self._diagnostic_history = self._diagnostic_history[-3000:]

    def get_stats(self) -> dict[str, Any]:
        """Return diagnostic statistics for the frontend."""
        active = sum(
            len(diags)
            for inst in self._instances.values()
            for diags in inst.diagnostics.values()
        )
        active_errors = sum(
            1
            for inst in self._instances.values()
            for diags in inst.diagnostics.values()
            for d in diags
            if d.get("severity") == 1
        )
        active_warnings = sum(
            1
            for inst in self._instances.values()
            for diags in inst.diagnostics.values()
            for d in diags
            if d.get("severity") == 2
        )

        return {
            "total_found": self._stats["total_found"],
            "total_resolved": self._stats["total_resolved"],
            "active_count": active,
            "active_errors": active_errors,
            "active_warnings": active_warnings,
            "by_worker": self._stats["by_worker"],
            "by_severity": self._stats["by_severity"],
            "recent_events": self._diagnostic_history[-50:],
        }
