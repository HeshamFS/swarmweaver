"""
Code Intelligence Service
=========================

Advanced code analysis using LSP server data — impact analysis,
unused code detection, dependency graphs, and project health scoring.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class CodeIntelligence:
    """High-level code intelligence built on LSP infrastructure."""

    def __init__(self, lsp_manager: Any):
        """
        Args:
            lsp_manager: LSPManager instance (typed as Any to avoid circular import)
        """
        self._lsp = lsp_manager

    async def impact_analysis(self, file_path: str, line: int, character: int) -> dict:
        """Pre-edit analysis: find all callers/references before changing a symbol.

        Uses LSP find_references + call_hierarchy to build a complete picture
        of what will break if this symbol changes.

        Returns:
            {
                "symbol": "functionName",
                "file": "path/to/file.py",
                "line": 42,
                "references": [{"file": "...", "line": N, "preview": "..."}],
                "callers": [{"name": "...", "file": "...", "line": N}],
                "callees": [{"name": "...", "file": "...", "line": N}],
                "total_references": N,
                "cross_file_references": N,
                "risk_level": "low|medium|high",
            }
        """
        # Get the LSP instance for this file
        instance = self._lsp.get_instance_for_file(Path(file_path))
        if not instance or not instance.client:
            return {"error": "No LSP server available for this file", "file": file_path}

        uri = Path(file_path).as_uri()
        client = instance.client

        # Get hover info for symbol name
        hover = await client.hover(uri, line, character)
        symbol_name = hover.contents[:50] if hover else "unknown"

        # Get all references
        refs = await client.find_references(uri, line, character, include_decl=False)
        ref_list = [
            {"file": r.uri, "line": r.start_line + 1}
            for r in refs
        ]

        # Get call hierarchy
        callers = []
        callees = []
        try:
            items = await client.prepare_call_hierarchy(uri, line, character)
            if items:
                incoming = await client.incoming_calls(items[0])
                callers = [
                    {"name": c.get("from", {}).get("name", "?"),
                     "file": c.get("from", {}).get("uri", ""),
                     "line": c.get("from", {}).get("range", {}).get("start", {}).get("line", 0) + 1}
                    for c in incoming
                ]
                outgoing = await client.outgoing_calls(items[0])
                callees = [
                    {"name": c.get("to", {}).get("name", "?"),
                     "file": c.get("to", {}).get("uri", ""),
                     "line": c.get("to", {}).get("range", {}).get("start", {}).get("line", 0) + 1}
                    for c in outgoing
                ]
        except Exception:
            pass

        # Calculate cross-file references
        source_uri = uri
        cross_file = len([r for r in ref_list if r["file"] != source_uri])

        # Risk assessment
        total_refs = len(ref_list)
        if total_refs > 20 or cross_file > 5:
            risk = "high"
        elif total_refs > 5 or cross_file > 2:
            risk = "medium"
        else:
            risk = "low"

        return {
            "symbol": symbol_name,
            "file": file_path,
            "line": line + 1,
            "references": ref_list[:50],
            "callers": callers[:30],
            "callees": callees[:30],
            "total_references": total_refs,
            "cross_file_references": cross_file,
            "risk_level": risk,
        }

    async def unused_code_detection(self, root_path: str) -> list[dict]:
        """Find symbols with 0 external references (potential dead code).

        Returns list of potentially unused symbols with their locations.
        """
        root = Path(root_path)
        results = []

        # Get all instances
        for instance in self._lsp.get_all_instances():
            if not instance.client or instance.status.value != "ready":
                continue

            # Get workspace symbols
            try:
                symbols = await instance.client.workspace_symbols("")
            except Exception:
                continue

            for sym in symbols[:200]:  # Cap to avoid excessive API calls
                name = sym.get("name", "")
                location = sym.get("location", {})
                uri = location.get("uri", "")
                line = location.get("range", {}).get("start", {}).get("line", 0)
                char = location.get("range", {}).get("start", {}).get("character", 0)

                # Skip private/internal symbols
                if name.startswith("_"):
                    continue

                # Find references
                try:
                    refs = await instance.client.find_references(
                        uri, line, char, include_decl=False
                    )
                    if not refs:
                        results.append({
                            "name": name,
                            "kind": sym.get("kind", 0),
                            "file": uri,
                            "line": line + 1,
                            "references": 0,
                        })
                except Exception:
                    continue

        return results

    async def dependency_graph(self, root_path: str, entry_files: list[str] | None = None) -> dict:
        """Build file-to-file dependency graph via imports and call hierarchy.

        Returns:
            {
                "nodes": [{"file": "...", "symbols": N}],
                "edges": [{"from": "...", "to": "...", "weight": N}],
                "clusters": [["file1", "file2"]],
            }
        """
        root = Path(root_path)
        nodes: dict[str, int] = {}
        edges: dict[tuple[str, str], int] = {}

        for instance in self._lsp.get_all_instances():
            if not instance.client or instance.status.value != "ready":
                continue

            # Get workspace symbols to discover all files
            try:
                symbols = await instance.client.workspace_symbols("")
            except Exception:
                continue

            # Group symbols by file
            file_symbols: dict[str, list[dict]] = {}
            for sym in symbols:
                uri = sym.get("location", {}).get("uri", "")
                if uri:
                    file_symbols.setdefault(uri, []).append(sym)
                    nodes[uri] = len(file_symbols[uri])

            # For each symbol, find references to build edges
            for uri, syms in list(file_symbols.items())[:50]:
                for sym in syms[:10]:
                    loc = sym.get("location", {})
                    line = loc.get("range", {}).get("start", {}).get("line", 0)
                    char = loc.get("range", {}).get("start", {}).get("character", 0)
                    try:
                        refs = await instance.client.find_references(
                            uri, line, char, include_decl=False
                        )
                        for ref in refs:
                            ref_uri = ref.uri
                            if ref_uri != uri:
                                key = (uri, ref_uri)
                                edges[key] = edges.get(key, 0) + 1
                    except Exception:
                        continue

        # Build clusters via Union-Find
        clusters = self._build_clusters(list(nodes.keys()), list(edges.keys()))

        return {
            "nodes": [{"file": f, "symbols": n} for f, n in nodes.items()],
            "edges": [{"from": k[0], "to": k[1], "weight": v} for k, v in edges.items()],
            "clusters": clusters,
        }

    async def complexity_metrics(self, file_path: str) -> dict:
        """Symbol hierarchy depth and nesting analysis for a single file."""
        instance = self._lsp.get_instance_for_file(Path(file_path))
        if not instance or not instance.client:
            return {"error": "No LSP server available", "file": file_path}

        uri = Path(file_path).as_uri()
        try:
            symbols = await instance.client.document_symbols(uri)
        except Exception as e:
            return {"error": str(e), "file": file_path}

        def _count_depth(syms, depth=0):
            max_d = depth
            count = 0
            for s in syms:
                count += 1
                if s.children:
                    child_d, child_c = _count_depth(s.children, depth + 1)
                    max_d = max(max_d, child_d)
                    count += child_c
            return max_d, count

        max_depth, total_symbols = _count_depth(symbols)

        return {
            "file": file_path,
            "total_symbols": total_symbols,
            "max_nesting_depth": max_depth,
            "top_level_symbols": len(symbols),
            "symbols": [
                {"name": s.name, "kind": s.kind, "line": s.range_start_line + 1,
                 "children": len(s.children)}
                for s in symbols
            ],
        }

    async def code_health_score(self) -> dict:
        """Project-wide health score (0-100) based on error/warning ratio.

        Score calculation:
        - Start at 100
        - Each error: -5 points (min 0)
        - Each warning: -1 point (min 0)
        - Bonus: +10 if 0 errors (capped at 100)
        """
        all_diags = self._lsp.get_all_diagnostics()
        errors = sum(1 for d in all_diags if d.get("severity") == 1)
        warnings = sum(1 for d in all_diags if d.get("severity") == 2)
        infos = sum(1 for d in all_diags if d.get("severity") == 3)
        hints = sum(1 for d in all_diags if d.get("severity") == 4)

        score = max(0, 100 - (errors * 5) - (warnings * 1))
        if errors == 0 and score < 100:
            score = min(100, score + 10)

        # Per-language breakdown
        by_language: dict[str, dict] = {}
        for instance in self._lsp.get_all_instances():
            lang = instance.spec.language_id
            lang_diags = [d for uri_diags in instance.diagnostics.values() for d in uri_diags]
            lang_errors = sum(1 for d in lang_diags if d.get("severity") == 1)
            lang_warnings = sum(1 for d in lang_diags if d.get("severity") == 2)
            lang_score = max(0, 100 - (lang_errors * 5) - (lang_warnings * 1))
            by_language[lang] = {
                "score": lang_score,
                "errors": lang_errors,
                "warnings": lang_warnings,
            }

        return {
            "score": score,
            "error_count": errors,
            "warning_count": warnings,
            "info_count": infos,
            "hint_count": hints,
            "total_diagnostics": len(all_diags),
            "by_language": by_language,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    @staticmethod
    def _build_clusters(nodes: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
        """Union-Find clustering of connected files."""
        parent: dict[str, str] = {n: n for n in nodes}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for a, b in edges:
            if a in parent and b in parent:
                union(a, b)

        groups: dict[str, list[str]] = {}
        for n in nodes:
            root = find(n)
            groups.setdefault(root, []).append(n)

        return list(groups.values())
