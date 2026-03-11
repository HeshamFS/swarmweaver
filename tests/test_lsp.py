"""
Tests for LSP Integration
===========================

Comprehensive tests for the Language Server Protocol integration:
  - services/lsp_client.py   (LSPClient, dataclasses)
  - services/lsp_manager.py  (LSPManager, LSPConfig, detect_languages)
  - hooks/lsp_hooks.py       (post-edit injection, watchdog, cross-worker routing)
  - services/lsp_tools.py    (MCP tool scope enforcement, diagnostics summary)
  - services/lsp_intelligence.py (impact analysis, unused code, dependency graph, health)
  - api/routers/lsp.py       (REST endpoints)

Run with:
    python -m pytest tests/test_lsp.py -v
    python -m unittest tests.test_lsp -v
"""

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from dataclasses import dataclass

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.lsp_client import (
    CallHierarchyItem,
    Diagnostic,
    DiagnosticReport,
    DocumentSymbol,
    HoverResult,
    Location,
    LSPClient,
    _encode_message,
    _text_document_identifier,
    _text_document_position,
)
from services.lsp_manager import (
    BUILTIN_SERVER_SPECS,
    EXTENSION_TO_LANGUAGE,
    LSPConfig,
    LSPManager,
    LSPServerInstance,
    LSPServerSpec,
    LSPServerStatus,
)
from hooks.lsp_hooks import (
    DEBOUNCE_MS,
    WATCHDOG_EVERY_N,
    lsp_post_edit_hook,
    lsp_diagnostic_watchdog_signal,
    set_lsp_context,
    _route_cross_worker_diagnostics,
)
from services.lsp_tools import (
    _is_in_scope,
    _make_error,
    _make_result,
    _OPERATIONS,
    LSP_TOOL_NAMES,
)
from services.lsp_intelligence import CodeIntelligence


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_mock_process():
    """Create a mock asyncio.subprocess.Process with stdin/stdout."""
    proc = MagicMock()
    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdout = MagicMock()
    proc.stdout.readline = AsyncMock(return_value=b"")
    proc.returncode = None
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    return proc


def _make_lsp_location_raw(uri="file:///test.py", line=10, char=5):
    """Build a raw LSP Location dict."""
    return {
        "uri": uri,
        "range": {
            "start": {"line": line, "character": char},
            "end": {"line": line, "character": char + 5},
        },
    }


def _make_lsp_diagnostic_raw(
    message="unused import", severity=2, line=3, source="pyright"
):
    """Build a raw LSP Diagnostic dict."""
    return {
        "range": {
            "start": {"line": line, "character": 0},
            "end": {"line": line, "character": 10},
        },
        "message": message,
        "severity": severity,
        "source": source,
        "code": "W001",
    }


# ═══════════════════════════════════════════════════════════════════════════
# TestLSPClient
# ═══════════════════════════════════════════════════════════════════════════


