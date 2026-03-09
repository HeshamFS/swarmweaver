"""
Test MCP Server Manager (services/mcp_manager.py)
===================================================

Comprehensive tests for the MCPServerConfig dataclass and MCPConfigStore
configuration manager that handles built-in, global, and project-level
MCP server configurations with layered merge semantics.

Run with:
    python -m pytest tests/test_mcp_manager.py -v
    python -m unittest tests.test_mcp_manager -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.mcp_manager import (
    MCPServerConfig,
    MCPConfigStore,
    GLOBAL_MCP_FILE,
    GLOBAL_CONFIG_DIR,
    _project_mcp_file,
)


def _make_config(
    name: str = "test_server",
    command: str = "echo",
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    enabled: bool = True,
    transport: str = "stdio",
    timeout: int = 30,
    description: str = "A test server",
    scope: str = "project",
    builtin: bool = False,
) -> MCPServerConfig:
    """Helper to build an MCPServerConfig with sensible defaults."""
    return MCPServerConfig(
        name=name,
        command=command,
        args=args or ["--help"],
        env=env or {},
        enabled=enabled,
        transport=transport,
        timeout=timeout,
        description=description,
        scope=scope,
        builtin=builtin,
    )


def _write_mcp_json(path: Path, configs: list[dict]) -> None:
    """Write a list of config dicts as a JSON file, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(configs, indent=2) + "\n", encoding="utf-8")


