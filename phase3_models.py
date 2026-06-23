"""Phase 3 — Pydantic data models for AI-contextualized outreach pipeline."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class EmailAngle(str, Enum):
    """Outreach angle categories, ordered by priority."""
    PHILANTHROPY = "philanthropy"
    LIFESTYLE = "lifestyle"
    BUSINESS = "business"
    WEALTH = "wealth"
    GENERAL = "general"


class ResearchSource(BaseModel):
    """A single web research source fetched for a prospect."""
    source_type: str = Field(
        description="company_website, linkedin_profile, linkedin_posts, news_article, philanthropy",
    )
    url: str = ""
    title: str = ""
    content_summary: str = Field(
        default="",
        description="Truncated relevant content from the source.",
    )
    fetch_success: bool = False
    error: str = ""


class ContextSignal(BaseModel):
    """A structured insight extracted from research by Claude."""
    signal_type: str = Field(
        description="role_change, company_milestone, philanthropy, lifestyle, achievement, interest",
    )
    headline: str = Field(description="One-line summary of the signal.")
    detail: str = Field(default="", description="Supporting detail.")
    source_url: str = ""
    recency: str = Field(
        default="unknown",
        description="recent (<6mo), moderate (6-24mo), older, unknown",
    )
    confidence: str = Field(
        default="medium",
        description="high, medium, low",
    )


class ResearchContext(BaseModel):
    """Aggregated research output for a single prospect."""
    prospect_id: str
    sources: list[ResearchSource] = Field(default_factory=list)
    signals: list[ContextSignal] = Field(default_factory=list)
    company_summary: str = ""
    role_summary: str = ""
    research_quality_score: int = Field(
        default=0, ge=0, le=100,
        description="0-100 quality score based on source diversity.",
    )
    recommended_angle: EmailAngle = EmailAngle.GENERAL

    @field_validator("research_quality_score", mode="before")
    @classmethod
    def clamp_quality(cls, v):
        v = int(round(float(v)))
        return max(0, min(100, v))


class GeneratedEmail(BaseModel):
    """A personalized cold email draft."""
    subject_line: str
    email_body: str
    angle_used: EmailAngle
    hooks_used: list[str] = Field(default_factory=list)
    word_count: int = 0

    @field_validator("word_count", mode="before")
    @classmethod
    def compute_word_count(cls, v, info):
        if v:
            return int(v)
        body = info.data.get("email_body", "")
        return len(body.split()) if body else 0


class ProspectOutreachResult(BaseModel):
    """Full pipeline result for one prospect."""
    prospect_id: str
    first_name: str = ""
    last_name: str = ""
    email_address: str = ""
    member_tier: str = ""
    propensity_total: int = 0
    linkedin_url: str = ""
    research: Optional[ResearchContext] = None
    email: Optional[GeneratedEmail] = None
    status: str = Field(
        default="pending",
        description="pending, researching, generating, completed, skipped, error",
    )
    skip_reason: str = ""
    error_message: str = ""
    processing_time_seconds: float = 0.0


class Phase3RunSummary(BaseModel):
    """Aggregate statistics for a full Phase 3 run."""
    total_processed: int = 0
    emails_generated: int = 0
    skipped_thin_research: int = 0
    skipped_other: int = 0
    errors: int = 0
    angle_distribution: dict[str, int] = Field(default_factory=dict)
    tier_breakdown: dict[str, dict[str, int]] = Field(default_factory=dict)
    avg_research_quality: float = 0.0
    avg_processing_time: float = 0.0
    estimated_cost_usd: float = 0.0
    runtime_seconds: float = 0.0
