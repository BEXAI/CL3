#!/usr/bin/env python3
"""HNWI LinkedIn Agentic Enrichment Engine.

Pipeline:
1. Reads candidate rows from CSV
2. SerpAPI Google Search: finds real LinkedIn URLs via site:linkedin.com/in/ queries
3. Claude verification: cross-references search results against input data
4. Writes verified LinkedIn URLs (confidence >= 90) to output CSV

Usage:
    python agent_enrich.py
"""

import asyncio
import csv
import json
import logging
import math
import os
import re
import ssl
import sys
from pathlib import Path

import aiohttp
import anthropic
import pandas as pd
from dotenv import load_dotenv
from tqdm.asyncio import tqdm_asyncio

from models import AgentValidationResult

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parent
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CONCURRENCY_LIMIT = min(int(os.getenv("CONCURRENCY_LIMIT", "5")), 10)
SKIP_ROWS = int(os.getenv("SKIP_ROWS", "0"))
MAX_ROWS = int(os.getenv("MAX_ROWS", "0"))
INPUT_FILE_PATH = os.getenv("INPUT_FILE_PATH", "input.csv")
OUTPUT_FILE_PATH = PROJECT_DIR / "enriched_hnwi_profiles.csv"
CHECKPOINT_FILE_PATH = PROJECT_DIR / "checkpoint_hnwi_profiles.csv"
MODEL = os.getenv("MODEL", "claude-sonnet-4-6")


def _safe_str(val) -> str:
    """Convert a value to string, treating NaN/None as empty string."""
    if val is None:
        return ""
    if isinstance(val, float) and math.isnan(val):
        return ""
    return str(val).strip()


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Step 1: SerpAPI Google Search (finds REAL LinkedIn URLs)
# ---------------------------------------------------------------------------

async def _serpapi_search(
    query: str, session: aiohttp.ClientSession, rate_limiter: TokenBucketRateLimiter
) -> list:
    """Execute a Google search via SerpAPI, rate-limited via token bucket."""
    params = {
        "api_key": SERPAPI_KEY,
        "engine": "google",
        "q": query,
        "num": 5,
    }
    for attempt in range(4):
        await rate_limiter.acquire()
        async with session.get(
            "https://serpapi.com/search.json", params=params
        ) as resp:
            if resp.status == 429:
                wait = 3 * (attempt + 1)
                log.warning("SerpAPI rate limit, retrying in %ds...", wait)
                await asyncio.sleep(wait)
                continue
            if resp.status >= 500:
                wait = 2 * (attempt + 1)
                log.warning("SerpAPI %d, retrying in %ds...", resp.status, wait)
                await asyncio.sleep(wait)
                continue
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"SerpAPI {resp.status}: {text[:300]}")
            data = await resp.json()
            return data.get("organic_results", [])
    return []


async def search_candidate(
    row_data: dict, session: aiohttp.ClientSession, rate_limiter: TokenBucketRateLimiter
) -> str:
    """Search Google via SerpAPI for LinkedIn profiles matching the candidate.

    Uses the strategy: site:linkedin.com/in/ "First Last" "City" "Business"
    Falls back to simpler queries if the specific one returns nothing.
    """
    first = _safe_str(row_data.get("First Name"))
    last = _safe_str(row_data.get("Last Name"))
    city = _safe_str(row_data.get("City"))
    state = _safe_str(row_data.get("State"))
    biz = _safe_str(row_data.get("Business name"))

    name = f"{first} {last}".strip()
    if not name:
        return "No name provided — cannot search."

    # Build queries from most specific to least specific
    queries = []

    # Query 1: Name + City + Business (most specific)
    q1_parts = [f'site:linkedin.com/in/ "{name}"']
    if city:
        q1_parts.append(f'"{city}"')
    if biz:
        q1_parts.append(f'"{biz}"')
    queries.append(" ".join(q1_parts))

    # Query 2: Name + Business only
    if city and biz:
        queries.append(f'site:linkedin.com/in/ "{name}" "{biz}"')

    # Query 3: Name + City + State
    if city and state:
        queries.append(f'site:linkedin.com/in/ "{name}" "{city}" "{state}"')

    # Query 4: Just name (broadest fallback)
    if biz or city:
        queries.append(f'site:linkedin.com/in/ "{name}"')

    # Try queries in order, stop at first results
    for query in queries:
        results = await _serpapi_search(query, session, rate_limiter)
        if results:
            linkedin_results = [
                r for r in results
                if "linkedin.com/in/" in r.get("link", "")
            ]
            if linkedin_results:
                return _format_search_results(linkedin_results, query)

    return "No LinkedIn profiles found after searching Google."


