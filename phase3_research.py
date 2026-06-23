"""Phase 3 — ProspectResearcher: 5-step async web research per prospect."""

import asyncio
import json
import logging
import re
from typing import Optional

import aiohttp
import anthropic

from phase3_models import (
    ContextSignal,
    EmailAngle,
    ResearchContext,
    ResearchSource,
)
from phase3_prompts import CONTEXT_EXTRACTION_PROMPT

log = logging.getLogger(__name__)

# Max content to keep per source (chars) to stay within Claude context
MAX_CONTENT_LENGTH = 3000
# HTTP timeout for direct URL fetches
FETCH_TIMEOUT = aiohttp.ClientTimeout(total=15)
# User-agent for web fetches
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class TokenBucketRateLimiter:
    """Token bucket rate limiter allowing concurrent requests within rate limits."""

    def __init__(self, rate: float = 0.8, max_tokens: int = 1):
        self._rate = rate
        self._max_tokens = max_tokens
        self._tokens = float(max_tokens)
        self._updated_at = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self):
        while True:
            async with self._lock:
                now = asyncio.get_event_loop().time()
                if self._updated_at:
                    self._tokens = min(
                        self._max_tokens,
                        self._tokens + (now - self._updated_at) * self._rate,
                    )
                self._updated_at = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._rate
            await asyncio.sleep(wait)


