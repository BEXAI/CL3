"""Phase 3 — Checkpoint manager: CSV + JSONL dual checkpoint with resume detection."""

import csv
import json
import os
import tempfile
from pathlib import Path

from phase3_models import ProspectOutreachResult


class CheckpointManager:
    """Manages dual-file checkpointing for crash-safe resume.

    - CSV:   One row per prospect (email drafts + metadata). Fast ID scan for resume.
    - JSONL: Full ProspectOutreachResult per line. Complete audit trail.
    - JSON:  Atomic-write progress counter (updated every N prospects).
    """

    CSV_COLUMNS = [
        "prospect_id", "first_name", "last_name", "email_address",
        "member_tier", "propensity_total", "linkedin_url",
        "status", "research_quality_score", "subject_line", "email_body",
        "angle_used", "hooks_used", "signals_count", "skip_reason", "error",
    ]

    def __init__(self, checkpoint_csv: Path, checkpoint_jsonl: Path, progress_json: Path):
        self._csv_path = checkpoint_csv
        self._jsonl_path = checkpoint_jsonl
        self._progress_path = progress_json
        self._completed_ids: set[str] = set()
        self._count = 0

    def load_completed_ids(self) -> set[str]:
        """Scan checkpoint CSV for already-processed prospect IDs."""
        self._completed_ids = set()
        if not self._csv_path.exists() or self._csv_path.stat().st_size == 0:
            return self._completed_ids
        try:
            with open(self._csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    pid = row.get("prospect_id", "").strip()
                    if pid:
                        self._completed_ids.add(pid)
        except Exception:
            pass
        self._count = len(self._completed_ids)
        return self._completed_ids

    async def save_result(self, result: ProspectOutreachResult, lock) -> None:
        """Append one result to both CSV and JSONL files (async-lock-safe)."""
        async with lock:
            self._append_csv(result)
            self._append_jsonl(result)
            self._completed_ids.add(result.prospect_id)
            self._count += 1
            if self._count % 10 == 0:
                self._write_progress()

    def _append_csv(self, result: ProspectOutreachResult) -> None:
        write_header = not self._csv_path.exists() or self._csv_path.stat().st_size == 0
        row = {
            "prospect_id": result.prospect_id,
            "first_name": result.first_name,
            "last_name": result.last_name,
            "email_address": result.email_address,
            "member_tier": result.member_tier,
            "propensity_total": result.propensity_total,
            "linkedin_url": result.linkedin_url,
            "status": result.status,
            "research_quality_score": result.research.research_quality_score if result.research else 0,
            "subject_line": result.email.subject_line if result.email else "",
            "email_body": _sanitize_csv(result.email.email_body) if result.email else "",
            "angle_used": result.email.angle_used.value if result.email else "",
            "hooks_used": "; ".join(result.email.hooks_used) if result.email else "",
            "signals_count": len(result.research.signals) if result.research else 0,
            "skip_reason": result.skip_reason,
            "error": result.error_message,
        }
        with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_COLUMNS)
            if write_header:
                writer.writeheader()
            writer.writerow(row)

    def _append_jsonl(self, result: ProspectOutreachResult) -> None:
        with open(self._jsonl_path, "a", encoding="utf-8") as f:
            f.write(result.model_dump_json() + "\n")

    def _write_progress(self) -> None:
        """Atomic write of progress counter."""
        data = {"completed": self._count}
        dir_name = str(self._progress_path.parent) or "."
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f)
            os.replace(tmp_path, str(self._progress_path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def finalize(self) -> None:
        """Write final progress count."""
        self._write_progress()

    @property
    def completed_count(self) -> int:
        return self._count


def _sanitize_csv(text: str) -> str:
    """Remove control characters that break CSV, preserving sentence structure."""
    if not text:
        return ""
    # Replace newlines with spaces, strip control chars
    import re
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", text)
    return text.strip()