class TestLSPClient(unittest.IsolatedAsyncioTestCase):
    """Tests for services/lsp_client.py"""

    def setUp(self):
        self.proc = _make_mock_process()
        self.client = LSPClient(
            process=self.proc,
            root_uri="file:///project",
            timeout_s=2.0,
        )

    async def test_initialize_handshake(self):
        """LSPClient.initialize() sends initialize request with capabilities."""
        # Simulate server response
        caps = {"capabilities": {"textDocumentSync": 1}}
        response_body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "result": caps}
        ).encode("utf-8")
        header = f"Content-Length: {len(response_body)}\r\n\r\n".encode("ascii")

        read_data = header + response_body
        read_pos = 0

        async def mock_readline():
            nonlocal read_pos
            lines = read_data.split(b"\n")
            # Return header lines then empty
            if read_pos == 0:
                read_pos = 1
                return f"Content-Length: {len(response_body)}\r\n".encode("ascii")
            elif read_pos == 1:
                read_pos = 2
                return b"\r\n"
            return b""

        async def mock_readexactly(n):
            return response_body[:n]

        self.proc.stdout.readline = mock_readline
        self.proc.stdout.readexactly = mock_readexactly

        result = await self.client.initialize()

        # Verify initialize was called
        self.assertIn("capabilities", result)
        self.assertEqual(result["capabilities"]["textDocumentSync"], 1)
        # stdin.write should have been called (initialize request)
        self.assertTrue(self.proc.stdin.write.called)

    async def test_shutdown_sequence(self):
        """shutdown() sends shutdown request then exit notification."""
        # Patch _send_request and _send_notification
        self.client._send_request = AsyncMock(return_value=None)
        self.client._send_notification = AsyncMock()
        self.client._reader_task = None

        await self.client.shutdown()

        self.client._send_request.assert_awaited_once_with("shutdown", None)
        self.client._send_notification.assert_awaited_once_with("exit", None)

    async def test_did_open(self):
        """did_open() sends textDocument/didOpen notification."""
        self.client._send_notification = AsyncMock()

        await self.client.did_open(
            "file:///test.py", "python", 1, "print('hello')"
        )

        self.client._send_notification.assert_awaited_once()
        call_args = self.client._send_notification.call_args
        self.assertEqual(call_args[0][0], "textDocument/didOpen")
        params = call_args[0][1]
        self.assertEqual(params["textDocument"]["uri"], "file:///test.py")
        self.assertEqual(params["textDocument"]["languageId"], "python")
        self.assertEqual(params["textDocument"]["text"], "print('hello')")

    async def test_did_change(self):
        """did_change() sends textDocument/didChange notification."""
        self.client._send_notification = AsyncMock()

        await self.client.did_change("file:///test.py", 2, "updated content")

        self.client._send_notification.assert_awaited_once()
        call_args = self.client._send_notification.call_args
        self.assertEqual(call_args[0][0], "textDocument/didChange")
        params = call_args[0][1]
        self.assertEqual(params["textDocument"]["version"], 2)
        self.assertEqual(params["contentChanges"][0]["text"], "updated content")

    async def test_diagnostics_received(self):
        """Reader loop processes publishDiagnostics and calls on_diagnostics callback."""
        callback = AsyncMock()
        self.client._on_diagnostics = callback

        diag_raw = _make_lsp_diagnostic_raw("type error", 1, 5)
        params = {
            "uri": "file:///test.py",
            "diagnostics": [diag_raw],
        }

        await self.client._handle_diagnostics(params)

        # Verify diagnostics are stored
        report = self.client.get_diagnostics("file:///test.py")
        self.assertEqual(len(report.diagnostics), 1)
        self.assertEqual(report.diagnostics[0].message, "type error")
        self.assertEqual(report.diagnostics[0].severity, 1)

        # Verify callback was called
        callback.assert_awaited_once()
        call_report = callback.call_args[0][0]
        self.assertIsInstance(call_report, DiagnosticReport)

    async def test_hover(self):
        """hover() returns HoverResult with markdown contents."""
        self.client._send_request = AsyncMock(
            return_value={
                "contents": {"kind": "markdown", "value": "def foo(x: int) -> str"},
                "range": {
                    "start": {"line": 1, "character": 0},
                    "end": {"line": 1, "character": 3},
                },
            }
        )

        result = await self.client.hover("file:///test.py", 1, 0)

        self.assertIsNotNone(result)
        self.assertIsInstance(result, HoverResult)
        self.assertEqual(result.contents, "def foo(x: int) -> str")
        self.assertEqual(result.start_line, 1)

    async def test_goto_definition(self):
        """go_to_definition() returns list of Location objects."""
        loc_raw = _make_lsp_location_raw("file:///other.py", 20, 4)
        self.client._send_request = AsyncMock(return_value=[loc_raw])

        result = await self.client.go_to_definition("file:///test.py", 5, 10)

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], Location)
        self.assertEqual(result[0].uri, "file:///other.py")
        self.assertEqual(result[0].start_line, 20)

    async def test_find_references(self):
        """find_references() returns references across files."""
        locs = [
            _make_lsp_location_raw("file:///a.py", 10, 0),
            _make_lsp_location_raw("file:///b.py", 20, 5),
            _make_lsp_location_raw("file:///a.py", 30, 2),
        ]
        self.client._send_request = AsyncMock(return_value=locs)

        result = await self.client.find_references("file:///a.py", 10, 0)

        self.assertEqual(len(result), 3)
        uris = {loc.uri for loc in result}
        self.assertIn("file:///a.py", uris)
        self.assertIn("file:///b.py", uris)

    async def test_document_symbols(self):
        """document_symbols() returns DocumentSymbol tree."""
        raw_symbols = [
            {
                "name": "MyClass",
                "kind": 5,
                "range": {
                    "start": {"line": 0, "character": 0},
                    "end": {"line": 20, "character": 0},
                },
                "children": [
                    {
                        "name": "method_a",
                        "kind": 6,
                        "range": {
                            "start": {"line": 2, "character": 4},
                            "end": {"line": 10, "character": 0},
                        },
                        "children": [],
                    }
                ],
            }
        ]
        self.client._send_request = AsyncMock(return_value=raw_symbols)

        result = await self.client.document_symbols("file:///test.py")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "MyClass")
        self.assertEqual(result[0].kind, 5)
        self.assertEqual(len(result[0].children), 1)
        self.assertEqual(result[0].children[0].name, "method_a")

    async def test_workspace_symbols(self):
        """workspace_symbols() returns flat symbol list."""
        raw = [
            {
                "name": "global_func",
                "kind": 12,
                "location": {
                    "uri": "file:///lib.py",
                    "range": {
                        "start": {"line": 5, "character": 0},
                        "end": {"line": 15, "character": 0},
                    },
                },
            }
        ]
        self.client._send_request = AsyncMock(return_value=raw)

        result = await self.client.workspace_symbols("global")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "global_func")
        self.assertEqual(result[0].uri, "file:///lib.py")

    async def test_completion(self):
        """completion() returns completion items."""
        self.client._send_request = AsyncMock(
            return_value={
                "isIncomplete": False,
                "items": [
                    {"label": "append", "kind": 2},
                    {"label": "extend", "kind": 2},
                ],
            }
        )

        result = await self.client.completion("file:///test.py", 3, 5)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["label"], "append")

    async def test_call_hierarchy(self):
        """prepare_call_hierarchy + incoming_calls works."""
        prepare_result = [
            {
                "name": "process_data",
                "kind": 12,
                "uri": "file:///core.py",
                "range": {
                    "start": {"line": 10, "character": 0},
                    "end": {"line": 30, "character": 0},
                },
                "selectionRange": {
                    "start": {"line": 10, "character": 4},
                    "end": {"line": 10, "character": 16},
                },
            }
        ]
        self.client._send_request = AsyncMock(return_value=prepare_result)

        items = await self.client.prepare_call_hierarchy("file:///core.py", 10, 4)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].name, "process_data")

        # Now test incoming_calls
        incoming_result = [
            {
                "from": {
                    "name": "main",
                    "kind": 12,
                    "uri": "file:///main.py",
                    "range": {
                        "start": {"line": 1, "character": 0},
                        "end": {"line": 5, "character": 0},
                    },
                },
                "fromRanges": [
                    {
                        "start": {"line": 3, "character": 4},
                        "end": {"line": 3, "character": 16},
                    }
                ],
            }
        ]
        self.client._send_request = AsyncMock(return_value=incoming_result)

        callers = await self.client.incoming_calls(items[0])

        self.assertEqual(len(callers), 1)
        self.assertEqual(callers[0].name, "main")
        self.assertEqual(len(callers[0].call_ranges), 1)

    async def test_request_timeout(self):
        """Request raises asyncio.TimeoutError after timeout_s."""
        # Create a client with very short timeout
        short_client = LSPClient(
            process=self.proc,
            root_uri="file:///project",
            timeout_s=0.01,
        )
        # _send_request creates a future that never resolves
        # We need the reader task to not run, so the future times out
        short_client._reader_task = asyncio.create_task(asyncio.sleep(10))

        with self.assertRaises(asyncio.TimeoutError):
            await short_client._send_request("textDocument/hover", {"test": True})

        short_client._reader_task.cancel()
        try:
            await short_client._reader_task
        except asyncio.CancelledError:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# TestLSPClientDataclasses
# ═══════════════════════════════════════════════════════════════════════════


class TestLSPClientDataclasses(unittest.TestCase):
    """Tests for LSP dataclass parsing and properties."""

    def test_location_from_lsp(self):
        """Location.from_lsp parses uri and range correctly."""
        raw = _make_lsp_location_raw("file:///foo.py", 42, 7)
        loc = Location.from_lsp(raw)
        self.assertEqual(loc.uri, "file:///foo.py")
        self.assertEqual(loc.start_line, 42)
        self.assertEqual(loc.start_character, 7)

    def test_diagnostic_severity_label(self):
        """Diagnostic.severity_label maps severity ints to strings."""
        self.assertEqual(Diagnostic(uri="", message="", severity=1).severity_label, "error")
        self.assertEqual(Diagnostic(uri="", message="", severity=2).severity_label, "warning")
        self.assertEqual(Diagnostic(uri="", message="", severity=3).severity_label, "information")
        self.assertEqual(Diagnostic(uri="", message="", severity=4).severity_label, "hint")
        self.assertEqual(Diagnostic(uri="", message="", severity=99).severity_label, "unknown")

    def test_diagnostic_from_lsp(self):
        """Diagnostic.from_lsp parses all fields."""
        raw = _make_lsp_diagnostic_raw("missing comma", 1, 7, "eslint")
        diag = Diagnostic.from_lsp("file:///index.ts", raw)
        self.assertEqual(diag.uri, "file:///index.ts")
        self.assertEqual(diag.message, "missing comma")
        self.assertEqual(diag.severity, 1)
        self.assertEqual(diag.source, "eslint")
        self.assertEqual(diag.start_line, 7)
        self.assertEqual(diag.code, "W001")

    def test_diagnostic_report_counts(self):
        """DiagnosticReport.error_count and warning_count work."""
        report = DiagnosticReport(
            uri="file:///test.py",
            diagnostics=[
                Diagnostic(uri="", message="e1", severity=1),
                Diagnostic(uri="", message="e2", severity=1),
                Diagnostic(uri="", message="w1", severity=2),
                Diagnostic(uri="", message="h1", severity=4),
            ],
        )
        self.assertEqual(report.error_count, 2)
        self.assertEqual(report.warning_count, 1)

    def test_hover_result_from_lsp_none(self):
        """HoverResult.from_lsp returns None for None input."""
        self.assertIsNone(HoverResult.from_lsp(None))

    def test_hover_result_from_lsp_string_contents(self):
        """HoverResult.from_lsp handles plain string contents."""
        raw = {"contents": "simple hover text"}
        result = HoverResult.from_lsp(raw)
        self.assertEqual(result.contents, "simple hover text")

    def test_hover_result_from_lsp_list_contents(self):
        """HoverResult.from_lsp handles list contents (MarkedString[])."""
        raw = {
            "contents": [
                {"language": "python", "value": "def foo()"},
                "A function that does stuff",
            ]
        }
        result = HoverResult.from_lsp(raw)
        self.assertIn("def foo()", result.contents)
        self.assertIn("A function that does stuff", result.contents)

    def test_document_symbol_from_lsp(self):
        """DocumentSymbol.from_lsp parses nested children."""
        raw = {
            "name": "Outer",
            "kind": 5,
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": 50, "character": 0},
            },
            "children": [
                {
                    "name": "inner",
                    "kind": 6,
                    "range": {
                        "start": {"line": 2, "character": 4},
                        "end": {"line": 10, "character": 0},
                    },
                    "children": [],
                },
            ],
        }
        sym = DocumentSymbol.from_lsp(raw, uri="file:///test.py")
        self.assertEqual(sym.name, "Outer")
        self.assertEqual(sym.kind, 5)
        self.assertEqual(len(sym.children), 1)
        self.assertEqual(sym.children[0].name, "inner")

    def test_encode_message(self):
        """_encode_message wraps body with Content-Length header."""
        body = b'{"jsonrpc":"2.0","id":1}'
        encoded = _encode_message(body)
        expected_header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self.assertIn(expected_header, encoded)
        self.assertTrue(encoded.endswith(body))

    def test_text_document_position(self):
        """_text_document_position builds correct structure."""
        result = _text_document_position("file:///test.py", 10, 5)
        self.assertEqual(result["textDocument"]["uri"], "file:///test.py")
        self.assertEqual(result["position"]["line"], 10)
        self.assertEqual(result["position"]["character"], 5)