def _format_search_results(results: list, query_used: str) -> str:
    """Format SerpAPI search results into text for Claude evaluation."""
    lines = [f"Google query used: {query_used}\n"]
    for i, item in enumerate(results, 1):
        url = item.get("link", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        lines.append(
            f"Result {i}:\n"
            f"  LinkedIn URL: {url}\n"
            f"  Title: {title}\n"
            f"  Snippet: {snippet}"
        )
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Step 2: Claude Verification (evaluates search results against input data)
# ---------------------------------------------------------------------------

def _build_evaluation_prompt(row_data: dict, search_output: str) -> str:
    """Build the prompt for Claude to verify Google search results."""

    relevant_keys = [
        "First Name", "Last Name", "City", "State",
        "Business name", "Business name 2", "Business name 3",
        "2nd Person Last Name", "2nd Person First Name",
    ]
    fields_summary = "\n".join(
        f"  - {k}: {s}"
        for k in relevant_keys
        if (s := _safe_str(row_data.get(k)))
    )

    return f"""You are a verification analyst. Your job is to examine REAL Google search
results for LinkedIn profiles and determine which (if any) is a TRUE match for
the candidate described below.

=== CANDIDATE RECORD ===
{fields_summary}

=== GOOGLE SEARCH RESULTS ===
{search_output}

=== INSTRUCTIONS ===
1. Examine each LinkedIn URL returned by Google.
2. Compare the profile's title, snippet, location, and company against the
   candidate's record fields (Business Name, City, State, names, assets).
3. For each matching field, add it to "matched_criteria".
4. For each conflicting field, add a description to "discrepancies_found".
5. Assign a confidence_score (0-100):
   - 95-100: Name, location, AND business clearly match in the Google result.
   - 85-94:  Name and business match, but location not confirmed.
   - 70-84:  Name matches, partial business or location match.
   - 50-69:  Only name matches; other fields ambiguous or missing.
   - 0-49:   No credible match or wrong person with same name.
6. ALWAYS populate "linkedin_url" with the best-matching URL from the results,
   even if confidence is low. Only set linkedin_url to null if there are truly
   NO results or NO plausible match at all.
7. STRICT PENALTIES:
   - If the LinkedIn profile clearly belongs to a DIFFERENT person, confidence = 0.
   - If business affiliations clearly conflict, cap confidence at 60.
8. If multiple results could match, pick the BEST one.
9. Write a clear "justification" explaining your reasoning.

Respond with ONLY a JSON object:
{{
  "linkedin_url": "<real URL from results or null>",
  "confidence_score": <0-100>,
  "matched_criteria": ["field1", "field2"],
  "discrepancies_found": ["description1"],
  "justification": "explanation"
}}"""


def _extract_json(raw: str) -> dict:
    """Robustly extract a JSON object from Claude's response."""
    # Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)

    # Try direct parse first (fastest path)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Fall back to regex extraction
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise json.JSONDecodeError("No JSON object found in response", raw, 0)


async def evaluate_search_results(
    row_data: dict, search_output: str, client: anthropic.AsyncAnthropic
) -> AgentValidationResult:
    """Use Claude to evaluate search results against the candidate record."""

    prompt = _build_evaluation_prompt(row_data, search_output)

    message = await client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    if not message.content:
        raise RuntimeError("Empty response from Claude API")

    raw = message.content[0].text.strip()
    parsed = _extract_json(raw)
    return AgentValidationResult(**parsed)


# ---------------------------------------------------------------------------
# Per-Row Pipeline
# ---------------------------------------------------------------------------

async def process_row(
    row_data: dict,
    row_index: int,
    search_session: aiohttp.ClientSession,
    rate_limiter: TokenBucketRateLimiter,
    claude_client: anthropic.AsyncAnthropic,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Full pipeline: SerpAPI Google Search -> Claude Verification."""
    async with semaphore:
        try:
            search_output = await search_candidate(row_data, search_session, rate_limiter)
            result = await evaluate_search_results(row_data, search_output, claude_client)

            return {
                "linkedin_url": result.linkedin_url,
                "confidence_score": result.confidence_score,
                "matched_criteria": "; ".join(result.matched_criteria),
                "discrepancies_found": "; ".join(result.discrepancies_found),
                "justification": result.justification,
            }
        except Exception as e:
            log.error("Failed to process row %d: %s", row_index, e)
            return {
                "linkedin_url": None,
                "confidence_score": 0,
                "matched_criteria": "",
                "discrepancies_found": "",
                "justification": f"Error: {e}",
            }


# ---------------------------------------------------------------------------
# Checkpoint Logic
# ---------------------------------------------------------------------------


def load_checkpoint() -> set:
    """Return set of row indices already processed."""
    path = Path(CHECKPOINT_FILE_PATH)
    if not path.exists() or path.stat().st_size == 0:
        return set()
    try:
        df = pd.read_csv(path, usecols=["_original_index"])
        return set(df["_original_index"].dropna().astype(int).tolist())
    except Exception:
        return set()


async def save_checkpoint(
    index: int, row_data: dict, result: dict, checkpoint_lock: asyncio.Lock
):
    """Append a single processed row to the checkpoint file (async-safe)."""
    async with checkpoint_lock:
        record = {**row_data, **result, "_original_index": index}
        path = Path(CHECKPOINT_FILE_PATH)
        write_header = not path.exists() or path.stat().st_size == 0
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(record.keys()))
            if write_header:
                writer.writeheader()
            writer.writerow(record)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    if not SERPAPI_KEY:
        log.error("SERPAPI_KEY is not set. Add it to your .env file.")
        sys.exit(1)
    if not ANTHROPIC_API_KEY:
        log.error("ANTHROPIC_API_KEY is not set.")
        sys.exit(1)

    input_path = PROJECT_DIR / INPUT_FILE_PATH
    if not input_path.exists():
        input_path = Path(INPUT_FILE_PATH)
    if not input_path.exists():
        log.error("Input file not found: %s", input_path)
        sys.exit(1)

    log.info("Loading dataset from %s", input_path)
    df = pd.read_csv(input_path, low_memory=False)
    total_rows = len(df)

    # Apply SKIP_ROWS and MAX_ROWS to select a slice of the dataset
    if SKIP_ROWS > 0:
        df = df.iloc[SKIP_ROWS:]
        df = df.reset_index(drop=True)
    if MAX_ROWS > 0:
        df = df.head(MAX_ROWS)

    log.info(
        "Processing rows %d–%d (%d rows) from %d total",
        SKIP_ROWS, SKIP_ROWS + len(df) - 1, len(df), total_rows,
    )

    completed = load_checkpoint()
    # Use global indices for checkpoint lookup, local indices for df access
    pending_indices = [i for i in range(len(df)) if (i + SKIP_ROWS) not in completed]

    if not pending_indices:
        log.info("All rows already processed. Assembling final output.")
    else:
        log.info(
            "%d rows already checkpointed, %d remaining",
            len(completed),
            len(pending_indices),
        )

        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
        rate_limiter = TokenBucketRateLimiter(rate=0.8, max_tokens=1)
        checkpoint_lock = asyncio.Lock()
        claude_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        ssl_ctx = ssl.create_default_context()

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=ssl_ctx)
        ) as search_session:

            async def _process_and_checkpoint(idx: int):
                row = df.iloc[idx].to_dict()
                global_idx = idx + SKIP_ROWS  # Map local index to global CSV row
                result = await process_row(
                    row, global_idx, search_session, rate_limiter,
                    claude_client, semaphore,
                )
                await save_checkpoint(global_idx, row, result, checkpoint_lock)
                return idx, result

            tasks = [_process_and_checkpoint(i) for i in pending_indices]
            await tqdm_asyncio.gather(*tasks, desc="Enriching candidates")

    # Assemble final output from checkpoint
    checkpoint_path = Path(CHECKPOINT_FILE_PATH)
    if checkpoint_path.exists() and checkpoint_path.stat().st_size > 0:
        results_df = pd.read_csv(checkpoint_path)

        # Deduplicate — keep last result per index (in case of re-runs)
        results_df["_original_index"] = results_df["_original_index"].dropna().astype(int)
        results_df = results_df.drop_duplicates(subset="_original_index", keep="last")
        results_df = results_df.set_index("_original_index")

        enrich_cols = [
            "linkedin_url",
            "confidence_score",
            "matched_criteria",
            "discrepancies_found",
            "justification",
        ]
        for col in enrich_cols:
            if col in results_df.columns:
                # Map global checkpoint indices back to local df indices
                mapped = results_df[col].rename(
                    index=lambda g: g - SKIP_ROWS
                )
                df[col] = mapped.reindex(df.index)

    df.to_csv(OUTPUT_FILE_PATH, index=False)
    log.info("Final output saved to %s", OUTPUT_FILE_PATH)

    if "confidence_score" in df.columns:
        has_url = df["linkedin_url"].notna().sum()
        high = (df["confidence_score"] >= 90).sum()
        mid = ((df["confidence_score"] >= 50) & (df["confidence_score"] < 90)).sum()
        low = ((df["confidence_score"] > 0) & (df["confidence_score"] < 50)).sum()
        log.info(
            "Results: %d/%d URLs found | %d high (>=90) | %d mid (50-89) | %d low (1-49)",
            has_url, len(df), high, mid, low,
        )


if __name__ == "__main__":
    asyncio.run(main())