def _extract_json(raw: str) -> dict:
    """Robustly extract a JSON object from Claude's response."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    # Try direct parse first (fastest path)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Try to find a balanced JSON object
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        candidate = match.group()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        # Try truncating at the last valid closing brace
        for end in range(len(candidate) - 1, 0, -1):
            if candidate[end] == "}":
                try:
                    return json.loads(candidate[: end + 1])
                except json.JSONDecodeError:
                    continue
    raise json.JSONDecodeError("No JSON object found in response", raw, 0)


def _truncate(text: str, max_len: int = MAX_CONTENT_LENGTH) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "... [truncated]"


def _safe_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, float):
        import math
        if math.isnan(val):
            return ""
    return str(val).strip()


def compute_quality_score(sources: list[ResearchSource]) -> int:
    """Score 0-100 based on source diversity."""
    score = 0
    types_found = {s.source_type for s in sources if s.fetch_success}

    if "company_website" in types_found:
        score += 20
    if "linkedin_profile" in types_found:
        score += 20
    if "news_article" in types_found:
        score += 15
    if "linkedin_posts" in types_found:
        score += 15
    if "philanthropy" in types_found:
        score += 10

    # Bonus for content volume
    total_content = sum(
        len(s.content_summary) for s in sources if s.fetch_success
    )
    if total_content > 500:
        score += 10
    if total_content > 1500:
        score += 10

    return min(score, 100)


def compile_research_text(sources: list[ResearchSource]) -> str:
    """Combine all successful sources into a single text block for Claude."""
    sections = []
    for s in sources:
        if s.fetch_success and s.content_summary:
            header = f"[{s.source_type.upper()}]"
            if s.title:
                header += f" {s.title}"
            if s.url:
                header += f" ({s.url})"
            sections.append(f"{header}\n{s.content_summary}")
    return "\n\n---\n\n".join(sections)


class ProspectResearcher:
    """Runs 5-step web research for a prospect using aiohttp + Claude web_search tool."""

    def __init__(
        self,
        claude_client: anthropic.AsyncAnthropic,
        http_session: aiohttp.ClientSession,
        claude_rate_limiter: TokenBucketRateLimiter,
        web_rate_limiter: TokenBucketRateLimiter,
        model: str = "claude-sonnet-4-6",
    ):
        self._claude = claude_client
        self._http = http_session
        self._claude_rl = claude_rate_limiter
        self._web_rl = web_rate_limiter
        self._model = model

    async def research_prospect(self, row: dict) -> ResearchContext:
        """Run all 5 research steps, then contextualize with Claude."""
        prospect_id = _safe_str(row.get("WE Record ID")) or _safe_str(row.get("originalID"))
        first = _safe_str(row.get("First Name"))
        last = _safe_str(row.get("Last Name"))
        company = _safe_str(row.get("Business name"))
        linkedin_url = _safe_str(row.get("LinkedIn_URL"))
        board_member = _safe_str(row.get("Board Member")).upper() == "Y"

        # Run research steps concurrently
        tasks = [
            self._step1_company_website(company),
            self._step2_linkedin_profile(linkedin_url, first, last),
            self._step3_linkedin_activity(first, last, company),
            self._step4_recent_news(first, last, company),
        ]
        if board_member:
            tasks.append(self._step5_philanthropy(first, last))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        sources: list[ResearchSource] = []
        for r in results:
            if isinstance(r, Exception):
                sources.append(ResearchSource(
                    source_type="error", fetch_success=False,
                    error=str(r)[:200],
                ))
            elif isinstance(r, list):
                sources.extend(r)
            elif r is not None:
                sources.append(r)

        # Compute quality score
        quality = compute_quality_score(sources)

        # Build research text for Claude
        research_text = compile_research_text(sources)

        if not research_text.strip():
            return ResearchContext(
                prospect_id=prospect_id,
                sources=sources,
                research_quality_score=quality,
            )

        # Claude context extraction
        context = await self._extract_context(row, sources, research_text, quality, prospect_id)
        return context

    async def _step1_company_website(self, company: str) -> Optional[ResearchSource]:
        """Fetch company website via Claude web search."""
        if not company:
            return ResearchSource(
                source_type="company_website", fetch_success=False,
                error="No company name",
            )
        try:
            await self._web_rl.acquire()
            await self._claude_rl.acquire()
            message = await self._claude.messages.create(
                model=self._model,
                max_tokens=1024,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{
                    "role": "user",
                    "content": f"Find the official website for the company '{company}'. "
                               f"Provide a brief 2-3 sentence summary of what the company does, "
                               f"its industry, and approximate size. Include the URL.",
                }],
            )
            text = self._extract_text_from_response(message)
            return ResearchSource(
                source_type="company_website",
                url=company,
                title=f"Company: {company}",
                content_summary=_truncate(text),
                fetch_success=bool(text),
            )
        except Exception as e:
            return ResearchSource(
                source_type="company_website", fetch_success=False,
                error=str(e)[:200],
            )

    async def _step2_linkedin_profile(
        self, linkedin_url: str, first: str, last: str
    ) -> Optional[ResearchSource]:
        """Fetch LinkedIn profile summary via Claude web search."""
        if not linkedin_url:
            return ResearchSource(
                source_type="linkedin_profile", fetch_success=False,
                error="No LinkedIn URL",
            )
        try:
            await self._web_rl.acquire()
            await self._claude_rl.acquire()
            message = await self._claude.messages.create(
                model=self._model,
                max_tokens=1024,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{
                    "role": "user",
                    "content": f"Look up the LinkedIn profile for {first} {last}: {linkedin_url}. "
                               f"Summarize their current role, company, career highlights, "
                               f"and any notable achievements or board positions mentioned.",
                }],
            )
            text = self._extract_text_from_response(message)
            return ResearchSource(
                source_type="linkedin_profile",
                url=linkedin_url,
                title=f"LinkedIn: {first} {last}",
                content_summary=_truncate(text),
                fetch_success=bool(text),
            )
        except Exception as e:
            return ResearchSource(
                source_type="linkedin_profile", url=linkedin_url,
                fetch_success=False, error=str(e)[:200],
            )

    async def _step3_linkedin_activity(
        self, first: str, last: str, company: str
    ) -> Optional[ResearchSource]:
        """Search for recent LinkedIn posts/articles."""
        if not first or not last:
            return ResearchSource(
                source_type="linkedin_posts", fetch_success=False, error="No name",
            )
        try:
            await self._web_rl.acquire()
            await self._claude_rl.acquire()
            query = f'"{first} {last}"'
            if company:
                query += f' "{company}"'
            query += " LinkedIn post OR article OR interview"
            message = await self._claude.messages.create(
                model=self._model,
                max_tokens=1024,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{
                    "role": "user",
                    "content": f"Search for recent LinkedIn posts, articles, or interviews by {first} {last}"
                               + (f" at {company}" if company else "")
                               + ". Summarize any notable public statements, thought leadership, "
                               "or topics they're passionate about. If nothing is found, say so clearly.",
                }],
            )
            text = self._extract_text_from_response(message)
            has_content = bool(text) and "nothing" not in text.lower()[:50] and "no results" not in text.lower()[:50]
            return ResearchSource(
                source_type="linkedin_posts",
                title=f"LinkedIn activity: {first} {last}",
                content_summary=_truncate(text) if has_content else "",
                fetch_success=has_content,
            )
        except Exception as e:
            return ResearchSource(
                source_type="linkedin_posts", fetch_success=False,
                error=str(e)[:200],
            )

    async def _step4_recent_news(
        self, first: str, last: str, company: str
    ) -> Optional[ResearchSource]:
        """Search for recent press/funding/awards."""
        if not first or not last:
            return ResearchSource(
                source_type="news_article", fetch_success=False, error="No name",
            )
        try:
            await self._web_rl.acquire()
            await self._claude_rl.acquire()
            query_parts = [f'"{first} {last}"']
            if company:
                query_parts.append(f'"{company}"')
            query_parts.append("news OR press OR award OR funding OR appointment")
            message = await self._claude.messages.create(
                model=self._model,
                max_tokens=1024,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{
                    "role": "user",
                    "content": f"Search for recent news about {first} {last}"
                               + (f" at {company}" if company else "")
                               + ". Look for press coverage, awards, funding announcements, "
                               "executive appointments, or notable business milestones. "
                               "Summarize the most relevant findings. If nothing found, say so clearly.",
                }],
            )
            text = self._extract_text_from_response(message)
            has_content = bool(text) and "nothing" not in text.lower()[:50] and "no results" not in text.lower()[:50]
            return ResearchSource(
                source_type="news_article",
                title=f"News: {first} {last}",
                content_summary=_truncate(text) if has_content else "",
                fetch_success=has_content,
            )
        except Exception as e:
            return ResearchSource(
                source_type="news_article", fetch_success=False,
                error=str(e)[:200],
            )

    async def _step5_philanthropy(self, first: str, last: str) -> Optional[ResearchSource]:
        """Search for philanthropy/board/foundation involvement."""
        try:
            await self._web_rl.acquire()
            await self._claude_rl.acquire()
            message = await self._claude.messages.create(
                model=self._model,
                max_tokens=1024,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{
                    "role": "user",
                    "content": f"Search for philanthropic activities, foundation involvement, "
                               f"nonprofit board memberships, or charitable giving by {first} {last}. "
                               f"Summarize any foundations they've started, boards they serve on, "
                               f"or causes they support. If nothing found, say so clearly.",
                }],
            )
            text = self._extract_text_from_response(message)
            has_content = bool(text) and "nothing" not in text.lower()[:50] and "no results" not in text.lower()[:50]
            return ResearchSource(
                source_type="philanthropy",
                title=f"Philanthropy: {first} {last}",
                content_summary=_truncate(text) if has_content else "",
                fetch_success=has_content,
            )
        except Exception as e:
            return ResearchSource(
                source_type="philanthropy", fetch_success=False,
                error=str(e)[:200],
            )

    def _extract_text_from_response(self, message) -> str:
        """Extract text content from a Claude API response that may include tool use."""
        parts = []
        for block in message.content:
            if hasattr(block, "text"):
                parts.append(block.text)
        return "\n".join(parts).strip()

    async def _extract_context(
        self,
        row: dict,
        sources: list[ResearchSource],
        research_text: str,
        quality: int,
        prospect_id: str,
    ) -> ResearchContext:
        """Use Claude to extract structured context from raw research."""
        prompt = CONTEXT_EXTRACTION_PROMPT.format(
            first_name=_safe_str(row.get("First Name")),
            last_name=_safe_str(row.get("Last Name")),
            linkedin_title=_safe_str(row.get("LinkedIn_Title")),
            company=_safe_str(row.get("Business name")),
            city=_safe_str(row.get("City")),
            state=_safe_str(row.get("State")),
            member_tier=_safe_str(row.get("Member_Tier")),
            propensity_total=_safe_str(row.get("Propensity_Total")),
            seniority_label=_safe_str(row.get("Title_Seniority_Label")),
            board_member=_safe_str(row.get("Board Member")),
            aircraft_owner=_safe_str(row.get("Aircraft Owner")),
            boat_owner=_safe_str(row.get("Boat Owner")),
            net_worth_rating=_safe_str(row.get("Net Worth Rating")),
            real_estate_properties=_safe_str(row.get("Real Estate Properties")),
            research_text=research_text,
        )

        parsed = None
        for attempt in range(2):
            await self._claude_rl.acquire()
            messages = [{"role": "user", "content": prompt}]
            if attempt > 0:
                # Retry: remind Claude to output JSON only
                messages.append({"role": "assistant", "content": "{"})
                messages[-1] = {"role": "user", "content": prompt + "\n\nIMPORTANT: Respond with ONLY a valid JSON object. No other text."}
            message = await self._claude.messages.create(
                model=self._model,
                max_tokens=2048,
                messages=messages,
            )
            raw = ""
            for block in message.content:
                if hasattr(block, "text"):
                    raw += block.text
            raw = raw.strip()
            try:
                parsed = _extract_json(raw)
                break
            except (json.JSONDecodeError, ValueError):
                if attempt == 0:
                    log.warning("JSON parse failed for %s, retrying...", prospect_id)
                    continue
                raise

        signals = []
        for s in parsed.get("signals", []):
            try:
                signals.append(ContextSignal(**s))
            except Exception:
                continue

        # Parse recommended angle
        angle_str = parsed.get("recommended_angle", "general").lower()
        try:
            angle = EmailAngle(angle_str)
        except ValueError:
            angle = EmailAngle.GENERAL

        # Adjust quality for signal count and recency
        adjusted_quality = quality
        if len(signals) >= 3:
            adjusted_quality += 10
        if any(s.recency == "recent" for s in signals):
            adjusted_quality += 10
        adjusted_quality = min(adjusted_quality, 100)

        return ResearchContext(
            prospect_id=prospect_id,
            sources=sources,
            signals=signals,
            company_summary=parsed.get("company_summary", ""),
            role_summary=parsed.get("role_summary", ""),
            research_quality_score=adjusted_quality,
            recommended_angle=angle,
        )


# ---------------------------------------------------------------------------
# Claude Code CLI backend
# ---------------------------------------------------------------------------

COMBINED_RESEARCH_PROMPT = """\
You are a research analyst. You have existing data about this prospect below. \
Do exactly 2 focused web searches to fill gaps, then return structured JSON.