# ═══════════════════════════════════════════════════════════════════════════
# TestLSPManager
# ═══════════════════════════════════════════════════════════════════════════


class TestLSPManager(unittest.TestCase):
    """Tests for services/lsp_manager.py"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self._tmp.name)
        self.project_dir = self.tmp_root / "project"
        self.project_dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_detect_typescript_project(self):
        """detect_languages finds typescript when tsconfig.json exists."""
        (self.project_dir / "tsconfig.json").write_text("{}")
        manager = LSPManager(self.project_dir)
        langs = manager.detect_languages(self.project_dir)
        self.assertIn("typescript", langs)

    def test_detect_python_project(self):
        """detect_languages finds python when pyproject.toml exists."""
        (self.project_dir / "pyproject.toml").write_text("[build-system]")
        manager = LSPManager(self.project_dir)
        langs = manager.detect_languages(self.project_dir)
        self.assertIn("python", langs)

    def test_detect_rust_project(self):
        """detect_languages finds rust when Cargo.toml exists."""
        (self.project_dir / "Cargo.toml").write_text("[package]")
        manager = LSPManager(self.project_dir)
        langs = manager.detect_languages(self.project_dir)
        self.assertIn("rust", langs)

    def test_detect_go_project(self):
        """detect_languages finds go when go.mod exists."""
        (self.project_dir / "go.mod").write_text("module example.com/test")
        manager = LSPManager(self.project_dir)
        langs = manager.detect_languages(self.project_dir)
        self.assertIn("go", langs)

    def test_detect_multiple_languages(self):
        """detect_languages finds multiple languages in mixed projects."""
        (self.project_dir / "tsconfig.json").write_text("{}")
        (self.project_dir / "pyproject.toml").write_text("[build-system]")
        (self.project_dir / "go.mod").write_text("module x")
        manager = LSPManager(self.project_dir)
        langs = manager.detect_languages(self.project_dir)
        self.assertIn("typescript", langs)
        self.assertIn("python", langs)
        self.assertIn("go", langs)

    def test_no_detection_empty(self):
        """detect_languages returns empty for bare directory."""
        empty_dir = self.tmp_root / "empty"
        empty_dir.mkdir()
        manager = LSPManager(empty_dir)
        langs = manager.detect_languages(empty_dir)
        self.assertEqual(langs, [])

    def test_detect_languages_by_extension_sampling(self):
        """detect_languages uses extension sampling when no markers exist."""
        src = self.project_dir / "src"
        src.mkdir()
        (src / "main.rs").write_text("fn main() {}")
        manager = LSPManager(self.project_dir)
        langs = manager.detect_languages(self.project_dir)
        self.assertIn("rust", langs)

    def test_ensure_server_lazy_spawn(self):
        """ensure_server only spawns when first requested (returns None without binary)."""
        manager = LSPManager(self.project_dir, config=LSPConfig(auto_install=False))
        # No binary installed, so ensure_server should return None
        result = asyncio.run(
            manager.ensure_server("python", self.project_dir)
        )
        self.assertIsNone(result)

    def test_stop_server_nonexistent(self):
        """stop_server on non-existing server does not raise."""
        manager = LSPManager(self.project_dir)
        # Should not raise
        asyncio.run(manager.stop_server("python", self.project_dir))

    def test_server_crash_recovery_circuit_breaker(self):
        """Server not restarted after max_restarts exceeded."""
        manager = LSPManager(self.project_dir)
        spec = LSPServerSpec(
            language_id="python",
            server_name="pyright",
            command="pyright-langserver",
        )
        # Create a mock process that has exited (poll returns exit code)
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1
        instance = LSPServerInstance(
            spec=spec,
            root_uri=self.project_dir.as_uri(),
            status=LSPServerStatus.READY,
            restart_count=3,
            max_restarts=3,
            process=mock_proc,
            pid=999,
        )
        key = ("python", str(self.project_dir), None)
        manager._instances[key] = instance

        # health_check should detect crashed
        status = manager.health_check(instance)
        self.assertEqual(status, LSPServerStatus.CRASHED)
        # restart_count >= max_restarts, so circuit breaker is tripped
        self.assertGreaterEqual(instance.restart_count, instance.max_restarts)

    def test_config_defaults(self):
        """LSPConfig() has sensible defaults."""
        config = LSPConfig()
        self.assertTrue(config.enabled)
        self.assertTrue(config.auto_install)
        self.assertTrue(config.auto_detect)
        self.assertEqual(config.max_servers_per_worktree, 6)
        self.assertEqual(config.health_check_interval_s, 30.0)
        self.assertEqual(config.request_timeout_s, 10.0)
        self.assertEqual(config.diagnostics_debounce_ms, 500)
        self.assertEqual(config.diagnostics_timeout_s, 5.0)
        self.assertEqual(config.max_diagnostics_per_file, 100)
        self.assertEqual(config.disabled_servers, [])
        self.assertEqual(config.custom_servers, [])

    def test_config_yaml(self):
        """LSPConfig.load() reads from lsp.yaml."""
        sw_dir = self.project_dir / ".swarmweaver"
        sw_dir.mkdir()
        yaml_content = """\