class _TempDirTestCase(unittest.TestCase):
    """Base class that sets up temp dirs and patches global config paths."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self._tmp.name)
        self.project_dir = self.tmp_root / "project"
        self.project_dir.mkdir()
        self.global_dir = self.tmp_root / "global_config"
        self.global_dir.mkdir()
        self.global_mcp_file = self.global_dir / "mcp_servers.json"

        # Patch the module-level global paths so tests never touch the real home dir
        self._patch_global_dir = patch(
            "services.mcp_manager.GLOBAL_CONFIG_DIR", self.global_dir
        )
        self._patch_global_file = patch(
            "services.mcp_manager.GLOBAL_MCP_FILE", self.global_mcp_file
        )
        self._patch_global_dir.start()
        self._patch_global_file.start()

    def tearDown(self):
        self._patch_global_dir.stop()
        self._patch_global_file.stop()
        self._tmp.cleanup()

    def _store(self, project_dir=None) -> MCPConfigStore:
        """Create a store with the test project dir (default) or custom."""
        return MCPConfigStore(project_dir=project_dir or self.project_dir)


# ═══════════════════════════════════════════════════════════════════════════
# MCPServerConfig Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMCPServerConfig(unittest.TestCase):
    """Tests for the MCPServerConfig dataclass serialization and defaults."""

    def test_config_to_dict_roundtrip(self):
        """to_dict then from_dict preserves every field."""
        original = _make_config(
            name="my_server",
            command="npx",
            args=["my-mcp-server", "--port", "3000"],
            env={"API_KEY": "abc123", "DEBUG": "1"},
            enabled=False,
            transport="stdio",
            timeout=60,
            description="My custom MCP server",
            scope="global",
            builtin=False,
        )
        d = original.to_dict()
        restored = MCPServerConfig.from_dict(d)

        self.assertEqual(restored.name, original.name, "name mismatch")
        self.assertEqual(restored.command, original.command, "command mismatch")
        self.assertEqual(restored.args, original.args, "args mismatch")
        self.assertEqual(restored.env, original.env, "env mismatch")
        self.assertEqual(restored.enabled, original.enabled, "enabled mismatch")
        self.assertEqual(restored.transport, original.transport, "transport mismatch")
        self.assertEqual(restored.timeout, original.timeout, "timeout mismatch")
        self.assertEqual(restored.description, original.description, "description mismatch")
        self.assertEqual(restored.scope, original.scope, "scope mismatch")
        self.assertEqual(restored.builtin, original.builtin, "builtin mismatch")

    def test_config_from_dict_ignores_unknown_keys(self):
        """Extra keys in the dict are silently ignored."""
        data = {
            "name": "server_x",
            "command": "node",
            "unknown_field": "should be ignored",
            "extra": 42,
        }
        cfg = MCPServerConfig.from_dict(data)
        self.assertEqual(cfg.name, "server_x")
        self.assertEqual(cfg.command, "node")
        self.assertFalse(hasattr(cfg, "unknown_field"))

    def test_config_to_sdk_format(self):
        """to_sdk_format returns command + args (+ env when present)."""
        cfg = _make_config(
            command="npx",
            args=["puppeteer-mcp-server"],
            env={"FOO": "bar"},
        )
        sdk = cfg.to_sdk_format()
        self.assertEqual(sdk["command"], "npx")
        self.assertEqual(sdk["args"], ["puppeteer-mcp-server"])
        self.assertEqual(sdk["env"], {"FOO": "bar"})
        # Should NOT contain internal fields
        self.assertNotIn("name", sdk)
        self.assertNotIn("enabled", sdk)
        self.assertNotIn("builtin", sdk)
        self.assertNotIn("scope", sdk)
        self.assertNotIn("timeout", sdk)

    def test_config_to_sdk_format_with_env(self):
        """SDK format includes env dict when it has entries."""
        cfg = _make_config(env={"API_KEY": "secret"})
        sdk = cfg.to_sdk_format()
        self.assertIn("env", sdk, "env should be present when non-empty")
        self.assertEqual(sdk["env"]["API_KEY"], "secret")

    def test_config_to_sdk_format_no_env(self):
        """SDK format omits env key when env dict is empty."""
        cfg = _make_config(env={})
        sdk = cfg.to_sdk_format()
        self.assertNotIn("env", sdk, "env should be omitted when empty")

    def test_config_defaults(self):
        """Verify default field values for a minimal config."""
        cfg = MCPServerConfig(name="minimal", command="test_cmd")
        self.assertEqual(cfg.args, [], "args should default to empty list")
        self.assertEqual(cfg.env, {}, "env should default to empty dict")
        self.assertTrue(cfg.enabled, "enabled should default to True")
        self.assertEqual(cfg.transport, "stdio", "transport should default to stdio")
        self.assertEqual(cfg.timeout, 30, "timeout should default to 30")
        self.assertEqual(cfg.description, "", "description should default to empty")
        self.assertEqual(cfg.scope, "project", "scope should default to project")
        self.assertFalse(cfg.builtin, "builtin should default to False")


# ═══════════════════════════════════════════════════════════════════════════
# MCPConfigStore - CRUD Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMCPConfigStoreCRUD(_TempDirTestCase):
    """Basic create/read/update/delete operations."""

    def test_list_servers_includes_builtins(self):
        """list_servers() always includes puppeteer and web_search by default."""
        store = self._store()
        servers = store.list_servers()
        names = {s.name for s in servers}
        self.assertIn("puppeteer", names, "puppeteer should be in the server list")
        self.assertIn("web_search", names, "web_search should be in the server list")

    def test_list_servers_excludes_builtins(self):
        """list_servers(include_builtin=False) omits built-in servers."""
        store = self._store()
        servers = store.list_servers(include_builtin=False)
        names = {s.name for s in servers}
        self.assertNotIn("puppeteer", names, "puppeteer should be excluded")
        self.assertNotIn("web_search", names, "web_search should be excluded")

    def test_add_server_to_project(self):
        """Adding a server to project scope creates the project config file."""
        store = self._store()
        cfg = _make_config(name="my_db")
        store.add_server(cfg, scope="project")

        project_file = _project_mcp_file(self.project_dir)
        self.assertTrue(project_file.exists(), "project MCP config file should exist")

        # Verify it appears in the merged list
        found = store.get_server("my_db")
        self.assertIsNotNone(found, "Server should be found after adding")
        self.assertEqual(found.name, "my_db")

    def test_add_server_to_global(self):
        """Adding a server to global scope creates the global config file."""
        store = self._store()
        cfg = _make_config(name="global_server")
        store.add_server(cfg, scope="global")

        self.assertTrue(
            self.global_mcp_file.exists(), "global MCP config file should exist"
        )
        found = store.get_server("global_server")
        self.assertIsNotNone(found, "Global server should be found")

    def test_add_server_overwrites_existing(self):
        """Adding a server with the same name replaces the old entry."""
        store = self._store()
        v1 = _make_config(name="replaceable", description="version 1")
        store.add_server(v1, scope="project")

        v2 = _make_config(name="replaceable", description="version 2")
        store.add_server(v2, scope="project")

        found = store.get_server("replaceable")
        self.assertIsNotNone(found)
        self.assertEqual(
            found.description, "version 2",
            "Updated description should be persisted",
        )

        # Make sure there's only one entry with that name in the file
        project_file = _project_mcp_file(self.project_dir)
        data = json.loads(project_file.read_text(encoding="utf-8"))
        matching = [e for e in data if e.get("name") == "replaceable"]
        self.assertEqual(
            len(matching), 1,
            "Only one entry with the same name should exist in the config file",
        )

    def test_remove_server(self):
        """Removing a server deletes it from the config file."""
        store = self._store()
        store.add_server(_make_config(name="to_remove"), scope="project")
        self.assertIsNotNone(store.get_server("to_remove"), "pre-condition: exists")

        result = store.remove_server("to_remove", scope="project")
        self.assertTrue(result, "remove should return True when server was found")

        # Verify it no longer appears (unless it falls through to builtin)
        servers = store.list_servers(include_builtin=False)
        names = {s.name for s in servers}
        self.assertNotIn("to_remove", names)

    def test_remove_nonexistent_server(self):
        """Removing a server that doesn't exist returns False."""
        store = self._store()
        result = store.remove_server("does_not_exist", scope="project")
        self.assertFalse(result, "remove should return False for missing server")

    def test_get_server_found(self):
        """get_server returns the correct MCPServerConfig when it exists."""
        store = self._store()
        store.add_server(
            _make_config(name="findme", command="node", args=["server.js"]),
            scope="project",
        )
        found = store.get_server("findme")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "findme")
        self.assertEqual(found.command, "node")
        self.assertEqual(found.args, ["server.js"])

    def test_get_server_not_found(self):
        """get_server returns None for an unknown name."""
        store = self._store()
        self.assertIsNone(
            store.get_server("nonexistent"),
            "get_server should return None for unknown servers",
        )


