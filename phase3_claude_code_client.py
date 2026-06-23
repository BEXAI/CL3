"""Phase 3 — Async wrapper around `claude -p` CLI subprocess calls."""

import asyncio
import json
import logging

log = logging.getLogger(__name__)

# Timeouts (seconds)
RESEARCH_TIMEOUT = 90
GENERATE_TIMEOUT = 60

# Max agent turns (caps tool calls to prevent runaway searches)
RESEARCH_MAX_TURNS = 6
GENERATE_MAX_TURNS = 2

# Default concurrency for claude-code backend
DEFAULT_CONCURRENCY = 3

# Retry config
MAX_RETRIES = 3
RETRY_BACKOFFS = [5, 15]  # seconds between retries 1→2, 2→3


class ClaudeCodeClient:
    """Calls `claude -p` as a subprocess for research and generation tasks."""

    def __init__(self, concurrency: int = DEFAULT_CONCURRENCY):
        self._semaphore = asyncio.Semaphore(concurrency)

    async def research(self, prompt: str) -> str:
        """Run a prompt with WebSearch only (no WebFetch — snippets suffice)."""
        return await self._call(
            prompt,
            tools="WebSearch",
            timeout=RESEARCH_TIMEOUT,
            max_turns=RESEARCH_MAX_TURNS,
        )

    async def generate(self, prompt: str) -> str:
        """Run a prompt with no tools (pure generation)."""
        return await self._call(
            prompt,
            tools="",
            timeout=GENERATE_TIMEOUT,
            max_turns=GENERATE_MAX_TURNS,
        )

    async def _call(self, prompt: str, tools: str, timeout: int, max_turns: int = 3) -> str:
        """Execute `claude -p` with retry and return the result text."""
        last_err: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return await self._call_once(prompt, tools, timeout, max_turns)
            except TimeoutError:
                raise  # Don't retry timeouts
            except RuntimeError as e:
                last_err = e
                if attempt < MAX_RETRIES:
                    delay = RETRY_BACKOFFS[attempt - 1]
                    log.warning(
                        "claude -p attempt %d/%d failed, retrying in %ds: %s",
                        attempt, MAX_RETRIES, delay, str(e)[:200],
                    )
                    await asyncio.sleep(delay)

        raise last_err  # type: ignore[misc]

    async def _call_once(self, prompt: str, tools: str, timeout: int, max_turns: int = 3) -> str:
        """Single attempt: execute `claude -p` and return the result text."""
        async with self._semaphore:
            cmd = [
                "claude",
                "-p",
                "--output-format", "json",
                "--tools", tools if tools else "",
                "--max-turns", str(max_turns),
            ]

            log.info(
                "claude -p call: tools=%s timeout=%ds cmd=%s",
                tools or "(none)", timeout, " ".join(cmd),
            )

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=prompt.encode("utf-8")),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise TimeoutError(
                    f"claude -p timed out after {timeout}s"
                )

            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                detail = stderr_str or stdout_str
                # Try to extract error from JSON envelope
                try:
                    envelope = json.loads(stdout_str)
                    if envelope.get("result"):
                        detail = str(envelope["result"])
                except (json.JSONDecodeError, KeyError):
                    pass
                raise RuntimeError(
                    f"claude -p exited with code {proc.returncode}: {detail[:500]}"
                )

            # Parse the JSON envelope: {"result": "...", "is_error": false, ...}
            try:
                envelope = json.loads(stdout_str)
            except json.JSONDecodeError:
                # If not valid JSON, return raw stdout as-is
                log.warning("claude -p returned non-JSON output, using raw text")
                return stdout_str

            if envelope.get("is_error"):
                raise RuntimeError(
                    f"claude -p reported error: {str(envelope.get('result', ''))[:300]}"
                )

            result = envelope.get("result", "")

            # Log cost if available
            cost_usd = envelope.get("cost_usd")
            if cost_usd is not None:
                log.debug("claude -p cost: $%.4f", cost_usd)

            return result