enabled: false
auto_install: false
max_servers_per_worktree: 2
request_timeout_s: 5.0
disabled_servers:
  - jdtls
  - solargraph
"""
        (sw_dir / "lsp.yaml").write_text(yaml_content)

        try:
            import yaml  # noqa: F401 — check if available
            config = LSPConfig.load(self.project_dir)
            self.assertFalse(config.enabled)
            self.assertFalse(config.auto_install)
            self.assertEqual(config.max_servers_per_worktree, 2)
            self.assertEqual(config.request_timeout_s, 5.0)
            self.assertIn("jdtls", config.disabled_servers)
        except ImportError:
            # PyYAML not installed — config should still load with defaults
            config = LSPConfig.load(self.project_dir)
            self.assertTrue(config.enabled)

    def test_config_env(self):
        """LSPConfig.load() reads SWARMWEAVER_LSP_* env vars."""
        env_patch = {
            "SWARMWEAVER_LSP_ENABLED": "false",
            "SWARMWEAVER_LSP_AUTO_INSTALL": "0",
            "SWARMWEAVER_LSP_MAX_SERVERS": "2",
            "SWARMWEAVER_LSP_REQUEST_TIMEOUT": "3.5",
            "SWARMWEAVER_LSP_DISABLED_SERVERS": "jdtls,solargraph",
        }
        with patch.dict(os.environ, env_patch, clear=False):
            config = LSPConfig.load(self.project_dir)
            self.assertFalse(config.enabled)
            self.assertFalse(config.auto_install)
            self.assertEqual(config.max_servers_per_worktree, 2)
            self.assertEqual(config.request_timeout_s, 3.5)
            self.assertIn("jdtls", config.disabled_servers)
            self.assertIn("solargraph", config.disabled_servers)

    def test_builtin_specs_not_empty(self):
        """BUILTIN_SERVER_SPECS contains at least the core 4 servers."""
        names = {s.server_name for s in BUILTIN_SERVER_SPECS}
        self.assertIn("typescript-language-server", names)
        self.assertIn("pyright", names)
        self.assertIn("gopls", names)
        self.assertIn("rust-analyzer", names)

    def test_extension_map_coverage(self):
        """EXTENSION_TO_LANGUAGE covers common file extensions."""
        self.assertEqual(EXTENSION_TO_LANGUAGE[".py"], "python")
        self.assertEqual(EXTENSION_TO_LANGUAGE[".ts"], "typescript")
        self.assertEqual(EXTENSION_TO_LANGUAGE[".go"], "go")
        self.assertEqual(EXTENSION_TO_LANGUAGE[".rs"], "rust")
        self.assertEqual(EXTENSION_TO_LANGUAGE[".java"], "java")
        self.assertEqual(EXTENSION_TO_LANGUAGE[".rb"], "ruby")

    def test_get_diagnostics_empty(self):
        """get_diagnostics returns [] when no instance matches the file."""
        manager = LSPManager(self.project_dir)
        diags = manager.get_diagnostics("/nonexistent/file.py")
        self.assertEqual(diags, [])

    def test_get_all_instances_empty(self):
        """get_all_instances returns empty list initially."""
        manager = LSPManager(self.project_dir)
        self.assertEqual(manager.get_all_instances(), [])

    def test_update_diagnostics(self):
        """update_diagnostics stores diagnostics on instance."""
        manager = LSPManager(self.project_dir)
        spec = LSPServerSpec(
            language_id="python",
            server_name="pyright",
            command="pyright-langserver",
        )
        instance = LSPServerInstance(spec=spec, root_uri=self.project_dir.as_uri())

        diags = [{"message": "error1", "severity": 1}, {"message": "warn1", "severity": 2}]
        manager.update_diagnostics("file:///test.py", diags, instance)

        self.assertEqual(len(instance.diagnostics["file:///test.py"]), 2)

    def test_disabled_server_not_in_spec_index(self):
        """Servers in disabled_servers list are excluded from spec index."""
        config = LSPConfig(disabled_servers=["pyright"])
        manager = LSPManager(self.project_dir, config=config)
        # pyright should not be in the spec index
        python_specs = manager._spec_index.get("python", [])
        names = [s.server_name for s in python_specs]
        self.assertNotIn("pyright", names)


class TestLSPLazySpawn(unittest.IsolatedAsyncioTestCase):
    """Tests for lazy LSP server spawning in notify_file_changed."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self._tmp.name)
        self.project_dir = self.tmp_root / "project"
        self.project_dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    async def test_lazy_spawn_on_first_write(self):
        """notify_file_changed with root_path lazily spawns a server."""
        manager = LSPManager(self.project_dir)
        tsx_file = self.project_dir / "src" / "App.tsx"
        tsx_file.parent.mkdir(parents=True, exist_ok=True)
        tsx_file.write_text("export const App = () => <div />;")

        # Mock ensure_server to avoid spawning a real process
        mock_instance = MagicMock()
        mock_instance.client = MagicMock()
        mock_instance.client.did_open = AsyncMock()
        mock_instance.client.did_change = AsyncMock()
        mock_instance.spec = MagicMock()
        mock_instance.spec.server_name = "typescript-language-server"
        mock_instance.status = LSPServerStatus.READY
        mock_instance.open_files = set()
        mock_instance.diagnostics = {}

        with patch.object(manager, "ensure_server", new=AsyncMock(return_value=mock_instance)) as mock_ensure:
            with patch.object(manager, "get_instance_for_file", return_value=None):
                result = await manager.notify_file_changed(
                    str(tsx_file), "export const App = () => <div />;",
                    worker_id="1", root_path=self.project_dir,
                )
            # ensure_server should have been called with the language id
            mock_ensure.assert_called_once()
            call_args = mock_ensure.call_args
            self.assertEqual(call_args[0][0], "typescriptreact")  # lang_id from .tsx
            self.assertEqual(call_args[1]["worker_id"], "1")

    async def test_no_lazy_spawn_without_root_path(self):
        """notify_file_changed without root_path does NOT lazy-spawn."""
        manager = LSPManager(self.project_dir)
        tsx_file = self.project_dir / "src" / "App.tsx"
        tsx_file.parent.mkdir(parents=True, exist_ok=True)
        tsx_file.write_text("export const App = () => <div />;")

        with patch.object(manager, "ensure_server", new=AsyncMock()) as mock_ensure:
            with patch.object(manager, "get_instance_for_file", return_value=None):
                result = await manager.notify_file_changed(
                    str(tsx_file), "export const App = () => <div />;",
                    worker_id="1",
                )
            mock_ensure.assert_not_called()
            self.assertEqual(result, [])

    async def test_server_dedup_same_binary(self):
        """ensure_server deduplicates when same server_name already running."""
        manager = LSPManager(self.project_dir)

        # Simulate a running instance for "typescript" lang
        ts_spec = manager._resolve_spec("typescript", self.project_dir)
        self.assertIsNotNone(ts_spec)
        mock_instance = LSPServerInstance(
            spec=ts_spec,
            root_uri=self.project_dir.as_uri(),
            worker_id="1",
            status=LSPServerStatus.READY,
        )
        key_ts = ("typescript", str(self.project_dir), "1")
        manager._instances[key_ts] = mock_instance

        # Now try ensure_server for "javascriptreact" (also typescript-language-server)
        with patch("shutil.which", return_value="/usr/bin/typescript-language-server"):
            result = await manager.ensure_server(
                "javascriptreact", self.project_dir, worker_id="1"
            )

        # Should reuse the existing instance, not spawn a new one
        self.assertIs(result, mock_instance)
        # The new key should also point to the same instance
        key_jsx = ("javascriptreact", str(self.project_dir), "1")
        self.assertIs(manager._instances[key_jsx], mock_instance)