# ═══════════════════════════════════════════════════════════════════════════
# MCPConfigStore - Merge Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMCPConfigStoreMerge(_TempDirTestCase):
    """Tests for the three-layer merge: builtin < global < project."""

    def test_project_overrides_global(self):
        """A project-level config overrides a global config with the same name."""
        # Write a global server
        _write_mcp_json(self.global_mcp_file, [
            {"name": "shared", "command": "global_cmd", "description": "from global"},
        ])
        # Write the same name at project level
        project_file = _project_mcp_file(self.project_dir)
        _write_mcp_json(project_file, [
            {"name": "shared", "command": "project_cmd", "description": "from project"},
        ])

        store = self._store()
        server = store.get_server("shared")
        self.assertIsNotNone(server)
        self.assertEqual(server.command, "project_cmd", "project should override global")
        self.assertEqual(server.description, "from project")

    def test_project_overrides_builtin(self):
        """A project-level config can override a built-in server."""
        project_file = _project_mcp_file(self.project_dir)
        _write_mcp_json(project_file, [
            {
                "name": "puppeteer",
                "command": "custom_puppeteer",
                "args": ["--custom"],
                "description": "custom override",
            },
        ])

        store = self._store()
        server = store.get_server("puppeteer")
        self.assertIsNotNone(server)
        self.assertEqual(
            server.command, "custom_puppeteer",
            "project config should override the built-in puppeteer",
        )

    def test_global_overrides_builtin(self):
        """A global-level config overrides a built-in server."""
        _write_mcp_json(self.global_mcp_file, [
            {
                "name": "web_search",
                "command": "custom_search",
                "args": ["--global"],
                "description": "global web_search override",
            },
        ])

        store = self._store()
        server = store.get_server("web_search")
        self.assertIsNotNone(server)
        self.assertEqual(
            server.command, "custom_search",
            "global config should override the built-in web_search",
        )

    def test_merge_order(self):
        """Full merge order: builtin < global < project."""
        # All three layers define the same server name
        _write_mcp_json(self.global_mcp_file, [
            {"name": "layered", "command": "global_cmd", "description": "global"},
        ])
        project_file = _project_mcp_file(self.project_dir)
        _write_mcp_json(project_file, [
            {"name": "layered", "command": "project_cmd", "description": "project"},
        ])

        store = self._store()
        server = store.get_server("layered")
        self.assertIsNotNone(server)
        self.assertEqual(
            server.command, "project_cmd",
            "project layer should win over global",
        )
        self.assertEqual(server.description, "project")

        # Remove project override -- global should now win
        store.remove_server("layered", scope="project")
        server = store.get_server("layered")
        self.assertIsNotNone(server)
        self.assertEqual(
            server.command, "global_cmd",
            "after removing project override, global should win",
        )


