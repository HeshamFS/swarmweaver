"""
JSON Schemas and Pydantic Models for Autonomous Coding Agent
=============================================================

Defines structured output schemas for reliable progress tracking
using the Claude Agent SDK's structured outputs feature.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class FeatureCompletionReport(BaseModel):
    """Structured report for a completed feature implementation."""
    task_id: str = Field(description="ID of the task in task_list.json")
    feature_description: str = Field(description="Brief description of the feature")
    status: Literal["passed", "failed", "skipped"] = Field(description="Test result status")
    test_steps_completed: list[str] = Field(default_factory=list, description="Steps that were verified")
    issues_found: list[str] = Field(default_factory=list, description="Any issues discovered")
    next_recommended_feature: Optional[int] = Field(default=None, description="Suggested next feature to implement")


class SessionSummary(BaseModel):
    """Summary of a coding session's accomplishments."""
    features_attempted: int = Field(description="Number of features worked on")
    features_passed: int = Field(description="Number of features marked as passing")
    features_failed: int = Field(description="Number of features that failed testing")
    blockers: list[str] = Field(default_factory=list, description="Any blocking issues encountered")
    recommendations: list[str] = Field(default_factory=list, description="Recommendations for next session")


# JSON Schema for Claude Agent SDK structured outputs
FEATURE_COMPLETION_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {
            "type": "string",
            "description": "ID of the task in task_list.json"
        },
        "feature_description": {
            "type": "string",
            "description": "Brief description of the feature"
        },
        "status": {
            "type": "string",
            "enum": ["passed", "failed", "skipped"],
            "description": "Test result status"
        },
        "test_steps_completed": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Steps that were verified"
        },
        "issues_found": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Any issues discovered"
        },
        "next_recommended_feature": {
            "type": ["integer", "null"],
            "description": "Suggested next feature to implement"
        }
    },
    "required": ["feature_index", "status"],
    "additionalProperties": False
}


SESSION_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "features_attempted": {
            "type": "integer",
            "description": "Number of features worked on"
        },
        "features_passed": {
            "type": "integer",
            "description": "Number of features marked as passing"
        },
        "features_failed": {
            "type": "integer",
            "description": "Number of features that failed testing"
        },
        "blockers": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Any blocking issues encountered"
        },
        "recommendations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Recommendations for next session"
        }
    },
    "required": ["features_attempted", "features_passed", "features_failed"],
    "additionalProperties": False
}
