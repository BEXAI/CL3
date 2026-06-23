"""Pydantic data models for HNWI LinkedIn agentic enrichment."""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class AgentValidationResult(BaseModel):
    """Structured output from the LLM evaluator after cross-referencing
    search results against the original candidate record."""

    linkedin_url: Optional[str] = Field(
        default=None,
        description="Verified LinkedIn profile URL. Only populated when confidence >= 90.",
    )
    confidence_score: int = Field(
        default=0,
        ge=0,
        le=100,
        description="0-100 confidence that the LinkedIn profile matches the candidate.",
    )

    @field_validator("confidence_score", mode="before")
    @classmethod
    def clamp_confidence(cls, v):
        """Round floats and clamp to 0-100."""
        v = int(round(float(v)))
        return max(0, min(100, v))

    matched_criteria: List[str] = Field(
        default_factory=list,
        description="List of input fields that positively matched (e.g. 'Business Name', 'City').",
    )
    discrepancies_found: List[str] = Field(
        default_factory=list,
        description="List of conflicts between the input record and search results.",
    )
    justification: str = Field(
        default="",
        description="Free-text explanation of the confidence score and match decision.",
    )