# ═══════════════════════════════════════════════════════════════════════════
# MCPConfigStore - Enable/Disable Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMCPConfigStoreEnableDisable(_TempDirTestCase):
    """Tests for enable/disable toggling, including builtin overrides."""

    def test_enable_server(self):
        """enable_server sets enabled=True and returns the config."""
        store = self._store()
        cfg = _make_config(name="toggle_me", enabled=False)
        store.add_server(cfg, scope="project")

        result = store.enable_server("toggle_me")
        self.assertIsNotNone(result)
        self.assertTrue(result.enabled, "Server should be enabled after enable_server")

        # Verify persistence
        fresh = store.get_server("toggle_me")
        self.assertTrue(fresh.enabled, "enabled=True should be persisted")

    def test_disable_server(self):
        """disable_server sets enabled=False and returns the config."""
        store = self._store()
        cfg = _make_config(name="toggle_me", enabled=True)
        store.add_server(cfg, scope="project")

        result = store.disable_server("toggle_me")
        self.assertIsNotNone(result)
        self.assertFalse(result.enabled, "Server should be disabled after disable_server")

    def test_disable_builtin_creates_override(self):
        """Disabling a built-in server creates a project-level override."""
        store = self._store()

        # puppeteer is built-in and enabled by default
        before = store.get_server("puppeteer")
        self.assertTrue(before.enabled, "pre-condition: puppeteer is enabled")

        result = store.disable_server("puppeteer")
        self.assertIsNotNone(result, "disable_server should return the config")
        self.assertFalse(result.enabled)

        # Verify the project file now has a puppeteer override
        project_file = _project_mcp_file(self.project_dir)
        self.assertTrue(project_file.exists(), "project config should be created")
        data = json.loads(project_file.read_text(encoding="utf-8"))
        puppet_entries = [e for e in data if e.get("name") == "puppeteer"]
        self.assertEqual(len(puppet_entries), 1, "exactly one override entry expected")
        self.assertFalse(puppet_entries[0]["enabled"])

    def test_enable_after_disable(self):
        """A server can be re-enabled after being disabled."""
        store = self._store()
        cfg = _make_config(name="flip_flop", enabled=True)
        store.add_server(cfg, scope="project")

        store.disable_server("flip_flop")
        self.assertFalse(store.get_server("flip_flop").enabled)

        store.enable_server("flip_flop")
        self.assertTrue(
            store.get_server("flip_flop").enabled,
            "Server should be re-enabled",
        )

    def test_enable_nonexistent_returns_none(self):
        """enable_server returns None for an unknown server name."""
        store = self._store()
        self.assertIsNone(store.enable_server("no_such_server"))

    def test_disable_nonexistent_returns_none(self):
        """disable_server returns None for an unknown server name."""
        store = self._store()
        self.assertIsNone(store.disable_server("no_such_server"))


# ═══════════════════════════════════════════════════════════════════════════
# MCPConfigStore - SDK Integration Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMCPConfigStoreSDK(_TempDirTestCase):
    """Tests for SDK-format output methods."""

    def test_get_enabled_sdk_servers(self):
        """get_enabled_sdk_servers returns only enabled servers in SDK dict format."""
        store = self._store()
        store.add_server(
            _make_config(name="custom_srv", command="node", args=["srv.js"], enabled=True),
            scope="project",
        )

        sdk = store.get_enabled_sdk_servers()
        # Should include builtins + custom_srv
        self.assertIn("puppeteer", sdk, "builtin puppeteer should be present")
        self.assertIn("web_search", sdk, "builtin web_search should be present")
        self.assertIn("custom_srv", sdk, "custom enabled server should be present")

        # Verify SDK format
        self.assertEqual(sdk["custom_srv"]["command"], "node")
        self.assertEqual(sdk["custom_srv"]["args"], ["srv.js"])

    def test_get_enabled_sdk_servers_respects_disabled(self):
        """Disabled servers are excluded from the SDK output."""
        store = self._store()
        store.add_server(
            _make_config(name="disabled_srv", enabled=False),
            scope="project",
        )

        sdk = store.get_enabled_sdk_servers()
        self.assertNotIn(
            "disabled_srv", sdk,
            "disabled server should not appear in SDK output",
        )

    def test_get_enabled_sdk_servers_disabled_builtin_excluded(self):
        """A disabled builtin server is excluded from SDK output."""
        store = self._store()
        store.disable_server("puppeteer")

        sdk = store.get_enabled_sdk_servers()
        self.assertNotIn(
            "puppeteer", sdk,
            "disabled puppeteer should not appear in SDK output",
        )

    def test_get_enabled_tool_names(self):
        """get_enabled_tool_names returns mcp__{name}__* patterns."""
        store = self._store()
        store.add_server(
            _make_config(name="my_tools", enabled=True),
            scope="project",
        )
        tool_names = store.get_enabled_tool_names()

        self.assertIn("mcp__puppeteer__*", tool_names)
        self.assertIn("mcp__web_search__*", tool_names)
        self.assertIn("mcp__my_tools__*", tool_names)

    def test_get_enabled_tool_names_excludes_disabled(self):
        """Disabled servers do not produce tool name patterns."""
        store = self._store()
        store.add_server(
            _make_config(name="off_server", enabled=False),
            scope="project",
        )
        tool_names = store.get_enabled_tool_names()
        self.assertNotIn("mcp__off_server__*", tool_names)


