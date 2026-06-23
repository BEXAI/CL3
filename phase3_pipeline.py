"""Phase 3 — Main orchestrator: rate limiters, concurrency control, output assembly."""

import asyncio
import csv
import json
import logging
import os
import ssl
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

import aiohttp
import anthropic
from tqdm.asyncio import tqdm_asyncio

from phase3_checkpoint import CheckpointManager
from phase3_claude_code_client import ClaudeCodeClient
from phase3_config import Phase3Config
from phase3_email_generator import ClaudeCodeEmailGenerator, EmailGenerator, compute_angle
from phase3_models import (
    EmailAngle,
    Phase3RunSummary,
    ProspectOutreachResult,
)
from phase3_research import (
    ClaudeCodeResearcher,
    ProspectResearcher,
    TokenBucketRateLimiter,
    _safe_str,
)

log = logging.getLogger(__name__)


def _find_email(row: dict) -> str:
    """Find the best email address from the row's email columns."""
    for key in [
        "Personal email 1", "Personal email 2", "Personal email 3",
        "Business email 1", "Business email 2",
    ]:
        val = _safe_str(row.get(key))
        if val and "@" in val:
            return val
    return ""


class Phase3Pipeline:
    """Orchestrates the full Phase 3 outreach pipeline."""

    def __init__(self, config: Phase3Config):
        self.config = config
        self.checkpoint = CheckpointManager(
            config.checkpoint_csv, config.checkpoint_jsonl, config.progress_json,
        )
        self._stats = Phase3RunSummary()
        self._results: list = []

    async def run(self) -> Phase3RunSummary:
        """Execute the full pipeline."""
        start_time = time.time()

        # Step 1: Load and filter prospects
        rows = self._load_prospects()
        if not rows:
            log.info("No prospects to process.")
            return self._stats

        # Step 2: Check resume state
        completed_ids = self.checkpoint.load_completed_ids()
        pending = [r for r in rows if self._get_prospect_id(r) not in completed_ids]

        log.info(
            "Scope: %d total | %d already done | %d pending",
            len(rows), len(completed_ids), len(pending),
        )

        if not pending:
            log.info("All prospects already processed. Assembling output.")
            self._assemble_output()
            return self._stats

        # Step 3: Initialize async components based on backend
        checkpoint_lock = asyncio.Lock()

        if self.config.backend == "claude-code":
            await self._run_claude_code_backend(pending, checkpoint_lock)
        else:
            await self._run_api_backend(pending, checkpoint_lock)

        # Step 4: Compile stats
        self._compile_stats(self._results, start_time)

        # Step 5: Assemble final output
        self.checkpoint.finalize()
        self._assemble_output()
        self._write_summary()

        return self._stats

    async def _run_claude_code_backend(
        self, pending: list[dict], checkpoint_lock: asyncio.Lock,
    ) -> None:
        """Run pipeline using claude -p CLI backend."""
        concurrency = min(self.config.concurrency, 3)
        log.info("Backend: claude-code | Concurrency: %d", concurrency)

        client = ClaudeCodeClient(concurrency=concurrency)
        researcher = ClaudeCodeResearcher(client)
        email_gen = ClaudeCodeEmailGenerator(client)

        async def process_one(row: dict):
            return await self._process_prospect(
                row, researcher, email_gen, checkpoint_lock,
            )

        tasks = [process_one(r) for r in pending]
        self._results = await tqdm_asyncio.gather(
            *tasks, desc="Phase 3 outreach (claude-code)", total=len(tasks),
        )

    async def _run_api_backend(
        self, pending: list[dict], checkpoint_lock: asyncio.Lock,
    ) -> None:
        """Run pipeline using Anthropic API backend."""
        log.info("Backend: api | Concurrency: %d", self.config.concurrency)

        semaphore = asyncio.Semaphore(self.config.concurrency)
        claude_client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
        claude_rl = TokenBucketRateLimiter(rate=self.config.claude_rate, max_tokens=1)
        web_rl = TokenBucketRateLimiter(rate=self.config.web_search_rate, max_tokens=1)

        ssl_ctx = ssl.create_default_context()
        connector = aiohttp.TCPConnector(ssl=ssl_ctx, limit=20)

        async with aiohttp.ClientSession(connector=connector) as http_session:
            researcher = ProspectResearcher(
                claude_client, http_session, claude_rl, web_rl, self.config.model,
            )
            email_gen = EmailGenerator(claude_client, claude_rl, self.config.model)

            async def process_one(row: dict):
                async with semaphore:
                    return await self._process_prospect(
                        row, researcher, email_gen, checkpoint_lock,
                    )

            tasks = [process_one(r) for r in pending]
            self._results = await tqdm_asyncio.gather(
                *tasks, desc="Phase 3 outreach (api)", total=len(tasks),
            )

    def _load_prospects(self) -> list[dict]:
        """Load and filter prospects from input CSV."""
        log.info("Loading prospects from %s", self.config.input_csv)
        rows = []
        with open(self.config.input_csv, encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tier = _safe_str(row.get("Member_Tier"))
                if tier in self.config.tiers:
                    rows.append(row)
                    if self.config.max_prospects > 0 and len(rows) >= self.config.max_prospects:
                        break

        log.info(
            "Loaded %d prospects in tiers: %s", len(rows), ", ".join(self.config.tiers),
        )

        return rows

    def _get_prospect_id(self, row: dict) -> str:
        return _safe_str(row.get("WE Record ID")) or _safe_str(row.get("originalID"))

    async def _process_prospect(
        self,
        row: dict,
        researcher,
        email_gen,
        checkpoint_lock: asyncio.Lock,
    ) -> ProspectOutreachResult:
        """Full per-prospect pipeline: research → contextualize → generate."""
        prospect_id = self._get_prospect_id(row)
        first = _safe_str(row.get("First Name"))
        last = _safe_str(row.get("Last Name"))
        t0 = time.time()

        result = ProspectOutreachResult(
            prospect_id=prospect_id,
            first_name=first,
            last_name=last,
            email_address=_find_email(row),
            member_tier=_safe_str(row.get("Member_Tier")),
            propensity_total=int(_safe_str(row.get("Propensity_Total")) or "0"),
            linkedin_url=_safe_str(row.get("LinkedIn_URL")),
            status="researching",
        )

        try:
            # Stage 1: Research
            context = await researcher.research_prospect(row)
            result.research = context
            result.status = "researching"

            # Quality gate
            if context.research_quality_score < self.config.min_quality:
                result.status = "skipped"
                result.skip_reason = (
                    f"skipped_thin_research (quality={context.research_quality_score})"
                )
                result.processing_time_seconds = time.time() - t0
                await self.checkpoint.save_result(result, checkpoint_lock)
                return result

            # Dry run: skip email generation
            if self.config.dry_run:
                result.status = "completed"
                result.skip_reason = "dry_run"
                result.processing_time_seconds = time.time() - t0
                await self.checkpoint.save_result(result, checkpoint_lock)
                return result

            # Stage 2: Angle selection (code-enforced)
            angle = compute_angle(row, context)

            # Stage 3: Email generation
            result.status = "generating"
            email = await email_gen.generate_email(row, context, angle)
            result.email = email
            result.status = "completed"

        except Exception as e:
            log.error("Error processing %s %s (%s): %s", first, last, prospect_id, e)
            result.status = "error"
            result.error_message = str(e)[:300]

        result.processing_time_seconds = time.time() - t0
        await self.checkpoint.save_result(result, checkpoint_lock)
        return result

    def _compile_stats(self, results: list, start_time: float) -> None:
        """Aggregate stats from all results."""
        angle_dist = defaultdict(int)
        tier_breakdown = defaultdict(lambda: defaultdict(int))
        quality_scores = []
        proc_times = []

        for r in results:
            if not isinstance(r, ProspectOutreachResult):
                self._stats.errors += 1
                continue

            self._stats.total_processed += 1
            proc_times.append(r.processing_time_seconds)

            if r.research:
                quality_scores.append(r.research.research_quality_score)

            if r.status == "completed" and r.email:
                self._stats.emails_generated += 1
                angle_dist[r.email.angle_used.value] += 1
                tier_breakdown[r.member_tier]["generated"] = (
                    tier_breakdown[r.member_tier].get("generated", 0) + 1
                )
            elif r.status == "skipped":
                if "thin_research" in r.skip_reason:
                    self._stats.skipped_thin_research += 1
                else:
                    self._stats.skipped_other += 1
                tier_breakdown[r.member_tier]["skipped"] = (
                    tier_breakdown[r.member_tier].get("skipped", 0) + 1
                )
            elif r.status == "error":
                self._stats.errors += 1
                tier_breakdown[r.member_tier]["error"] = (
                    tier_breakdown[r.member_tier].get("error", 0) + 1
                )

        self._stats.angle_distribution = dict(angle_dist)
        self._stats.tier_breakdown = {k: dict(v) for k, v in tier_breakdown.items()}
        self._stats.avg_research_quality = (
            sum(quality_scores) / len(quality_scores) if quality_scores else 0
        )
        self._stats.avg_processing_time = (
            sum(proc_times) / len(proc_times) if proc_times else 0
        )
        self._stats.runtime_seconds = time.time() - start_time

        if self.config.backend == "claude-code":
            # Claude Code CLI uses the Max subscription — no per-call API cost
            self._stats.estimated_cost_usd = 0.0
        else:
            # Rough cost estimate: ~$0.003/context extraction + ~$0.003/email gen
            # + ~$0.005/web search call * ~4.5 avg searches per prospect
            total_api_calls = self._stats.total_processed  # context calls
            total_api_calls += self._stats.emails_generated  # email gen calls
            web_search_calls = self._stats.total_processed * 4.5  # avg web searches
            self._stats.estimated_cost_usd = round(
                total_api_calls * 0.003 + web_search_calls * 0.005, 2
            )

    def _assemble_output(self) -> None:
        """Assemble final output CSV from checkpoint CSV."""
        if not self.config.checkpoint_csv.exists():
            log.warning("No checkpoint CSV found — nothing to assemble.")
            return

        # Copy checkpoint CSV to output, deduplicating by prospect_id
        seen = set()
        rows = []
        with open(self.config.checkpoint_csv, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                pid = row.get("prospect_id", "")
                if pid and pid not in seen:
                    seen.add(pid)
                    rows.append(row)

        if rows and fieldnames:
            with open(self.config.output_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            log.info(
                "Output written: %s (%d rows)", self.config.output_csv, len(rows),
            )

    def _write_summary(self) -> None:
        """Write run summary JSON."""
        data = self._stats.model_dump()
        dir_name = str(self.config.summary_json.parent) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, str(self.config.summary_json))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        log.info("Summary written: %s", self.config.summary_json)

        # Print summary
        print()
        print("=" * 70)
        print("PHASE 3 — OUTREACH PIPELINE SUMMARY")
        print("=" * 70)
        print()
        print(f"  Total processed:       {self._stats.total_processed:,}")
        print(f"  Emails generated:      {self._stats.emails_generated:,}")
        print(f"  Skipped (thin data):   {self._stats.skipped_thin_research:,}")
        print(f"  Skipped (other):       {self._stats.skipped_other:,}")
        print(f"  Errors:                {self._stats.errors:,}")
        print(f"  Avg research quality:  {self._stats.avg_research_quality:.1f}")
        print(f"  Avg processing time:   {self._stats.avg_processing_time:.1f}s")
        print(f"  Estimated cost:        ${self._stats.estimated_cost_usd:.2f}")
        print(f"  Runtime:               {self._stats.runtime_seconds:.0f}s")
        print()
        if self._stats.angle_distribution:
            print("  Angle Distribution:")
            for angle, count in sorted(
                self._stats.angle_distribution.items(), key=lambda x: -x[1]
            ):
                print(f"    {angle:15s}  {count:>6,}")
        print()
        if self._stats.tier_breakdown:
            print("  Tier Breakdown:")
            for tier, counts in self._stats.tier_breakdown.items():
                parts = ", ".join(f"{k}={v}" for k, v in counts.items())
                print(f"    {tier:10s}  {parts}")
        print()
        print("DONE!")
