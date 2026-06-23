"""Phase 3 — EmailGenerator: angle selection + Claude email generation."""

import json
import logging

import anthropic

from phase3_models import EmailAngle, GeneratedEmail, ResearchContext
from phase3_prompts import EMAIL_GENERATION_PROMPT
from phase3_research import TokenBucketRateLimiter, _safe_str, _extract_json

log = logging.getLogger(__name__)


def format_signals(context: ResearchContext) -> str:
    """Format context signals into readable text for the prompt."""
    if not context.signals:
        return "No specific signals extracted."
    lines = []
    for i, sig in enumerate(context.signals, 1):
        line = f"{i}. [{sig.signal_type.upper()}] {sig.headline}"
        if sig.detail:
            line += f"\n   Detail: {sig.detail}"
        line += f"\n   Recency: {sig.recency} | Confidence: {sig.confidence}"
        lines.append(line)
    return "\n".join(lines)


def compute_angle(row: dict, context: ResearchContext) -> EmailAngle:
    """Determine outreach angle via code-enforced rules (takes precedence over Claude).

    Priority:
    1. Strong philanthropy signals (Board Member=Y + philanthropy source) → philanthropy
    2. Aircraft/Boat Owner or lifestyle signals → lifestyle
    3. Recent business milestone or C-Suite/Founder seniority → business
    4. High wealth indicators (Net Worth Rating >= 10) → wealth
    5. Fallback → general
    """
    board = _safe_str(row.get("Board Member")).upper() == "Y"
    aircraft = _safe_str(row.get("Aircraft Owner")).upper() == "Y"
    boat = _safe_str(row.get("Boat Owner")).upper() == "Y"
    seniority = _safe_str(row.get("Title_Seniority_Label"))
    nw_rating = 0
    try:
        nw_rating = int(_safe_str(row.get("Net Worth Rating")) or "0")
    except ValueError:
        pass

    signal_types = {s.signal_type for s in context.signals}
    has_philanthropy_signal = "philanthropy" in signal_types
    has_lifestyle_signal = "lifestyle" in signal_types
    has_business_signal = "company_milestone" in signal_types or "achievement" in signal_types

    # Rule 1: Philanthropy
    if board and has_philanthropy_signal:
        return EmailAngle.PHILANTHROPY
    if board and any(
        s.source_type == "philanthropy" and s.fetch_success
        for s in context.sources
    ):
        return EmailAngle.PHILANTHROPY

    # Rule 2: Lifestyle
    if aircraft or boat or has_lifestyle_signal:
        return EmailAngle.LIFESTYLE

    # Rule 3: Business
    if has_business_signal or seniority in ("C-Suite", "Founder/Owner"):
        return EmailAngle.BUSINESS

    # Rule 4: Wealth
    if nw_rating >= 10:
        return EmailAngle.WEALTH

    # Rule 5: Fallback — use Claude's recommendation if available
    if context.recommended_angle != EmailAngle.GENERAL:
        return context.recommended_angle

    return EmailAngle.GENERAL


class EmailGenerator:
    """Generates personalized cold emails using Claude."""

    def __init__(
        self,
        claude_client: anthropic.AsyncAnthropic,
        rate_limiter: TokenBucketRateLimiter,
        model: str = "claude-sonnet-4-6",
    ):
        self._claude = claude_client
        self._rl = rate_limiter
        self._model = model

    async def generate_email(
        self, row: dict, context: ResearchContext, angle: EmailAngle
    ) -> GeneratedEmail:
        """Generate a personalized email using Claude."""
        signals_text = format_signals(context)
        prompt = EMAIL_GENERATION_PROMPT.format(
            first_name=_safe_str(row.get("First Name")),
            last_name=_safe_str(row.get("Last Name")),
            linkedin_title=_safe_str(row.get("LinkedIn_Title")),
            company=_safe_str(row.get("Business name")),
            city=_safe_str(row.get("City")),
            state=_safe_str(row.get("State")),
            member_tier=_safe_str(row.get("Member_Tier")),
            signals_text=signals_text,
            company_summary=context.company_summary,
            role_summary=context.role_summary,
            angle=angle.value,
        )

        parsed = None
        for attempt in range(2):
            await self._rl.acquire()
            message = await self._claude.messages.create(
                model=self._model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            try:
                parsed = _extract_json(raw)
                break
            except (json.JSONDecodeError, ValueError):
                if attempt == 0:
                    log.warning("Email JSON parse failed, retrying...")
                    continue
                raise

        body = parsed.get("email_body", "")
        return GeneratedEmail(
            subject_line=parsed.get("subject_line", ""),
            email_body=body,
            angle_used=angle,
            hooks_used=parsed.get("hooks_used", []),
            word_count=len(body.split()) if body else 0,
        )


class ClaudeCodeEmailGenerator:
    """Generates personalized cold emails using claude -p CLI."""

    def __init__(self, client):
        """Initialize with a ClaudeCodeClient instance."""
        self._client = client

    async def generate_email(
        self, row: dict, context: ResearchContext, angle: EmailAngle
    ) -> GeneratedEmail:
        """Generate a personalized email using claude -p (no tools)."""
        signals_text = format_signals(context)
        prompt = EMAIL_GENERATION_PROMPT.format(
            first_name=_safe_str(row.get("First Name")),
            last_name=_safe_str(row.get("Last Name")),
            linkedin_title=_safe_str(row.get("LinkedIn_Title")),
            company=_safe_str(row.get("Business name")),
            city=_safe_str(row.get("City")),
            state=_safe_str(row.get("State")),
            member_tier=_safe_str(row.get("Member_Tier")),
            signals_text=signals_text,
            company_summary=context.company_summary,
            role_summary=context.role_summary,
            angle=angle.value,
        )

        parsed = None
        for attempt in range(2):
            raw = await self._client.generate(prompt)
            try:
                parsed = _extract_json(raw)
                break
            except (json.JSONDecodeError, ValueError):
                if attempt == 0:
                    log.warning("Email JSON parse failed (claude-code), retrying...")
                    continue
                raise

        body = parsed.get("email_body", "")
        return GeneratedEmail(
            subject_line=parsed.get("subject_line", ""),
            email_body=body,
            angle_used=angle,
            hooks_used=parsed.get("hooks_used", []),
            word_count=len(body.split()) if body else 0,
        )