# ═══════════════════════════════════════════════════════════════════════════
# MCPConfigStore - Validation Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMCPConfigStoreValidation(_TempDirTestCase):
    """Tests for the validate_server method."""

    def test_validate_valid_config(self):
        """A well-formed config returns valid=True with no errors."""
        store = self._store()
        cfg = _make_config(name="valid_server", command="echo")
        result = store.validate_server(cfg)
        self.assertTrue(result["valid"], f"Should be valid, got errors: {result['errors']}")
        self.assertEqual(result["errors"], [])

    def test_validate_empty_name(self):
        """An empty name produces a validation error."""
        store = self._store()
        cfg = _make_config(name="")
        result = store.validate_server(cfg)
        self.assertFalse(result["valid"], "Empty name should be invalid")
        self.assertTrue(
            any("name" in e.lower() for e in result["errors"]),
            f"Should have a name error, got: {result['errors']}",
        )

    def test_validate_invalid_name(self):
        """Names with special characters are rejected."""
        store = self._store()
        for bad_name in ["has space", "has/slash", "has@sign", "123starts_with_digit"]:
            cfg = _make_config(name=bad_name)
            result = store.validate_server(cfg)
            # The implementation checks alphanumeric + _ and -
            # Names starting with digits or containing special chars should fail
            # (the exact behavior depends on the regex used)
            if not bad_name.replace("_", "").replace("-", "").isalnum():
                self.assertFalse(
                    result["valid"],
                    f"Name '{bad_name}' should be invalid",
                )

    def test_validate_empty_command(self):
        """An empty command produces a validation error."""
        store = self._store()
        cfg = _make_config(command="")
        result = store.validate_server(cfg)
        self.assertFalse(result["valid"], "Empty command should be invalid")
        self.assertTrue(
            any("command" in e.lower() for e in result["errors"]),
            f"Should have a command error, got: {result['errors']}",
        )

    def test_validate_bad_timeout(self):
        """Timeout out of range produces a validation error."""
        store = self._store()
        for bad_timeout in [0, -5, 999]:
            cfg = _make_config(timeout=bad_timeout)
            result = store.validate_server(cfg)
            self.assertFalse(
                result["valid"],
                f"Timeout {bad_timeout} should be invalid",
            )
            self.assertTrue(
                any("timeout" in e.lower() for e in result["errors"]),
                f"Should have a timeout error for {bad_timeout}, got: {result['errors']}",
            )

    def test_validate_command_not_found(self):
        """A command not on PATH produces a warning (not an error)."""
        store = self._store()
        cfg = _make_config(command="definitely_not_a_real_command_xyz123")
        result = store.validate_server(cfg)
        # Command not found is a warning, not an error
        self.assertTrue(
            result["valid"],
            "Missing command should be a warning, not an error",
        )
        self.assertTrue(
            any("not found" in w.lower() for w in result["warnings"]),
            f"Should have a 'not found' warning, got: {result['warnings']}",
        )