class TestLSPStats(unittest.TestCase):
    """Tests for diagnostic history tracking and stats."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project_dir = Path(self._tmp.name) / "project"
        self.project_dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_track_new_diagnostics(self):
        """New diagnostics are recorded as 'found' events."""
        manager = LSPManager(self.project_dir)
        diags = [
            {"uri": "file:///test.ts", "start_line": 1, "message": "Error 1", "severity": 1},
            {"uri": "file:///test.ts", "start_line": 5, "message": "Warn 1", "severity": 2},
        ]
        manager._track_diagnostic_changes("file:///test.ts", diags, "1")
        stats = manager.get_stats()
        self.assertEqual(stats["total_found"], 2)
        self.assertEqual(stats["total_resolved"], 0)
        self.assertEqual(stats["by_worker"]["1"]["found"], 2)

    def test_track_resolved_diagnostics(self):
        """When diagnostics disappear, they are recorded as 'resolved'."""
        manager = LSPManager(self.project_dir)
        # First: 2 diagnostics appear
        diags = [
            {"uri": "file:///test.ts", "start_line": 1, "message": "Error 1", "severity": 1},
            {"uri": "file:///test.ts", "start_line": 5, "message": "Warn 1", "severity": 2},
        ]
        manager._track_diagnostic_changes("file:///test.ts", diags, "1")
        # Then: only 1 remains (Error 1 was fixed)
        diags2 = [
            {"uri": "file:///test.ts", "start_line": 5, "message": "Warn 1", "severity": 2},
        ]
        manager._track_diagnostic_changes("file:///test.ts", diags2, "1")
        stats = manager.get_stats()
        self.assertEqual(stats["total_found"], 2)
        self.assertEqual(stats["total_resolved"], 1)
        self.assertEqual(stats["by_worker"]["1"]["resolved"], 1)

    def test_track_all_resolved(self):
        """When all diagnostics clear, all are recorded as resolved."""
        manager = LSPManager(self.project_dir)
        diags = [{"uri": "file:///a.ts", "start_line": 1, "message": "Err", "severity": 1}]
        manager._track_diagnostic_changes("file:///a.ts", diags, "2")
        manager._track_diagnostic_changes("file:///a.ts", [], "2")
        stats = manager.get_stats()
        self.assertEqual(stats["total_found"], 1)
        self.assertEqual(stats["total_resolved"], 1)

    def test_recent_events_timeline(self):
        """Recent events are in chronological order."""
        manager = LSPManager(self.project_dir)
        diags = [{"uri": "file:///x.ts", "start_line": 1, "message": "Err", "severity": 1}]
        manager._track_diagnostic_changes("file:///x.ts", diags, "1")
        manager._track_diagnostic_changes("file:///x.ts", [], "1")
        stats = manager.get_stats()
        events = stats["recent_events"]
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event"], "found")
        self.assertEqual(events[1]["event"], "resolved")

    def test_by_severity_tracking(self):
        """Severity breakdown tracks errors vs warnings separately."""
        manager = LSPManager(self.project_dir)
        diags = [
            {"uri": "file:///a.ts", "start_line": 1, "message": "Err", "severity": 1},
            {"uri": "file:///a.ts", "start_line": 2, "message": "Warn", "severity": 2},
        ]
        manager._track_diagnostic_changes("file:///a.ts", diags, "1")
        # Fix the error only
        diags2 = [{"uri": "file:///a.ts", "start_line": 2, "message": "Warn", "severity": 2}]
        manager._track_diagnostic_changes("file:///a.ts", diags2, "1")
        stats = manager.get_stats()
        self.assertEqual(stats["by_severity"][1]["found"], 1)
        self.assertEqual(stats["by_severity"][1]["resolved"], 1)
        self.assertEqual(stats["by_severity"][2]["found"], 1)
        self.assertEqual(stats["by_severity"][2]["resolved"], 0)


# ═══════════════════════════════════════════════════════════════════════════
# TestLSPHooks
# ═══════════════════════════════════════════════════════════════════════════


class TestLSPHooks(unittest.IsolatedAsyncioTestCase):
    """Tests for hooks/lsp_hooks.py"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    async def test_fires_on_write(self):
        """lsp_post_edit_hook activates for Write tool."""
        manager = AsyncMock()
        manager.notify_file_changed = AsyncMock(return_value=[
            {"uri": "file:///test.py", "message": "type error", "severity": 1, "start_line": 5},
        ])
        set_lsp_context(manager, self.tmp_root)

        # Create the file on disk
        test_file = self.tmp_root / "test.py"
        test_file.write_text("x = 1")

        result = await lsp_post_edit_hook({
            "tool_name": "Write",
            "tool_input": {"file_path": str(test_file)},
        })

        self.assertEqual(result.get("decision"), "block")
        self.assertIn("ERROR", result.get("reason", ""))

    async def test_fires_on_edit(self):
        """lsp_post_edit_hook activates for Edit tool."""
        manager = AsyncMock()
        manager.notify_file_changed = AsyncMock(return_value=[
            {"uri": "file:///test.py", "message": "unused var", "severity": 2, "start_line": 3},
        ])
        set_lsp_context(manager, self.tmp_root)

        test_file = self.tmp_root / "test.py"
        test_file.write_text("x = 1")

        result = await lsp_post_edit_hook({
            "tool_name": "Edit",
            "tool_input": {"file_path": str(test_file)},
        })

        self.assertEqual(result.get("decision"), "block")
        self.assertIn("WARNING", result.get("reason", ""))

    async def test_skips_non_write(self):
        """lsp_post_edit_hook returns {} for Read, Bash, etc."""
        for tool in ("Read", "Bash", "Glob", "Grep"):
            result = await lsp_post_edit_hook({
                "tool_name": tool,
                "tool_input": {"command": "ls"},
            })
            self.assertEqual(result, {}, f"Should skip for {tool}")

    async def test_debounces(self):
        """Rapid edits to same file are debounced (< 150ms)."""
        manager = AsyncMock()
        manager.notify_file_changed = AsyncMock(return_value=[
            {"uri": "", "message": "err", "severity": 1, "start_line": 1},
        ])
        set_lsp_context(manager, self.tmp_root)

        test_file = self.tmp_root / "test.py"
        test_file.write_text("x = 1")

        # First call should proceed
        result1 = await lsp_post_edit_hook({
            "tool_name": "Write",
            "tool_input": {"file_path": str(test_file)},
        })
        # Immediately call again (< 150ms)
        result2 = await lsp_post_edit_hook({
            "tool_name": "Write",
            "tool_input": {"file_path": str(test_file)},
        })

        # Second call should be debounced (returns {})
        self.assertEqual(result2, {})

    async def test_injects_errors(self):
        """When diagnostics contain errors, hook returns block with injection."""
        manager = AsyncMock()
        manager.notify_file_changed = AsyncMock(return_value=[
            {"uri": "", "message": "SyntaxError: invalid syntax", "severity": 1,
             "start_line": 10, "source": "pyright"},
        ])
        set_lsp_context(manager, self.tmp_root)

        test_file = self.tmp_root / "syntax_error.py"
        test_file.write_text("def foo(:\n    pass")

        # Ensure not debounced by using a unique file
        result = await lsp_post_edit_hook({
            "tool_name": "Write",
            "tool_input": {"file_path": str(test_file)},
        })

        self.assertEqual(result["decision"], "block")
        self.assertIn("SyntaxError", result["reason"])
        self.assertIn("line 11", result["reason"])  # 0-based + 1 = 11
        self.assertIn("pyright", result["reason"])

    async def test_no_manager_returns_empty(self):
        """Hook returns {} when no LSP manager is configured."""
        set_lsp_context(None, self.tmp_root)

        result = await lsp_post_edit_hook({
            "tool_name": "Write",
            "tool_input": {"file_path": "/some/file.py"},
        })
        self.assertEqual(result, {})

    async def test_watchdog_signal(self):
        """lsp_diagnostic_watchdog_signal tracks error trend."""
        manager = AsyncMock()
        manager.get_all_diagnostics = MagicMock(return_value=[
            {"uri": "", "message": "err", "severity": 1, "start_line": 0},
            {"uri": "", "message": "err2", "severity": 1, "start_line": 1},
        ])
        set_lsp_context(manager, self.tmp_root)

        # Run WATCHDOG_EVERY_N calls to trigger the check
        for i in range(WATCHDOG_EVERY_N):
            result = await lsp_diagnostic_watchdog_signal({
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
            })

        # The last call should have triggered the watchdog
        self.assertEqual(result, {})  # Watchdog never blocks


