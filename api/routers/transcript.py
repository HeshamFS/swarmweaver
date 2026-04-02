"""Session transcript API endpoints."""

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/api/transcripts")
async def list_transcripts(
    path: str = Query(..., description="Project directory path"),
):
    """List all session transcripts for a project."""
    from services.transcript import TranscriptReader
    sessions = TranscriptReader.list_sessions(Path(path))
    return {"sessions": sessions}


@router.get("/api/transcripts/{session_id}")
async def get_transcript(
    session_id: str,
    path: str = Query(..., description="Project directory path"),
):
    """Get a specific session transcript."""
    from services.transcript import TranscriptReader
    transcript_path = Path(path) / ".swarmweaver" / "transcripts" / f"{session_id}.jsonl"
    if not transcript_path.exists():
        # Try global
        transcript_path = Path.home() / ".swarmweaver" / "transcripts" / f"{session_id}.jsonl"

    entries = TranscriptReader.load_transcript(transcript_path)
    info = TranscriptReader.detect_interruption(entries)

    return {
        "session_id": session_id,
        "entries": entries[-100:],  # Last 100 entries
        "total_entries": len(entries),
        "interruption": info,
    }


@router.get("/api/transcripts/{session_id}/resume-context")
async def get_resume_context(
    session_id: str,
    path: str = Query(..., description="Project directory path"),
):
    """Get the resume context for a session (for injecting into new session prompt)."""
    from services.transcript import TranscriptReader
    transcript_path = Path(path) / ".swarmweaver" / "transcripts" / f"{session_id}.jsonl"
    if not transcript_path.exists():
        transcript_path = Path.home() / ".swarmweaver" / "transcripts" / f"{session_id}.jsonl"

    entries = TranscriptReader.load_transcript(transcript_path)
    context = TranscriptReader.build_resume_context(entries)
    info = TranscriptReader.detect_interruption(entries)

    return {
        "session_id": session_id,
        "resume_context": context,
        "interruption": info,
    }