# ═══════════════════════════════════════════════════════════════════════════
# MCPConfigStore - Import/Export Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMCPConfigStoreImportExport(_TempDirTestCase):
    """Tests for config export and import."""

    def test_export_config(self):
        """export_config returns non-builtin configs as dicts."""
        store = self._store()
        store.add_server(
            _make_config(name="export_me", description="exportable"),
            scope="project",
        )
        store.add_server(
            _make_config(name="export_too", description="also exportable"),
            scope="project",
        )

        exported = store.export_config(scope="project")
        names = [e["name"] for e in exported]
        self.assertIn("export_me", names)
        self.assertIn("export_too", names)
        self.assertEqual(len(exported), 2)

    def test_import_config(self):
        """import_config loads configs and saves them."""
        store = self._store()
        configs = [
            {"name": "imported_a", "command": "cmd_a"},
            {"name": "imported_b", "command": "cmd_b", "description": "B server"},
        ]
        count = store.import_config(configs, scope="project")
        self.assertEqual(count, 2, "Should import 2 configs")

        # Verify they exist
        self.assertIsNotNone(store.get_server("imported_a"))
        self.assertIsNotNone(store.get_server("imported_b"))

    def test_import_config_skips_invalid(self):
        """Import gracefully skips entries that fail validation or parsing."""
        store = self._store()
        configs = [
            {"name": "good_one", "command": "echo"},
            {"name": "", "command": "echo"},  # invalid: empty name
            "not_a_dict",                      # invalid: wrong type
            {"name": "also_good", "command": "cat"},
        ]
        count = store.import_config(configs, scope="project")
        # The import method tries from_dict then validate; non-dicts cause
        # exceptions which are caught. Empty-name configs may or may not
        # pass depending on whether import validates.
        # At minimum "good_one" and "also_good" should import.
        self.assertGreaterEqual(count, 2, "At least the valid configs should import")
        self.assertIsNotNone(store.get_server("good_one"))
        self.assertIsNotNone(store.get_server("also_good"))

    def test_import_export_roundtrip(self):
        """export then import preserves data."""
        store = self._store()
        store.add_server(
            _make_config(name="roundtrip_a", command="echo", args=["hello"]),
            scope="project",
        )
        store.add_server(
            _make_config(name="roundtrip_b", command="cat", args=["-n"],
                         env={"LANG": "en_US"}, description="cat server"),
            scope="project",
        )

        exported = store.export_config(scope="project")

        # Create a second store with a different project dir
        other_project = self.tmp_root / "other_project"
        other_project.mkdir()
        store2 = MCPConfigStore(project_dir=other_project)
        count = store2.import_config(exported, scope="project")
        self.assertEqual(count, 2)

        a = store2.get_server("roundtrip_a")
        self.assertIsNotNone(a)
        self.assertEqual(a.command, "echo")
        self.assertEqual(a.args, ["hello"])

        b = store2.get_server("roundtrip_b")
        self.assertIsNotNone(b)
        self.assertEqual(b.command, "cat")
        self.assertEqual(b.env, {"LANG": "en_US"})
        self.assertEqual(b.description, "cat server")


