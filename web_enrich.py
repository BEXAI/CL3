"""Drive the existing per-person enrichment (agent_enrich) from the web UI.

Parses pasted lines like:
    Jane Smith
    John Doe, Acme Capital, Miami, FL
into candidate rows, then runs agent_enrich.process_row concurrently and
returns a clean result list for the front end.
"""

import asyncio
import os
import ssl

import aiohttp
import anthropic

import agent_enrich

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CONCURRENCY = min(int(os.getenv("ENRICH_CONCURRENCY", "5")), 10)


def parse_lines(text: str) -> list[dict]:
    """Turn pasted text into candidate row dicts.

    Each non-empty line is `Name[, Company[, City[, State]]]`.
    The first whitespace token of Name is the first name; the rest is the
    last name.
    """
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        name = parts[0]
        tokens = name.split()
        if not tokens:
            continue
        first = tokens[0]
        last = " ".join(tokens[1:]) if len(tokens) > 1 else ""
        rows.append(
            {
                "First Name": first,
                "Last Name": last,
                "Business name": parts[1] if len(parts) > 1 else "",
                "City": parts[2] if len(parts) > 2 else "",
                "State": parts[3] if len(parts) > 3 else "",
                "_input": line,
            }
        )
    return rows


async def _run(rows: list[dict], on_progress) -> list[dict]:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    rate_limiter = agent_enrich.TokenBucketRateLimiter(rate=0.8, max_tokens=1)
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    ssl_ctx = ssl.create_default_context()
    results: list[dict | None] = [None] * len(rows)
    done = 0
    lock = asyncio.Lock()

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(ssl=ssl_ctx)
    ) as session:

        async def one(i: int, row: dict):
            nonlocal done
            res = await agent_enrich.process_row(
                row, i, session, rate_limiter, client, semaphore
            )
            results[i] = {
                "input": row.get("_input", ""),
                "name": f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip(),
                "linkedin_url": res.get("linkedin_url"),
                "confidence_score": res.get("confidence_score", 0),
                "justification": res.get("justification", ""),
            }
            async with lock:
                done += 1
                on_progress(done)

        await asyncio.gather(*(one(i, r) for i, r in enumerate(rows)))

    return [r for r in results if r is not None]


def run_enrichment_sync(rows: list[dict], on_progress) -> list[dict]:
    """Blocking entry point — call from a background thread."""
    return asyncio.run(_run(rows, on_progress))