# ═══════════════════════════════════════════════════════════════════════════
# TestLSPTools
# ═══════════════════════════════════════════════════════════════════════════


class TestLSPTools(unittest.TestCase):
    """Tests for services/lsp_tools.py"""

    def test_is_in_scope_matches(self):
        """_is_in_scope returns True for matching glob patterns."""
        self.assertTrue(_is_in_scope("src/app.py", ["src/*"]))
        self.assertTrue(_is_in_scope("src/utils/helpers.py", ["src/**/*.py"]))
        self.assertTrue(_is_in_scope("tests/test_a.py", ["tests/*"]))

    def test_is_in_scope_rejects(self):
        """_is_in_scope returns False for non-matching patterns."""
        self.assertFalse(_is_in_scope("docs/README.md", ["src/*"]))
        self.assertFalse(_is_in_scope("config.yaml", ["src/*", "tests/*"]))

    def test_is_in_scope_empty_scope(self):
        """_is_in_scope returns False for empty scope (restrictive default)."""
        self.assertFalse(_is_in_scope("any/file.py", []))

    def test_make_error_format(self):
        """_make_error returns MCP-formatted error response."""
        result = _make_error("something went wrong")
        content = result["content"][0]
        self.assertEqual(content["type"], "text")
        parsed = json.loads(content["text"])
        self.assertEqual(parsed["error"], "something went wrong")

    def test_make_result_format(self):
        """_make_result returns MCP-formatted success response."""
        result = _make_result({"ok": True, "data": [1, 2, 3]})
        content = result["content"][0]
        self.assertEqual(content["type"], "text")
        parsed = json.loads(content["text"])
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["data"], [1, 2, 3])

    def test_operations_list_complete(self):
        """_OPERATIONS contains all expected LSP operations."""
        expected = {
            "definition", "references", "hover", "symbols",
            "diagnostics", "call_hierarchy", "completion",
            "rename_preview", "workspace_symbols", "implementation",
            "signature_help", "code_actions", "formatting",
        }
        self.assertEqual(set(_OPERATIONS), expected)

    def test_tool_names(self):
        """LSP_TOOL_NAMES has the expected tool name patterns."""
        self.assertIn("mcp__lsp_tools__lsp_query", LSP_TOOL_NAMES)
        self.assertIn("mcp__lsp_tools__lsp_diagnostics_summary", LSP_TOOL_NAMES)
        self.assertEqual(len(LSP_TOOL_NAMES), 2)


# ═══════════════════════════════════════════════════════════════════════════
# TestLSPWorktreeIsolation
# ═══════════════════════════════════════════════════════════════════════════


class TestLSPWorktreeIsolation(unittest.TestCase):
    """Tests for per-worktree LSP server isolation."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self._tmp.name)
        self.project_dir = self.tmp_root / "project"
        self.project_dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_separate_servers(self):
        """Different worktrees get separate LSP server instances (via key tuple)."""
        manager = LSPManager(self.project_dir)

        spec = LSPServerSpec(
            language_id="python",
            server_name="pyright",
            command="pyright-langserver",
        )

        worktree_a = self.tmp_root / "wt-a"
        worktree_b = self.tmp_root / "wt-b"
        worktree_a.mkdir()
        worktree_b.mkdir()

        instance_a = LSPServerInstance(
            spec=spec, root_uri=worktree_a.as_uri(), worker_id="worker-1"
        )
        instance_b = LSPServerInstance(
            spec=spec, root_uri=worktree_b.as_uri(), worker_id="worker-2"
        )

        key_a = ("python", str(worktree_a), "worker-1")
        key_b = ("python", str(worktree_b), "worker-2")
        manager._instances[key_a] = instance_a
        manager._instances[key_b] = instance_b

        # They should be separate instances
        self.assertIsNot(
            manager._instances[key_a],
            manager._instances[key_b],
        )
        self.assertEqual(len(manager.get_all_instances()), 2)

    def test_worker_id_tagging(self):
        """Instances are tagged with worker_id."""
        spec = LSPServerSpec(
            language_id="typescript",
            server_name="typescript-language-server",
            command="typescript-language-server",
        )
        instance = LSPServerInstance(
            spec=spec,
            root_uri="file:///worktree",
            worker_id="worker-42",
        )
        self.assertEqual(instance.worker_id, "worker-42")

    def test_cross_worker_routing(self):
        """Diagnostics from one worker's edit can be detected for affected files."""
        manager = LSPManager(self.project_dir)
        spec = LSPServerSpec(
            language_id="python",
            server_name="pyright",
            command="pyright-langserver",
            extensions=[".py"],
        )

        # Worker 1 owns src/
        worktree = self.project_dir
        instance = LSPServerInstance(
            spec=spec,
            root_uri=worktree.as_uri(),
            worker_id="worker-1",
            status=LSPServerStatus.READY,
        )
        key = ("python", str(worktree), "worker-1")
        manager._instances[key] = instance

        # Store diagnostics for a file in worker-1's scope
        diags = [{"message": "error", "severity": 1}]
        manager.update_diagnostics("file:///project/src/utils.py", diags, instance)

        self.assertEqual(len(instance.diagnostics["file:///project/src/utils.py"]), 1)

    def test_cross_worker_mail(self):
        """_route_cross_worker_diagnostics creates mail messages for affected workers."""
        mail_dir = self.tmp_root / "mail_project"
        mail_dir.mkdir()
        (mail_dir / ".swarmweaver").mkdir()

        file_scope_map = {
            "/project/src/utils.py": "worker-2",
            "/project/src/main.py": "worker-1",
        }

        diags = [
            Diagnostic(
                uri="file:///project/src/utils.py",
                message="type mismatch",
                severity=1,
                start_line=10,
            ),
        ]

        # Mock MailStore and MessageType to avoid real SQLite
        mock_store = MagicMock()
        mock_mail_store_cls = MagicMock(return_value=mock_store)
        mock_message_type = MagicMock()
        mock_message_type.DISPATCH.value = "dispatch"

        with patch.dict("sys.modules", {}):
            with patch(
                "state.mail.MailStore", mock_mail_store_cls, create=True
            ), patch(
                "state.mail.MessageType", mock_message_type, create=True
            ):
                asyncio.run(
                    _route_cross_worker_diagnostics(
                        diags, "worker-1", mail_dir, file_scope_map
                    )
                )

            # Should have sent mail to worker-2 (file owner)
            mock_store.send.assert_called_once()
            call_kwargs = mock_store.send.call_args
            self.assertIn("worker-2", str(call_kwargs))