=== PROSPECT (already known — do NOT re-search this) ===
Name: {first_name} {last_name}
Company: {company}
LinkedIn URL: {linkedin_url}
LinkedIn Title: {linkedin_title}
LinkedIn Description: {linkedin_description}
Board Member: {board_member}
City/State: {city}, {state}

=== RULES ===
- Do NOT search for or fetch LinkedIn pages (they are login-walled).
- Do NOT use WebFetch. Only use WebSearch.
- Do exactly 2 web searches, no more:
  Search 1: "{first_name} {last_name}" "{company}" — to find company info and their role
  Search 2: "{first_name} {last_name}" news OR award OR appointment — to find recent activity
- Read the search snippets and extract what you need. Do NOT follow links.
- Return your JSON response immediately after reading the search results.

=== OUTPUT FORMAT ===
Respond with ONLY a JSON object:
{{
  "company_website": {{
    "url": "https://...",
    "summary": "2-3 sentence summary of the company"
  }},
  "linkedin_profile": {{
    "summary": "Based on the LinkedIn Title and Description provided above, summarize their role and career"
  }},
  "linkedin_activity": {{
    "found": false,
    "summary": ""
  }},
  "recent_news": {{
    "found": true/false,
    "summary": "press, awards, funding, appointments from search results"
  }},
  "philanthropy": {{
    "found": true/false,
    "summary": "any foundation, nonprofit, or charitable info found in search results"
  }}
}}"""


class ClaudeCodeResearcher:
    """Runs web research for a prospect using claude -p with WebSearch/WebFetch tools."""

    def __init__(self, client):
        """Initialize with a ClaudeCodeClient instance."""
        self._client = client

    async def research_prospect(self, row: dict) -> ResearchContext:
        """Run combined web research, then contextualize with Claude."""
        prospect_id = _safe_str(row.get("WE Record ID")) or _safe_str(row.get("originalID"))
        first = _safe_str(row.get("First Name"))
        last = _safe_str(row.get("Last Name"))
        company = _safe_str(row.get("Business name"))
        linkedin_url = _safe_str(row.get("LinkedIn_URL"))
        linkedin_title = _safe_str(row.get("LinkedIn_Title"))
        linkedin_desc = _safe_str(row.get("LinkedIn_Description"))
        board_member = _safe_str(row.get("Board Member")).upper() == "Y"
        city = _safe_str(row.get("City"))
        state = _safe_str(row.get("State"))

        prompt = COMBINED_RESEARCH_PROMPT.format(
            first_name=first,
            last_name=last,
            company=company,
            linkedin_url=linkedin_url or "(not available)",
            linkedin_title=linkedin_title or "(not available)",
            linkedin_description=linkedin_desc or "(not available)",
            board_member="Yes" if board_member else "No",
            city=city,
            state=state,
        )

        # Single research call with web tools
        sources: list[ResearchSource] = []
        try:
            raw = await self._client.research(prompt)
            sources = self._parse_research_response(raw, company, first, last, linkedin_url)
        except Exception as e:
            log.error("Research failed for %s %s: %s", first, last, e)
            sources.append(ResearchSource(
                source_type="error", fetch_success=False, error=str(e)[:200],
            ))

        # Compute quality score (same logic as API backend)
        quality = compute_quality_score(sources)

        # Build research text for context extraction
        research_text = compile_research_text(sources)

        if not research_text.strip():
            return ResearchContext(
                prospect_id=prospect_id,
                sources=sources,
                research_quality_score=quality,
            )

        # Context extraction (no tools needed)
        context = await self._extract_context(row, sources, research_text, quality, prospect_id)
        return context

    def _parse_research_response(
        self, raw: str, company: str, first: str, last: str, linkedin_url: str
    ) -> list[ResearchSource]:
        """Parse the combined JSON response into ResearchSource objects."""
        sources = []
        try:
            data = _extract_json(raw)
        except (json.JSONDecodeError, ValueError):
            # If JSON parse fails, treat entire response as a single source
            log.warning("Could not parse research JSON, using raw text")
            sources.append(ResearchSource(
                source_type="company_website",
                title=f"Raw research: {first} {last}",
                content_summary=_truncate(raw),
                fetch_success=bool(raw.strip()),
            ))
            return sources

        # Company website
        cw = data.get("company_website", {})
        if isinstance(cw, dict):
            summary = cw.get("summary", "") or ""
            sources.append(ResearchSource(
                source_type="company_website",
                url=cw.get("url", "") or "",
                title=f"Company: {company}",
                content_summary=_truncate(summary),
                fetch_success=bool(summary),
            ))

        # LinkedIn profile
        lp = data.get("linkedin_profile", {})
        if isinstance(lp, dict):
            summary = lp.get("summary", "") or ""
            sources.append(ResearchSource(
                source_type="linkedin_profile",
                url=linkedin_url or "",
                title=f"LinkedIn: {first} {last}",
                content_summary=_truncate(summary),
                fetch_success=bool(summary),
            ))

        # LinkedIn activity
        la = data.get("linkedin_activity", {})
        if isinstance(la, dict):
            found = la.get("found", False)
            summary = la.get("summary", "")
            sources.append(ResearchSource(
                source_type="linkedin_posts",
                title=f"LinkedIn activity: {first} {last}",
                content_summary=_truncate(summary) if found else "",
                fetch_success=bool(found and summary),
            ))

        # Recent news
        rn = data.get("recent_news", {})
        if isinstance(rn, dict):
            found = rn.get("found", False)
            summary = rn.get("summary", "")
            sources.append(ResearchSource(
                source_type="news_article",
                title=f"News: {first} {last}",
                content_summary=_truncate(summary) if found else "",
                fetch_success=bool(found and summary),
            ))

        # Philanthropy
        ph = data.get("philanthropy", {})
        if isinstance(ph, dict):
            found = ph.get("found", False)
            summary = ph.get("summary", "")
            sources.append(ResearchSource(
                source_type="philanthropy",
                title=f"Philanthropy: {first} {last}",
                content_summary=_truncate(summary) if found else "",
                fetch_success=bool(found and summary),
            ))

        return sources

    async def _extract_context(
        self,
        row: dict,
        sources: list[ResearchSource],
        research_text: str,
        quality: int,
        prospect_id: str,
    ) -> ResearchContext:
        """Use Claude (no tools) to extract structured context from raw research."""
        prompt = CONTEXT_EXTRACTION_PROMPT.format(
            first_name=_safe_str(row.get("First Name")),
            last_name=_safe_str(row.get("Last Name")),
            linkedin_title=_safe_str(row.get("LinkedIn_Title")),
            company=_safe_str(row.get("Business name")),
            city=_safe_str(row.get("City")),
            state=_safe_str(row.get("State")),
            member_tier=_safe_str(row.get("Member_Tier")),
            propensity_total=_safe_str(row.get("Propensity_Total")),
            seniority_label=_safe_str(row.get("Title_Seniority_Label")),
            board_member=_safe_str(row.get("Board Member")),
            aircraft_owner=_safe_str(row.get("Aircraft Owner")),
            boat_owner=_safe_str(row.get("Boat Owner")),
            net_worth_rating=_safe_str(row.get("Net Worth Rating")),
            real_estate_properties=_safe_str(row.get("Real Estate Properties")),
            research_text=research_text,
        )

        raw = await self._client.generate(prompt)

        try:
            parsed = _extract_json(raw)
        except (json.JSONDecodeError, ValueError):
            # Retry with stronger instruction
            retry_prompt = prompt + "\n\nIMPORTANT: Respond with ONLY a valid JSON object. No other text."
            raw = await self._client.generate(retry_prompt)
            parsed = _extract_json(raw)

        signals = []
        for s in parsed.get("signals", []):
            try:
                signals.append(ContextSignal(**s))
            except Exception:
                continue

        angle_str = parsed.get("recommended_angle", "general").lower()
        try:
            angle = EmailAngle(angle_str)
        except ValueError:
            angle = EmailAngle.GENERAL

        adjusted_quality = quality
        if len(signals) >= 3:
            adjusted_quality += 10
        if any(s.recency == "recent" for s in signals):
            adjusted_quality += 10
        adjusted_quality = min(adjusted_quality, 100)

        return ResearchContext(
            prospect_id=prospect_id,
            sources=sources,
            signals=signals,
            company_summary=parsed.get("company_summary", ""),
            role_summary=parsed.get("role_summary", ""),
            research_quality_score=adjusted_quality,
            recommended_angle=angle,
        )