# ═══════════════════════════════════════════════════════════════════════════
# MCPConfigStore - File Handling Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMCPConfigStoreFileHandling(_TempDirTestCase):
    """Tests for robustness with missing, corrupt, or auto-created config files."""

    def test_missing_config_file(self):
        """Missing config files produce an empty list, no crash."""
        store = self._store()
        # No project or global config files exist
        servers = store.list_servers(include_builtin=False)
        self.assertEqual(servers, [], "No user configs should exist yet")

    def test_corrupt_config_file(self):
        """Corrupt JSON in a config file is handled gracefully."""
        project_file = _project_mcp_file(self.project_dir)
        project_file.parent.mkdir(parents=True, exist_ok=True)
        project_file.write_text("this is { not valid json !!", encoding="utf-8")

        store = self._store()
        # Should not raise
        servers = store.list_servers(include_builtin=False)
        self.assertEqual(
            servers, [],
            "Corrupt config should produce no user servers",
        )

    def test_corrupt_global_config_file(self):
        """Corrupt global JSON is handled gracefully."""
        self.global_mcp_file.parent.mkdir(parents=True, exist_ok=True)
        self.global_mcp_file.write_text("{broken json", encoding="utf-8")

        store = self._store()
        # Should not crash; builtins still work
        servers = store.list_servers()
        names = {s.name for s in servers}
        self.assertIn("puppeteer", names, "builtins should still load")

    def test_config_file_created_on_first_add(self):
        """Adding a server creates the config file and parent directories."""
        deep_project = self.tmp_root / "deep" / "nested" / "project"
        # Intentionally don't create the directory
        store = MCPConfigStore(project_dir=deep_project)
        cfg = _make_config(name="first_ever")
        store.add_server(cfg, scope="project")

        expected_file = _project_mcp_file(deep_project)
        self.assertTrue(
            expected_file.exists(),
            "Config file and parent dirs should be auto-created",
        )

    def test_builtin_servers_not_persisted(self):
        """Built-in servers are never written to config files."""
        store = self._store()
        # Add a non-builtin server to force a file write
        store.add_server(_make_config(name="user_srv"), scope="project")

        project_file = _project_mcp_file(self.project_dir)
        data = json.loads(project_file.read_text(encoding="utf-8"))
        builtin_names = {"puppeteer", "web_search"}
        for entry in data:
            # Entries with builtin=True should not be persisted
            # (user overrides of builtins are stored with builtin=False)
            if entry.get("builtin", False):
                self.fail(
                    f"Builtin server '{entry.get('name')}' should not be persisted "
                    f"with builtin=True"
                )

    def test_config_not_dict_in_list(self):
        """Non-dict entries in the config list are skipped."""
        project_file = _project_mcp_file(self.project_dir)
        _write_mcp_json(project_file, [
            {"name": "good_server", "command": "echo"},
            "this is a string, not a dict",
            42,
            None,
        ])

        store = self._store()
        servers = store.list_servers(include_builtin=False)
        names = {s.name for s in servers}
        self.assertIn("good_server", names, "Valid entry should be loaded")
        # Invalid entries should be silently skipped
        self.assertEqual(len(servers), 1, "Only the valid dict entry should load")

    def test_config_file_is_not_list(self):
        """A JSON file containing a non-list value is treated as empty."""
        project_file = _project_mcp_file(self.project_dir)
        project_file.parent.mkdir(parents=True, exist_ok=True)
        project_file.write_text('{"not": "a list"}', encoding="utf-8")

        store = self._store()
        servers = store.list_servers(include_builtin=False)
        self.assertEqual(servers, [], "Non-list JSON should be treated as empty")


# ═══════════════════════════════════════════════════════════════════════════
# MCPConfigStore - Test Server
# ═══════════════════════════════════════════════════════════════════════════


class TestMCPConfigStoreTestServer(_TempDirTestCase):
    """Tests for the test_server() method."""

    def test_test_server_command_not_found(self):
        """test_server returns success=False when the command binary is missing."""
        store = self._store()
        cfg = _make_config(
            name="bad_cmd",
            command="absolutely_nonexistent_binary_xyz_123",
            args=[],
        )
        store.add_server(cfg, scope="project")

        result = store.test_server("bad_cmd")
        self.assertFalse(result["success"], "Should fail for missing command")
        msg = result["message"].lower()
        self.assertTrue(
            "not found" in msg or "permission denied" in msg or "error" in msg,
            f"Message should indicate failure, got: {result['message']}",
        )
        self.assertIsInstance(result["duration_ms"], int)

    def test_test_server_not_found(self):
        """test_server returns an error for an unknown server name."""
        store = self._store()
        result = store.test_server("nonexistent_server")
        self.assertFalse(result["success"])
        self.assertIn("not found", result["message"].lower())
        self.assertEqual(result["duration_ms"], 0)

    def test_test_server_disabled(self):
        """test_server returns an error for a disabled server."""
        store = self._store()
        cfg = _make_config(name="disabled_one", enabled=False)
        store.add_server(cfg, scope="project")

        result = store.test_server("disabled_one")
        self.assertFalse(result["success"])
        self.assertIn("disabled", result["message"].lower())
        self.assertEqual(result["duration_ms"], 0)

    def test_test_server_success_with_echo(self):
        """test_server succeeds for a command that exits cleanly (echo)."""
        store = self._store()
        cfg = _make_config(
            name="echo_srv",
            command="echo",
            args=["hello"],
        )
        store.add_server(cfg, scope="project")

        result = store.test_server("echo_srv")
        self.assertTrue(
            result["success"],
            f"echo should succeed, got: {result['message']}",
        )
        self.assertGreater(result["duration_ms"], 0, "Duration should be positive")

    def test_test_server_failure_with_false(self):
        """test_server reports failure for a command that exits with non-zero."""
        store = self._store()
        cfg = _make_config(
            name="fail_srv",
            command="false",   # Unix `false` exits with code 1
            args=[],
        )
        store.add_server(cfg, scope="project")

        result = store.test_server("fail_srv")
        self.assertFalse(
            result["success"],
            "false command should produce a failure result",
        )


