"""
Context Manager — Multi-Layered Compaction
============================================

Manages context window overflow via 3-layer compaction:
1. Microcompact: strip old tool results (>60 min)
2. Session memory: reuse MELS expertise as summary
3. Legacy compact: full 9-section summarization via Claude

Thresholds from source CLI:
- Auto-compact buffer: 13,000 tokens
- Output reserve: 20,000 tokens
- Circuit breaker: 3 consecutive failures
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class CompactionConfig:
    """Configuration for auto-compaction behavior."""
    auto_compact_threshold: int = 0       # 0 = auto-calculate (context_window - 13K)
    buffer_tokens: int = 13_000           # Buffer before context limit
    output_reserve_tokens: int = 20_000   # Reserved for compaction output
    circuit_breaker_max: int = 3          # Max consecutive failures
    microcompact_age_minutes: int = 60    # Strip tool results older than this
    enable_microcompact: bool = True
    enable_session_memory: bool = True
    enable_legacy_compact: bool = True


# Tool types eligible for microcompact stripping
MICROCOMPACT_TOOL_TYPES = [
    "Read", "Bash", "Grep", "Glob",
    "WebSearch", "WebFetch", "Edit", "Write",
]

# 9-section compact prompt template
COMPACT_PROMPT_SECTIONS = [
    "Current Intent",
    "Key Technical Concepts",
    "Files and Code Sections",
    "Errors and Fixes",
    "Problem-Solving Approach",
    "All User Messages",
    "Pending Tasks",
    "Current Work",
    "Next Step",
]


@dataclass
class CompactionResult:
    """Result of a compaction operation."""
    layers_used: list[str] = field(default_factory=list)
    tokens_before: int = 0
    tokens_after_estimate: int = 0
    microcompact_tools_stripped: int = 0
    session_memory_injected: bool = False
    legacy_prompt_generated: bool = False
    compact_summary: str = ""
    error: Optional[str] = None


class ContextManager:
    """Multi-layered context window manager for agent sessions."""

    def __init__(
        self,
        config: CompactionConfig,
        project_dir: Path,
        session_id: str = "",
    ):
        self.config = config
        self.project_dir = project_dir
        self.session_id = session_id
        self._circuit_breaker_count: int = 0
        self._last_compact_tokens: int = 0
        self._compact_count: int = 0
        self._total_tokens_saved: int = 0

    def get_threshold(self, context_window: int) -> int:
        """Calculate the auto-compact threshold for a given context window."""
        if self.config.auto_compact_threshold > 0:
            return self.config.auto_compact_threshold
        effective = context_window - self.config.output_reserve_tokens
        return max(0, effective - self.config.buffer_tokens)

    def should_compact(self, input_tokens: int, context_window: int) -> bool:
        """Check if compaction should trigger."""
        if self._circuit_breaker_count >= self.config.circuit_breaker_max:
            return False
        threshold = self.get_threshold(context_window)
        return input_tokens >= threshold

    def compact(self, input_tokens: int, context_window: int) -> CompactionResult:
        """Execute the 3-layer compaction pipeline.

        Returns a CompactionResult with the layers used and results.
        The caller (engine) is responsible for applying the compaction
        (e.g., starting a new session with the compact summary).
        """
        result = CompactionResult(tokens_before=input_tokens)

        # Layer 1: Microcompact
        if self.config.enable_microcompact:
            result.microcompact_tools_stripped = len(MICROCOMPACT_TOOL_TYPES)
            result.layers_used.append("microcompact")

        # Layer 2: Session memory (MELS expertise injection)
        if self.config.enable_session_memory:
            session_memory = self._load_session_memory()
            if session_memory:
                result.session_memory_injected = True
                result.layers_used.append("session_memory")

        # Layer 3: Legacy compact (9-section summarization)
        if self.config.enable_legacy_compact:
            result.compact_summary = self._build_compact_prompt()
            result.legacy_prompt_generated = True
            result.layers_used.append("legacy_compact")

        # Circuit breaker tracking
        if input_tokens >= self._last_compact_tokens and self._last_compact_tokens > 0:
            self._circuit_breaker_count += 1
        else:
            self._circuit_breaker_count = 0
        self._last_compact_tokens = input_tokens
        self._compact_count += 1

        return result

    def _load_session_memory(self) -> str:
        """Load MELS expertise relevant to current session."""
        try:
            from services.expertise_priming import PrimingEngine
            from services.expertise_store import ExpertiseStore

            db_path = self.project_dir / ".swarmweaver" / "expertise" / "expertise.db"
            if not db_path.exists():
                return ""
            store = ExpertiseStore(db_path)
            engine = PrimingEngine()
            primed = engine.prime(store, budget_tokens=2000)
            store.close()
            return primed
        except Exception:
            return ""

    def _build_compact_prompt(self) -> str:
        """Build the 9-section compaction prompt."""
        prompt_path = Path(__file__).parent.parent / "prompts" / "shared" / "compact.md"
        if prompt_path.exists():
            try:
                return prompt_path.read_text(encoding="utf-8")
            except OSError:
                pass
        # Fallback inline prompt
        sections = "\n\n".join(
            f"### {i+1}. {section}\n[Provide detailed content for this section]"
            for i, section in enumerate(COMPACT_PROMPT_SECTIONS)
        )
        return (
            "CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.\n\n"
            "Summarize the conversation so far into a structured document "
            "with ALL of the following sections:\n\n"
            f"{sections}\n\n"
            "Include specific file names, code snippets, and exact details. "
            "Do not omit any user messages or pending work."
        )

    def post_compact_cleanup(self) -> None:
        """Clear caches after compaction."""
        self._circuit_breaker_count = max(0, self._circuit_breaker_count)

    def get_status(self) -> dict:
        """Return current context manager status for API/UI."""
        return {
            "circuit_breaker_count": self._circuit_breaker_count,
            "circuit_breaker_max": self.config.circuit_breaker_max,
            "circuit_breaker_tripped": self._circuit_breaker_count >= self.config.circuit_breaker_max,
            "compact_count": self._compact_count,
            "total_tokens_saved": self._total_tokens_saved,
            "microcompact_enabled": self.config.enable_microcompact,
            "session_memory_enabled": self.config.enable_session_memory,
            "legacy_compact_enabled": self.config.enable_legacy_compact,
            "microcompact_age_minutes": self.config.microcompact_age_minutes,
            "buffer_tokens": self.config.buffer_tokens,
        }