# ═══════════════════════════════════════════════════════════════════════════
# TestLSPIntelligence
# ═══════════════════════════════════════════════════════════════════════════


class TestLSPIntelligence(unittest.IsolatedAsyncioTestCase):
    """Tests for services/lsp_intelligence.py"""

    def setUp(self):
        self.manager = MagicMock()

    async def test_impact_analysis(self):
        """impact_analysis returns references, callers, risk_level."""
        mock_instance = MagicMock()
        mock_client = AsyncMock()
        mock_instance.client = mock_client
        mock_instance.status.value = "ready"
        self.manager.get_instance_for_file.return_value = mock_instance

        # Mock hover
        mock_client.hover.return_value = HoverResult(contents="def process()")

        # Mock references — lots of refs for high risk
        # The code accesses r.uri and r.range_start_line on these objects
        def _make_ref(uri, line):
            ref = MagicMock()
            ref.uri = uri
            ref.range_start_line = line
            return ref

        refs = [_make_ref(f"file:///file{i}.py", i) for i in range(25)]
        mock_client.find_references.return_value = refs

        # Mock call hierarchy — prepare returns objects, incoming/outgoing return dicts
        mock_item = MagicMock()
        mock_item.name = "process"
        mock_item.kind = 12
        mock_client.prepare_call_hierarchy.return_value = [mock_item]
        mock_client.incoming_calls.return_value = [
            {"from": {"name": "main", "uri": "file:///main.py",
                       "range": {"start": {"line": 1}}}, "fromRanges": []}
        ]
        mock_client.outgoing_calls.return_value = []

        intel = CodeIntelligence(self.manager)
        result = await intel.impact_analysis("/project/core.py", 10, 0)

        self.assertIn("references", result)
        self.assertIn("risk_level", result)
        self.assertEqual(result["risk_level"], "high")
        self.assertEqual(result["total_references"], 25)

    async def test_impact_analysis_low_risk(self):
        """impact_analysis returns low risk for symbols with few references."""
        mock_instance = MagicMock()
        mock_client = AsyncMock()
        mock_instance.client = mock_client
        mock_instance.status.value = "ready"
        self.manager.get_instance_for_file.return_value = mock_instance

        mock_client.hover.return_value = HoverResult(contents="helper()")

        ref = MagicMock()
        ref.uri = "file:///same.py"
        ref.range_start_line = 5
        mock_client.find_references.return_value = [ref]
        mock_client.prepare_call_hierarchy.return_value = []

        intel = CodeIntelligence(self.manager)
        result = await intel.impact_analysis("/project/util.py", 5, 0)

        self.assertEqual(result["risk_level"], "low")
        self.assertEqual(result["total_references"], 1)

    async def test_impact_analysis_no_server(self):
        """impact_analysis returns error when no LSP server available."""
        self.manager.get_instance_for_file.return_value = None

        intel = CodeIntelligence(self.manager)
        result = await intel.impact_analysis("/project/unknown.xyz", 0, 0)

        self.assertIn("error", result)

    async def test_code_health_score(self):
        """code_health_score returns 0-100 score based on diagnostics."""
        # Mock diagnostics: 2 errors, 3 warnings
        diags = [
            {"uri": "", "message": "e1", "severity": 1, "start_line": 0},
            {"uri": "", "message": "e2", "severity": 1, "start_line": 0},
            {"uri": "", "message": "w1", "severity": 2, "start_line": 0},
            {"uri": "", "message": "w2", "severity": 2, "start_line": 0},
            {"uri": "", "message": "w3", "severity": 2, "start_line": 0},
        ]
        self.manager.get_all_diagnostics.return_value = diags
        self.manager.get_all_instances.return_value = []

        intel = CodeIntelligence(self.manager)
        result = await intel.code_health_score()

        # Score: 100 - (2*5) - (3*1) = 87
        self.assertEqual(result["score"], 87)
        self.assertEqual(result["error_count"], 2)
        self.assertEqual(result["warning_count"], 3)

    async def test_code_health_score_perfect(self):
        """code_health_score returns 100 when no errors or warnings."""
        self.manager.get_all_diagnostics.return_value = []
        self.manager.get_all_instances.return_value = []

        intel = CodeIntelligence(self.manager)
        result = await intel.code_health_score()

        self.assertEqual(result["score"], 100)
        self.assertEqual(result["error_count"], 0)

    async def test_code_health_score_zero_floor(self):
        """code_health_score never goes below 0."""
        # 30 errors -> 100 - 150 = -50 -> clamped to 0
        diags = [
            {"uri": "", "message": f"e{i}", "severity": 1, "start_line": 0}
            for i in range(30)
        ]
        self.manager.get_all_diagnostics.return_value = diags
        self.manager.get_all_instances.return_value = []

        intel = CodeIntelligence(self.manager)
        result = await intel.code_health_score()

        self.assertEqual(result["score"], 0)

    def test_build_clusters(self):
        """_build_clusters groups connected nodes together."""
        nodes = ["a.py", "b.py", "c.py", "d.py", "e.py"]
        edges = [("a.py", "b.py"), ("b.py", "c.py"), ("d.py", "e.py")]

        clusters = CodeIntelligence._build_clusters(nodes, edges)

        # Should have 2 clusters: {a,b,c} and {d,e}
        self.assertEqual(len(clusters), 2)
        flat = [sorted(c) for c in clusters]
        self.assertIn(["a.py", "b.py", "c.py"], flat)
        self.assertIn(["d.py", "e.py"], flat)

    def test_build_clusters_no_edges(self):
        """_build_clusters with no edges returns each node as its own cluster."""
        nodes = ["a.py", "b.py", "c.py"]
        clusters = CodeIntelligence._build_clusters(nodes, [])
        self.assertEqual(len(clusters), 3)


# ═══════════════════════════════════════════════════════════════════════════
# TestLSPAPI
# ═══════════════════════════════════════════════════════════════════════════