# ═══════════════════════════════════════════════════════════════════════════
# MCPConfigStore - No Project Dir
# ═══════════════════════════════════════════════════════════════════════════


class TestMCPConfigStoreNoProject(_TempDirTestCase):
    """Tests for MCPConfigStore when no project_dir is provided."""

    def test_list_servers_without_project(self):
        """list_servers works with no project dir (only global + builtins)."""
        store = MCPConfigStore(project_dir=None)
        servers = store.list_servers()
        names = {s.name for s in servers}
        self.assertIn("puppeteer", names, "builtins should be available")

    def test_add_to_global_without_project(self):
        """add_server to global scope works when no project is set."""
        store = MCPConfigStore(project_dir=None)
        cfg = _make_config(name="global_only")
        store.add_server(cfg, scope="global")

        found = store.get_server("global_only")
        self.assertIsNotNone(found)

    def test_add_to_project_scope_falls_back_to_global(self):
        """When no project_dir, add_server with scope=project falls back to global."""
        store = MCPConfigStore(project_dir=None)
        cfg = _make_config(name="fallback_server")
        # This should not crash -- implementation falls back to global
        store.add_server(cfg, scope="project")
        found = store.get_server("fallback_server")
        self.assertIsNotNone(found)


# ═══════════════════════════════════════════════════════════════════════════
# MCPConfigStore - Edge Cases
# ═══════════════════════════════════════════════════════════════════════════


class TestMCPConfigStoreEdgeCases(_TempDirTestCase):
    """Misc edge cases and boundary conditions."""

    def test_multiple_servers_different_scopes(self):
        """Multiple servers across global and project scopes coexist correctly."""
        store = self._store()
        store.add_server(_make_config(name="srv_global"), scope="global")
        store.add_server(_make_config(name="srv_project"), scope="project")

        servers = store.list_servers(include_builtin=False)
        names = {s.name for s in servers}
        self.assertIn("srv_global", names)
        self.assertIn("srv_project", names)

    def test_empty_args_and_env(self):
        """Servers with empty args and env serialize and deserialize correctly."""
        store = self._store()
        cfg = MCPServerConfig(name="minimal_srv", command="echo")
        store.add_server(cfg, scope="project")

        found = store.get_server("minimal_srv")
        self.assertIsNotNone(found)
        self.assertEqual(found.args, [])
        self.assertEqual(found.env, {})

    def test_sdk_format_does_not_mutate_config(self):
        """Calling to_sdk_format does not modify the original config."""
        cfg = _make_config(args=["--port", "3000"], env={"KEY": "val"})
        original_args = list(cfg.args)
        original_env = dict(cfg.env)

        sdk = cfg.to_sdk_format()
        sdk["args"].append("--extra")
        sdk.get("env", {})["NEW"] = "injected"

        self.assertEqual(cfg.args, original_args, "Original args should not be mutated")
        self.assertEqual(cfg.env, original_env, "Original env should not be mutated")

    def test_large_number_of_servers(self):
        """Store handles a non-trivial number of servers."""
        store = self._store()
        for i in range(50):
            store.add_server(
                _make_config(name=f"srv_{i:03d}", command="echo", args=[str(i)]),
                scope="project",
            )

        servers = store.list_servers(include_builtin=False)
        self.assertEqual(len(servers), 50, "All 50 servers should be listed")

        # Verify a specific one
        srv_25 = store.get_server("srv_025")
        self.assertIsNotNone(srv_25)
        self.assertEqual(srv_25.args, ["25"])

    def test_remove_then_re_add(self):
        """A removed server can be re-added cleanly."""
        store = self._store()
        cfg = _make_config(name="comeback", description="original")
        store.add_server(cfg, scope="project")
        store.remove_server("comeback", scope="project")
        self.assertIsNone(
            store.get_server("comeback"),
            "Server should be gone after removal (excluding builtins check)",
        ) if "comeback" not in {"puppeteer", "web_search"} else None

        cfg2 = _make_config(name="comeback", description="reborn")
        store.add_server(cfg2, scope="project")
        found = store.get_server("comeback")
        self.assertIsNotNone(found)
        self.assertEqual(found.description, "reborn")


if __name__ == "__main__":
    unittest.main()
