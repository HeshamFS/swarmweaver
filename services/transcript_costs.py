"""
Transcript Cost Analyzer
==========================

Parses JSONL transcript files produced by Claude Code / Agent SDK sessions
and calculates dollar costs based on token usage and model pricing.
"""

import json
from pathlib import Path
from typing import Optional


class TranscriptCostAnalyzer:
    """
    Analyzes Claude transcript files to compute cost breakdowns by agent,
    model, and token type (input, output, cache_read, cache_creation).

    Costs are per million tokens.
    """

    MODEL_COSTS: dict[str, dict[str, float]] = {
        "opus": {
            "input": 15,
            "output": 75,
            "cache_read": 1.5,
            "cache_creation": 3.75,
        },
        "sonnet": {
            "input": 3,
            "output": 15,
            "cache_read": 0.3,
            "cache_creation": 0.75,
        },
        "haiku": {
            "input": 0.80,
            "output": 4,
            "cache_read": 0.08,
            "cache_creation": 0.20,
        },
    }

    def parse_transcript(self, transcript_path: Path) -> dict:
        """
        Parse a JSONL transcript file and extract token usage per message.

        Returns:
            {
                "messages": int,
                "model": str,
                "agent": str,
                "input_tokens": int,
                "output_tokens": int,
                "cache_read_tokens": int,
                "cache_creation_tokens": int,
            }
        """
        usage: dict = {
            "messages": 0,
            "model": "",
            "agent": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
        }

        if not transcript_path.exists():
            return usage

        try:
            for line in transcript_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Extract model name from entry
                model = entry.get("model", "")
                if model and not usage["model"]:
                    usage["model"] = model

                # Extract agent name
                agent = entry.get("agent_name", "") or entry.get("agent", "")
                if agent and not usage["agent"]:
                    usage["agent"] = agent

                # Extract token usage from the entry
                token_usage = entry.get("usage", {})
                if not token_usage and entry.get("message", {}).get("usage"):
                    token_usage = entry["message"]["usage"]

                if token_usage:
                    usage["messages"] += 1
                    usage["input_tokens"] += token_usage.get("input_tokens", 0)
                    usage["output_tokens"] += token_usage.get("output_tokens", 0)
                    usage["cache_read_tokens"] += token_usage.get(
                        "cache_read_input_tokens",
                        token_usage.get("cache_read_tokens", 0),
                    )
                    usage["cache_creation_tokens"] += token_usage.get(
                        "cache_creation_input_tokens",
                        token_usage.get("cache_creation_tokens", 0),
                    )
        except OSError:
            pass

        return usage

    def calculate_costs(self, usage: dict, model: str = "") -> dict:
        """
        Calculate dollar costs from token usage.

        Args:
            usage: Token usage dict from parse_transcript().
            model: Model name override (if empty, uses usage["model"]).

        Returns:
            {input_cost, output_cost, cache_read_cost, cache_creation_cost, total}
        """
        model_key = self._resolve_model_key(model or usage.get("model", ""))
        rates = self.MODEL_COSTS.get(model_key, self.MODEL_COSTS["sonnet"])

        input_cost = (usage.get("input_tokens", 0) / 1_000_000) * rates["input"]
        output_cost = (usage.get("output_tokens", 0) / 1_000_000) * rates["output"]
        cache_read_cost = (usage.get("cache_read_tokens", 0) / 1_000_000) * rates["cache_read"]
        cache_creation_cost = (usage.get("cache_creation_tokens", 0) / 1_000_000) * rates["cache_creation"]

        return {
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "cache_read_cost": round(cache_read_cost, 6),
            "cache_creation_cost": round(cache_creation_cost, 6),
            "total": round(input_cost + output_cost + cache_read_cost + cache_creation_cost, 6),
            "model_key": model_key,
        }

    def analyze_project_transcripts(self, project_dir: Path) -> dict:
        """
        Analyze all transcript files in a project directory.

        Searches for JSONL files in:
          - .swarmweaver/transcripts/
          - .swarmweaver/logs/
          - .swarm/worker-*/

        Returns:
            {
                total_cost, by_agent, by_model,
                token_breakdown: {input, output, cache_read, cache_creation},
                transcript_count,
            }
        """
        result: dict = {
            "total_cost": 0.0,
            "by_agent": {},
            "by_model": {},
            "token_breakdown": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
            },
            "transcript_count": 0,
        }

        transcript_files = self._find_transcripts(project_dir)
        for tf in transcript_files:
            usage = self.parse_transcript(tf)
            if usage["messages"] == 0:
                continue

            result["transcript_count"] += 1
            costs = self.calculate_costs(usage)

            result["total_cost"] += costs["total"]

            # Aggregate token breakdown
            for key in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"):
                result["token_breakdown"][key] += usage.get(key, 0)

            # By agent (include token breakdown for worker view)
            agent = usage.get("agent") or self._agent_from_path(tf, project_dir) or "unknown"
            if agent not in result["by_agent"]:
                result["by_agent"][agent] = {
                    "cost": 0.0,
                    "messages": 0,
                    "tokens": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                }
            result["by_agent"][agent]["cost"] += costs["total"]
            result["by_agent"][agent]["messages"] += usage["messages"]
            result["by_agent"][agent]["tokens"] += (
                usage["input_tokens"] + usage["output_tokens"]
            )
            result["by_agent"][agent]["input_tokens"] += usage.get("input_tokens", 0)
            result["by_agent"][agent]["output_tokens"] += usage.get("output_tokens", 0)
            result["by_agent"][agent]["cache_read_tokens"] += usage.get("cache_read_tokens", 0)
            result["by_agent"][agent]["cache_creation_tokens"] += usage.get("cache_creation_tokens", 0)

            # By model
            model_key = costs["model_key"]
            if model_key not in result["by_model"]:
                result["by_model"][model_key] = {"cost": 0.0, "messages": 0, "tokens": 0}
            result["by_model"][model_key]["cost"] += costs["total"]
            result["by_model"][model_key]["messages"] += usage["messages"]
            result["by_model"][model_key]["tokens"] += (
                usage["input_tokens"] + usage["output_tokens"]
            )

        result["total_cost"] = round(result["total_cost"], 4)
        for agent_data in result["by_agent"].values():
            agent_data["cost"] = round(agent_data["cost"], 4)
        for model_data in result["by_model"].values():
            model_data["cost"] = round(model_data["cost"], 4)

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_model_key(self, model_name: str) -> str:
        """Map a full model string to a pricing tier key."""
        lower = model_name.lower()
        if "opus" in lower:
            return "opus"
        if "haiku" in lower:
            return "haiku"
        return "sonnet"  # default

    def _agent_from_path(self, transcript_path: Path, project_dir: Path) -> Optional[str]:
        """Infer agent name from path (e.g. worker-1 from .../swarm/worker-1/...)."""
        try:
            rel = transcript_path.relative_to(project_dir)
            for part in rel.parts:
                if part.startswith("worker-") and part[7:].isdigit():
                    return part
        except ValueError:
            pass
        return None

    def _find_transcripts(self, project_dir: Path) -> list[Path]:
        """Find all JSONL transcript files in standard locations."""
        files: list[Path] = []
        search_dirs = [
            project_dir / ".swarmweaver" / "transcripts",
            project_dir / ".swarmweaver" / "logs",
        ]

        # Static Swarm: .swarm/worker-*
        swarm_dir = project_dir / ".swarm"
        if swarm_dir.exists():
            try:
                for child in swarm_dir.iterdir():
                    if child.is_dir() and child.name.startswith("worker-"):
                        search_dirs.append(child / ".swarmweaver" / "transcripts")
                        search_dirs.append(child / ".swarmweaver" / "logs")
            except OSError:
                pass

        # Smart Swarm: .swarmweaver/swarm/worker-*
        smart_swarm_dir = project_dir / ".swarmweaver" / "swarm"
        if smart_swarm_dir.exists():
            try:
                for child in smart_swarm_dir.iterdir():
                    if child.is_dir() and child.name.startswith("worker-"):
                        search_dirs.append(child / ".swarmweaver" / "transcripts")
                        search_dirs.append(child / ".swarmweaver" / "logs")
            except OSError:
                pass

        for d in search_dirs:
            if not d.exists():
                continue
            try:
                for f in d.rglob("*.jsonl"):
                    files.append(f)
                for f in d.rglob("*.ndjson"):
                    files.append(f)
            except OSError:
                pass

        return files