class TestLSPAPI(unittest.IsolatedAsyncioTestCase):
    """Tests for api/routers/lsp.py"""

    async def test_get_status_no_manager(self):
        """GET /api/lsp/status returns empty list when LSP not initialized."""
        from api.routers.lsp import lsp_status

        with patch("api.state.get_lsp_manager", return_value=None):
            result = await lsp_status(path="/project")

        self.assertEqual(result["servers"], [])
        self.assertIn("not initialized", result.get("message", ""))

    async def test_get_status_with_servers(self):
        """GET /api/lsp/status returns server list with details."""
        from api.routers.lsp import lsp_status

        mock_instance = MagicMock()
        mock_instance.spec.language_id = "python"
        mock_instance.spec.server_name = "pyright"
        mock_instance.status.value = "ready"
        mock_instance.root_uri = "file:///project"
        mock_instance.pid = 12345
        mock_instance.started_at = time.time()
        mock_instance.restart_count = 0
        mock_instance.open_files = {"file:///a.py"}
        mock_instance.diagnostics = {"file:///a.py": [{"msg": "err"}]}
        mock_instance.worker_id = None

        mock_manager = MagicMock()
        mock_manager.get_all_instances.return_value = [mock_instance]

        with patch("api.state.get_lsp_manager", return_value=mock_manager):
            result = await lsp_status(path="/project")

        self.assertEqual(len(result["servers"]), 1)
        server = result["servers"][0]
        self.assertEqual(server["language_id"], "python")
        self.assertEqual(server["server_name"], "pyright")
        self.assertEqual(server["status"], "ready")
        self.assertEqual(server["pid"], 12345)

    async def test_get_diagnostics_no_manager(self):
        """GET /api/lsp/diagnostics returns empty when LSP not initialized."""
        from api.routers.lsp import lsp_diagnostics

        with patch("api.state.get_lsp_manager", return_value=None):
            result = await lsp_diagnostics(path="/project")

        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(result["total"], 0)

    async def test_hover_no_manager(self):
        """POST /api/lsp/hover returns error when LSP not initialized."""
        from api.routers.lsp import lsp_hover

        with patch("api.state.get_lsp_manager", return_value=None):
            result = await lsp_hover(
                path="/project",
                file_path="src/main.py",
                line=10,
                character=5,
            )

        self.assertIn("error", result)

    async def test_definition_no_manager(self):
        """POST /api/lsp/definition returns error when LSP not initialized."""
        from api.routers.lsp import lsp_definition

        with patch("api.state.get_lsp_manager", return_value=None):
            result = await lsp_definition(
                path="/project",
                file_path="src/main.py",
                line=10,
                character=5,
            )

        self.assertIn("error", result)

    async def test_restart_no_manager(self):
        """POST /api/lsp/servers/{id}/restart returns error when LSP not initialized."""
        from api.routers.lsp import lsp_restart_server

        with patch("api.state.get_lsp_manager", return_value=None):
            result = await lsp_restart_server(
                server_id="python",
                path="/project",
            )

        self.assertIn("error", result)

    async def test_code_health_no_manager(self):
        """GET /api/lsp/code-health returns score=100 when LSP not initialized."""
        from api.routers.lsp import lsp_code_health

        with patch("api.state.get_lsp_manager", return_value=None):
            result = await lsp_code_health(path="/project")

        self.assertEqual(result["score"], 100)
        self.assertEqual(result["error_count"], 0)

    async def test_config_get(self):
        """GET /api/lsp/config returns config values."""
        from api.routers.lsp import lsp_config_get

        with patch(
            "services.lsp_manager.LSPConfig.load",
            return_value=LSPConfig(enabled=True, auto_install=False),
        ):
            result = await lsp_config_get(path="/project")

        self.assertTrue(result["enabled"])
        self.assertFalse(result["auto_install"])
        self.assertIn("max_servers_per_worktree", result)

    async def test_servers_list(self):
        """GET /api/lsp/servers lists all configured server specs."""
        from api.routers.lsp import lsp_servers

        result = await lsp_servers(path="/project")

        self.assertIn("servers", result)
        self.assertGreater(len(result["servers"]), 0)
        # Verify structure
        first = result["servers"][0]
        self.assertIn("language_id", first)
        self.assertIn("server_name", first)
        self.assertIn("command", first)
        self.assertIn("extensions", first)


# ═══════════════════════════════════════════════════════════════════════════
# TestLSPServerSpec
# ═══════════════════════════════════════════════════════════════════════════


class TestLSPServerSpec(unittest.TestCase):
    """Tests for LSPServerSpec and LSPServerInstance dataclasses."""

    def test_spec_defaults(self):
        """LSPServerSpec has sensible defaults."""
        spec = LSPServerSpec(
            language_id="test",
            server_name="test-server",
            command="test-cmd",
        )
        self.assertEqual(spec.args, [])
        self.assertEqual(spec.install_command, "")
        self.assertEqual(spec.extensions, [])
        self.assertEqual(spec.project_markers, [])
        self.assertEqual(spec.init_options, {})
        self.assertEqual(spec.settings, {})
        self.assertEqual(spec.capabilities, {})
        self.assertEqual(spec.priority, 1)

    def test_instance_defaults(self):
        """LSPServerInstance has correct default status."""
        spec = LSPServerSpec(
            language_id="python",
            server_name="pyright",
            command="pyright-langserver",
        )
        instance = LSPServerInstance(spec=spec, root_uri="file:///project")
        self.assertEqual(instance.status, LSPServerStatus.STOPPED)
        self.assertIsNone(instance.client)
        self.assertIsNone(instance.process)
        self.assertIsNone(instance.pid)
        self.assertIsNone(instance.started_at)
        self.assertEqual(instance.restart_count, 0)
        self.assertEqual(instance.max_restarts, 3)
        self.assertEqual(instance.diagnostics, {})
        self.assertEqual(instance.open_files, set())
        self.assertIsNone(instance.worker_id)

    def test_server_status_enum_values(self):
        """LSPServerStatus enum has the expected values."""
        self.assertEqual(LSPServerStatus.STOPPED.value, "stopped")
        self.assertEqual(LSPServerStatus.STARTING.value, "starting")
        self.assertEqual(LSPServerStatus.READY.value, "ready")
        self.assertEqual(LSPServerStatus.DEGRADED.value, "degraded")
        self.assertEqual(LSPServerStatus.CRASHED.value, "crashed")

    def test_health_check_stopped_process(self):
        """health_check returns STOPPED when process is None."""
        manager = LSPManager(tempfile.mkdtemp())
        spec = LSPServerSpec(
            language_id="python",
            server_name="pyright",
            command="pyright-langserver",
        )
        instance = LSPServerInstance(
            spec=spec, root_uri="file:///project", process=None
        )
        status = manager.health_check(instance)
        self.assertEqual(status, LSPServerStatus.STOPPED)

    def test_health_check_crashed_process(self):
        """health_check returns CRASHED when process has exited."""
        manager = LSPManager(tempfile.mkdtemp())
        spec = LSPServerSpec(
            language_id="python",
            server_name="pyright",
            command="pyright-langserver",
        )
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # exited with code 1
        instance = LSPServerInstance(
            spec=spec,
            root_uri="file:///project",
            process=mock_proc,
            pid=999,
            status=LSPServerStatus.READY,
        )
        status = manager.health_check(instance)
        self.assertEqual(status, LSPServerStatus.CRASHED)


if __name__ == "__main__":
    unittest.main()
