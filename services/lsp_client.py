"""Pure async JSON-RPC 2.0 client over stdio for LSP communication.

No external dependencies -- uses asyncio.subprocess + Content-Length framing.
Provides typed dataclass results for all LSP operations.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

_SEVERITY_LABELS = {1: "error", 2: "warning", 3: "information", 4: "hint"}


@dataclass
class Location:
    """A location inside a resource (file URI + line/column range)."""

    uri: str
    start_line: int
    start_character: int
    end_line: int
    end_character: int

    @classmethod
    def from_lsp(cls, raw: dict[str, Any]) -> Location:
        """Build from an LSP ``Location`` object."""
        rng = raw["range"]
        return cls(
            uri=raw["uri"],
            start_line=rng["start"]["line"],
            start_character=rng["start"]["character"],
            end_line=rng["end"]["line"],
            end_character=rng["end"]["character"],
        )


@dataclass
class Diagnostic:
    """A single diagnostic (error/warning) reported by the language server."""

    uri: str
    message: str
    severity: int = 1
    start_line: int = 0
    start_character: int = 0
    end_line: int = 0
    end_character: int = 0
    source: str = ""
    code: str | int | None = None

    @property
    def severity_label(self) -> str:
        """Human-readable severity label."""
        return _SEVERITY_LABELS.get(self.severity, "unknown")

    @classmethod
    def from_lsp(cls, uri: str, raw: dict[str, Any]) -> Diagnostic:
        rng = raw.get("range", {})
        start = rng.get("start", {})
        end = rng.get("end", {})
        return cls(
            uri=uri,
            message=raw.get("message", ""),
            severity=raw.get("severity", 1),
            start_line=start.get("line", 0),
            start_character=start.get("character", 0),
            end_line=end.get("line", 0),
            end_character=end.get("character", 0),
            source=raw.get("source", ""),
            code=raw.get("code"),
        )


@dataclass
class DiagnosticReport:
    """Aggregated diagnostics for a document URI."""

    uri: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    version: int | None = None

    @property
    def error_count(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == 1)

    @property
    def warning_count(self) -> int:
        return sum(1 for d in self.diagnostics if d.severity == 2)


@dataclass
class HoverResult:
    """Result of a textDocument/hover request."""

    contents: str
    start_line: int = 0
    start_character: int = 0
    end_line: int = 0
    end_character: int = 0

    @classmethod
    def from_lsp(cls, raw: dict[str, Any] | None) -> HoverResult | None:
        if raw is None:
            return None
        contents = raw.get("contents", "")
        if isinstance(contents, dict):
            contents = contents.get("value", str(contents))
        elif isinstance(contents, list):
            parts = []
            for part in contents:
                parts.append(part.get("value", str(part)) if isinstance(part, dict) else str(part))
            contents = "\n".join(parts)
        rng = raw.get("range", {})
        start = rng.get("start", {})
        end = rng.get("end", {})
        return cls(
            contents=str(contents),
            start_line=start.get("line", 0),
            start_character=start.get("character", 0),
            end_line=end.get("line", 0),
            end_character=end.get("character", 0),
        )


@dataclass
class DocumentSymbol:
    """A symbol found in a document (function, class, variable, etc.)."""

    name: str
    kind: int
    uri: str = ""
    start_line: int = 0
    start_character: int = 0
    end_line: int = 0
    end_character: int = 0
    detail: str = ""
    children: list[DocumentSymbol] = field(default_factory=list)

    @classmethod
    def from_lsp(cls, raw: dict[str, Any], uri: str = "") -> DocumentSymbol:
        rng = raw.get("range", raw.get("location", {}).get("range", {}))
        start = rng.get("start", {})
        end = rng.get("end", {})
        # Workspace symbols carry a "location" with a uri
        loc_uri = raw.get("location", {}).get("uri", uri)
        children_raw = raw.get("children", [])
        return cls(
            name=raw.get("name", ""),
            kind=raw.get("kind", 0),
            uri=loc_uri,
            start_line=start.get("line", 0),
            start_character=start.get("character", 0),
            end_line=end.get("line", 0),
            end_character=end.get("character", 0),
            detail=raw.get("detail", ""),
            children=[cls.from_lsp(c, uri=loc_uri) for c in children_raw],
        )


@dataclass
class CallHierarchyItem:
    """An item in the call hierarchy (incoming or outgoing call)."""

    name: str
    kind: int
    uri: str
    start_line: int = 0
    start_character: int = 0
    end_line: int = 0
    end_character: int = 0
    detail: str = ""
    call_ranges: list[dict[str, int]] = field(default_factory=list)

    @classmethod
    def from_lsp(cls, raw: dict[str, Any]) -> CallHierarchyItem:
        """Build from an LSP ``CallHierarchyIncomingCall`` or ``OutgoingCall``.

        Both wrappers carry a nested item (``from`` / ``to``) plus ``fromRanges``.
        """
        # Unwrap incoming / outgoing call wrappers
        item = raw.get("from") or raw.get("to") or raw
        rng = item.get("range", {})
        start = rng.get("start", {})
        end = rng.get("end", {})
        call_ranges: list[dict[str, int]] = []
        for cr in raw.get("fromRanges", []):
            call_ranges.append(
                {
                    "start_line": cr.get("start", {}).get("line", 0),
                    "start_character": cr.get("start", {}).get("character", 0),
                    "end_line": cr.get("end", {}).get("line", 0),
                    "end_character": cr.get("end", {}).get("character", 0),
                }
            )
        return cls(
            name=item.get("name", ""),
            kind=item.get("kind", 0),
            uri=item.get("uri", ""),
            start_line=start.get("line", 0),
            start_character=start.get("character", 0),
            end_line=end.get("line", 0),
            end_character=end.get("character", 0),
            detail=item.get("detail", ""),
            call_ranges=call_ranges,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_document_identifier(uri: str) -> dict[str, str]:
    return {"uri": uri}


def _text_document_position(uri: str, line: int, character: int) -> dict[str, Any]:
    return {
        "textDocument": _text_document_identifier(uri),
        "position": {"line": line, "character": character},
    }


def _encode_message(body: bytes) -> bytes:
    """Wrap a JSON-RPC body with Content-Length framing."""
    header = f"Content-Length: {len(body)}\r\n\r\n"
    return header.encode("ascii") + body


# ---------------------------------------------------------------------------
# LSPClient
# ---------------------------------------------------------------------------


class LSPClient:
    """Async JSON-RPC 2.0 client that communicates with an LSP server over stdio.

    Args:
        process: An ``asyncio.subprocess.Process`` whose stdin/stdout are the
            LSP server's stdio transport.
        root_uri: The workspace root URI (``file:///path/to/project``).
        timeout_s: Default timeout in seconds for request/response round-trips.
        on_diagnostics: Optional async callback invoked with a
            ``DiagnosticReport`` whenever ``textDocument/publishDiagnostics``
            is received from the server.
    """

    def __init__(
        self,
        process: asyncio.subprocess.Process,
        root_uri: str,
        timeout_s: float = 10.0,
        on_diagnostics: Callable[[DiagnosticReport], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self._process = process
        self._root_uri = root_uri
        self._timeout_s = timeout_s
        self._on_diagnostics = on_diagnostics

        # Request ID counter -- thread-safe via itertools.count()
        self._id_counter = itertools.count(1)

        # Pending request futures keyed by request ID
        self._pending: dict[int, asyncio.Future[Any]] = {}

        # Latest diagnostics per URI
        self._diagnostics: dict[str, DiagnosticReport] = {}

        # Background reader task
        self._reader_task: asyncio.Task[None] | None = None

        # Server capabilities returned by ``initialize``
        self.server_capabilities: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> dict[str, Any]:
        """Send the ``initialize`` request and ``initialized`` notification.

        Returns the full ``InitializeResult`` from the server.
        """
        self._reader_task = asyncio.create_task(self._reader_loop(), name="lsp-reader")

        result = await self._send_request(
            "initialize",
            {
                "processId": None,
                "rootUri": self._root_uri,
                "capabilities": {
                    "textDocument": {
                        "synchronization": {"dynamicRegistration": False, "didSave": True},
                        "completion": {"completionItem": {"snippetSupport": False}},
                        "hover": {"contentFormat": ["plaintext", "markdown"]},
                        "definition": {"dynamicRegistration": False},
                        "implementation": {"dynamicRegistration": False},
                        "references": {"dynamicRegistration": False},
                        "documentSymbol": {"dynamicRegistration": False},
                        "codeAction": {"dynamicRegistration": False},
                        "formatting": {"dynamicRegistration": False},
                        "rename": {"dynamicRegistration": False, "prepareSupport": True},
                        "signatureHelp": {"dynamicRegistration": False},
                        "callHierarchy": {"dynamicRegistration": False},
                        "publishDiagnostics": {"relatedInformation": True},
                    },
                    "workspace": {
                        "symbol": {"dynamicRegistration": False},
                        "workspaceFolders": True,
                    },
                },
                "workspaceFolders": [{"uri": self._root_uri, "name": "root"}],
            },
        )
        self.server_capabilities = result.get("capabilities", {})
        await self._send_notification("initialized", {})
        return result

    async def shutdown(self) -> None:
        """Gracefully shut down the language server and clean up resources."""
        try:
            await self._send_request("shutdown", None)
            await self._send_notification("exit", None)
        except Exception:
            logger.debug("LSP shutdown handshake failed; terminating process", exc_info=True)

        # Cancel the reader loop
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        # Terminate and reap the process
        if self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()

        # Cancel any remaining pending futures
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    # ------------------------------------------------------------------
    # Document synchronization
    # ------------------------------------------------------------------

    async def did_open(self, uri: str, language_id: str, version: int, text: str) -> None:
        """Notify the server that a document has been opened."""
        await self._send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": language_id,
                    "version": version,
                    "text": text,
                }
            },
        )

    async def did_change(self, uri: str, version: int, text: str) -> None:
        """Notify the server that a document has changed (full sync)."""
        await self._send_notification(
            "textDocument/didChange",
            {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": [{"text": text}],
            },
        )

    async def did_save(self, uri: str, text: str | None = None) -> None:
        """Notify the server that a document has been saved."""
        params: dict[str, Any] = {"textDocument": _text_document_identifier(uri)}
        if text is not None:
            params["text"] = text
        await self._send_notification("textDocument/didSave", params)

    async def did_close(self, uri: str) -> None:
        """Notify the server that a document has been closed."""
        await self._send_notification(
            "textDocument/didClose",
            {"textDocument": _text_document_identifier(uri)},
        )

    # ------------------------------------------------------------------
    # Code intelligence
    # ------------------------------------------------------------------

    async def go_to_definition(self, uri: str, line: int, character: int) -> list[Location]:
        """Get definition location(s) for the symbol at the given position."""
        result = await self._send_request(
            "textDocument/definition",
            _text_document_position(uri, line, character),
        )
        return self._parse_locations(result)

    async def go_to_implementation(self, uri: str, line: int, character: int) -> list[Location]:
        """Get implementation location(s) for the symbol at the given position."""
        result = await self._send_request(
            "textDocument/implementation",
            _text_document_position(uri, line, character),
        )
        return self._parse_locations(result)

    async def find_references(
        self, uri: str, line: int, character: int, *, include_declaration: bool = True
    ) -> list[Location]:
        """Find all references to the symbol at the given position."""
        params = _text_document_position(uri, line, character)
        params["context"] = {"includeDeclaration": include_declaration}
        result = await self._send_request("textDocument/references", params)
        return self._parse_locations(result)

    async def hover(self, uri: str, line: int, character: int) -> HoverResult | None:
        """Get hover information for the symbol at the given position."""
        result = await self._send_request(
            "textDocument/hover",
            _text_document_position(uri, line, character),
        )
        return HoverResult.from_lsp(result)

    async def document_symbols(self, uri: str) -> list[DocumentSymbol]:
        """Get all symbols in a document."""
        result = await self._send_request(
            "textDocument/documentSymbol",
            {"textDocument": _text_document_identifier(uri)},
        )
        if not result:
            return []
        return [DocumentSymbol.from_lsp(s, uri=uri) for s in result]

    async def workspace_symbols(self, query: str = "") -> list[DocumentSymbol]:
        """Search for symbols across the entire workspace."""
        result = await self._send_request("workspace/symbol", {"query": query})
        if not result:
            return []
        return [DocumentSymbol.from_lsp(s) for s in result]

    async def completion(self, uri: str, line: int, character: int) -> list[dict[str, Any]]:
        """Get completion items at the given position.

        Returns raw completion items as dicts to preserve server-specific fields.
        """
        result = await self._send_request(
            "textDocument/completion",
            _text_document_position(uri, line, character),
        )
        if result is None:
            return []
        # Result may be a CompletionList or a plain list
        if isinstance(result, dict):
            return result.get("items", [])
        return result if isinstance(result, list) else []

    async def signature_help(self, uri: str, line: int, character: int) -> dict[str, Any] | None:
        """Get signature help at the given position.

        Returns the raw ``SignatureHelp`` object, or ``None``.
        """
        return await self._send_request(
            "textDocument/signatureHelp",
            _text_document_position(uri, line, character),
        )

    async def code_actions(
        self,
        uri: str,
        start_line: int,
        start_character: int,
        end_line: int,
        end_character: int,
        diagnostics: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Request code actions for the given range.

        Returns raw code-action dicts to preserve server-specific fields.
        """
        result = await self._send_request(
            "textDocument/codeAction",
            {
                "textDocument": _text_document_identifier(uri),
                "range": {
                    "start": {"line": start_line, "character": start_character},
                    "end": {"line": end_line, "character": end_character},
                },
                "context": {"diagnostics": diagnostics or []},
            },
        )
        return result if isinstance(result, list) else []

    async def formatting(
        self,
        uri: str,
        *,
        tab_size: int = 4,
        insert_spaces: bool = True,
    ) -> list[dict[str, Any]]:
        """Format an entire document.  Returns a list of ``TextEdit`` dicts."""
        result = await self._send_request(
            "textDocument/formatting",
            {
                "textDocument": _text_document_identifier(uri),
                "options": {"tabSize": tab_size, "insertSpaces": insert_spaces},
            },
        )
        return result if isinstance(result, list) else []

    async def rename_preview(
        self, uri: str, line: int, character: int, new_name: str
    ) -> dict[str, Any]:
        """Request a workspace edit that renames the symbol at the given position.

        Returns the raw ``WorkspaceEdit`` object.
        """
        params = _text_document_position(uri, line, character)
        params["newName"] = new_name
        result = await self._send_request("textDocument/rename", params)
        return result if isinstance(result, dict) else {}

    async def prepare_call_hierarchy(
        self, uri: str, line: int, character: int
    ) -> list[CallHierarchyItem]:
        """Prepare call hierarchy items at the given position."""
        result = await self._send_request(
            "textDocument/prepareCallHierarchy",
            _text_document_position(uri, line, character),
        )
        if not result:
            return []
        return [CallHierarchyItem.from_lsp(item) for item in result]

    async def incoming_calls(self, item: CallHierarchyItem) -> list[CallHierarchyItem]:
        """Get incoming calls for a call hierarchy item."""
        raw_item = {
            "name": item.name,
            "kind": item.kind,
            "uri": item.uri,
            "range": {
                "start": {"line": item.start_line, "character": item.start_character},
                "end": {"line": item.end_line, "character": item.end_character},
            },
            "selectionRange": {
                "start": {"line": item.start_line, "character": item.start_character},
                "end": {"line": item.end_line, "character": item.end_character},
            },
        }
        result = await self._send_request(
            "callHierarchy/incomingCalls", {"item": raw_item}
        )
        if not result:
            return []
        return [CallHierarchyItem.from_lsp(c) for c in result]

    async def outgoing_calls(self, item: CallHierarchyItem) -> list[CallHierarchyItem]:
        """Get outgoing calls from a call hierarchy item."""
        raw_item = {
            "name": item.name,
            "kind": item.kind,
            "uri": item.uri,
            "range": {
                "start": {"line": item.start_line, "character": item.start_character},
                "end": {"line": item.end_line, "character": item.end_character},
            },
            "selectionRange": {
                "start": {"line": item.start_line, "character": item.start_character},
                "end": {"line": item.end_line, "character": item.end_character},
            },
        }
        result = await self._send_request(
            "callHierarchy/outgoingCalls", {"item": raw_item}
        )
        if not result:
            return []
        return [CallHierarchyItem.from_lsp(c) for c in result]

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def get_diagnostics(self, uri: str) -> DiagnosticReport:
        """Return the latest cached diagnostics for the given URI.

        Diagnostics are populated asynchronously via
        ``textDocument/publishDiagnostics`` notifications from the server.
        """
        return self._diagnostics.get(uri, DiagnosticReport(uri=uri))

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    async def _send_request(self, method: str, params: Any) -> Any:
        """Send a JSON-RPC request and wait for the corresponding response.

        Raises ``asyncio.TimeoutError`` if no response arrives within
        ``self._timeout_s`` seconds, and ``RuntimeError`` on JSON-RPC errors.
        """
        req_id = next(self._id_counter)
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params

        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future

        body = json.dumps(message).encode("utf-8")
        assert self._process.stdin is not None  # noqa: S101
        self._process.stdin.write(_encode_message(body))
        await self._process.stdin.drain()

        logger.debug("LSP --> [%d] %s", req_id, method)

        try:
            return await asyncio.wait_for(future, timeout=self._timeout_s)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise asyncio.TimeoutError(
                f"LSP request {method} (id={req_id}) timed out after {self._timeout_s}s"
            )

    async def _send_notification(self, method: str, params: Any) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            message["params"] = params

        body = json.dumps(message).encode("utf-8")
        assert self._process.stdin is not None  # noqa: S101
        self._process.stdin.write(_encode_message(body))
        await self._process.stdin.drain()

        logger.debug("LSP --> (notification) %s", method)

    async def _reader_loop(self) -> None:
        """Background task that reads JSON-RPC messages from the server's stdout.

        Routes responses to their pending futures and handles
        ``textDocument/publishDiagnostics`` notifications via the
        ``on_diagnostics`` callback.
        """
        assert self._process.stdout is not None  # noqa: S101
        reader = self._process.stdout

        try:
            while True:
                # ---- Parse headers (Content-Length framing) ----
                content_length: int | None = None
                while True:
                    raw_line = await reader.readline()
                    if not raw_line:
                        logger.debug("LSP reader: EOF on stdout")
                        return
                    line = raw_line.decode("ascii", errors="replace").strip()
                    if not line:
                        # Empty line terminates the header block
                        break
                    if line.lower().startswith("content-length:"):
                        content_length = int(line.split(":", 1)[1].strip())

                if content_length is None:
                    logger.warning("LSP reader: missing Content-Length header; skipping")
                    continue

                # ---- Read body ----
                body_bytes = await reader.readexactly(content_length)
                try:
                    msg = json.loads(body_bytes)
                except json.JSONDecodeError:
                    logger.warning("LSP reader: invalid JSON body: %s", body_bytes[:200])
                    continue

                # ---- Route ----
                msg_id = msg.get("id")

                if msg_id is not None and msg_id in self._pending:
                    # This is a response to one of our requests
                    future = self._pending.pop(msg_id)
                    if "error" in msg:
                        err = msg["error"]
                        future.set_exception(
                            RuntimeError(
                                f"LSP error {err.get('code', '?')}: {err.get('message', '')}"
                            )
                        )
                    else:
                        future.set_result(msg.get("result"))
                    logger.debug("LSP <-- [%s] response", msg_id)

                elif "method" in msg:
                    # Server-initiated notification or request
                    method = msg["method"]
                    params = msg.get("params", {})
                    logger.debug("LSP <-- (notification) %s", method)

                    if method == "textDocument/publishDiagnostics":
                        await self._handle_diagnostics(params)

                    elif msg_id is not None:
                        # Server request we don't handle -- respond with
                        # MethodNotFound so the server doesn't hang.
                        err_resp = {
                            "jsonrpc": "2.0",
                            "id": msg_id,
                            "error": {"code": -32601, "message": "Method not found"},
                        }
                        err_body = json.dumps(err_resp).encode("utf-8")
                        assert self._process.stdin is not None  # noqa: S101
                        self._process.stdin.write(_encode_message(err_body))
                        await self._process.stdin.drain()

        except asyncio.CancelledError:
            logger.debug("LSP reader loop cancelled")
        except asyncio.IncompleteReadError:
            logger.debug("LSP reader: server closed stdout")
        except Exception:
            logger.exception("LSP reader loop crashed")

    async def _handle_diagnostics(self, params: dict[str, Any]) -> None:
        """Process a ``textDocument/publishDiagnostics`` notification."""
        uri = params.get("uri", "")
        raw_diags = params.get("diagnostics", [])
        report = DiagnosticReport(
            uri=uri,
            diagnostics=[Diagnostic.from_lsp(uri, d) for d in raw_diags],
            version=params.get("version"),
        )
        self._diagnostics[uri] = report

        if self._on_diagnostics is not None:
            try:
                await self._on_diagnostics(report)
            except Exception:
                logger.exception("on_diagnostics callback failed for %s", uri)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_locations(result: Any) -> list[Location]:
        """Normalise a definition/implementation/references result into a list."""
        if result is None:
            return []
        if isinstance(result, dict):
            return [Location.from_lsp(result)]
        if isinstance(result, list):
            return [Location.from_lsp(loc) for loc in result]
        return []
