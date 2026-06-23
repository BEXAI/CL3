"""Phase 3 — Configuration, CLI argument parsing, and environment variable loading."""

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_DIR = Path(__file__).resolve().parent


@dataclass
class Phase3Config:
    """All tuneable parameters for the Phase 3 outreach pipeline."""

    # Backend: "api" (Anthropic API) or "claude-code" (claude -p CLI)
    backend: str = "claude-code"

    # API
    anthropic_api_key: str = ""
    model: str = "claude-sonnet-4-6"

    # Concurrency / rate limits
    concurrency: int = 5
    claude_rate: float = 0.75       # tokens/sec  (~45 req/min)
    web_search_rate: float = 0.33   # tokens/sec  (~20 req/min)

    # Quality gate
    min_quality: int = 30

    # Scope
    tiers: list[str] = field(default_factory=lambda: ["Platinum", "Gold"])
    max_prospects: int = 0  # 0 = unlimited

    # Paths
    input_csv: Path = PROJECT_DIR / "prospect_scores_25003.csv"
    output_csv: Path = PROJECT_DIR / "phase3_email_drafts.csv"
    checkpoint_csv: Path = PROJECT_DIR / "phase3_checkpoint.csv"
    checkpoint_jsonl: Path = PROJECT_DIR / "phase3_checkpoint.jsonl"
    progress_json: Path = PROJECT_DIR / "phase3_progress.json"
    summary_json: Path = PROJECT_DIR / "phase3_summary.json"

    # Flags
    dry_run: bool = False  # research only, skip email generation
    reset_checkpoint: bool = False  # delete checkpoint files before starting


def load_config() -> Phase3Config:
    """Build config from environment variables, then override with CLI args."""
    cfg = Phase3Config(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        model=os.getenv("PHASE3_MODEL", "claude-sonnet-4-6"),
        concurrency=min(int(os.getenv("PHASE3_CONCURRENCY", "5")), 20),
        claude_rate=float(os.getenv("PHASE3_CLAUDE_RATE", "0.75")),
        min_quality=int(os.getenv("PHASE3_MIN_QUALITY", "30")),
        max_prospects=int(os.getenv("PHASE3_MAX_PROSPECTS", "0")),
    )

    parser = argparse.ArgumentParser(
        description="Phase 3: AI-Contextualized Personalized Cold Email Outreach",
    )
    parser.add_argument(
        "--tiers", nargs="+", default=None,
        help="Tiers to process (default: Platinum Gold)",
    )
    parser.add_argument("--max", type=int, default=None, help="Max prospects to process")
    parser.add_argument("--dry-run", action="store_true", help="Research only, skip email generation")
    parser.add_argument("--min-quality", type=int, default=None, help="Min research quality score (0-100)")
    parser.add_argument("--concurrency", type=int, default=None, help="Max concurrent prospects")
    parser.add_argument("--model", type=str, default=None, help="Claude model to use")
    parser.add_argument("--input", type=str, default=None, help="Input CSV path")
    parser.add_argument(
        "--backend", type=str, default=None,
        choices=["api", "claude-code"],
        help="Backend: 'api' (Anthropic API) or 'claude-code' (claude -p CLI, default)",
    )
    parser.add_argument(
        "--reset-checkpoint", action="store_true",
        help="Delete checkpoint files before starting (use after a failed run)",
    )

    args = parser.parse_args()

    if args.tiers is not None:
        cfg.tiers = args.tiers
    if args.max is not None:
        cfg.max_prospects = args.max
    if args.dry_run:
        cfg.dry_run = True
    if args.min_quality is not None:
        cfg.min_quality = args.min_quality
    if args.concurrency is not None:
        cfg.concurrency = min(args.concurrency, 20)
    if args.model is not None:
        cfg.model = args.model
    if args.input is not None:
        cfg.input_csv = Path(args.input)
    if args.backend is not None:
        cfg.backend = args.backend
    if args.reset_checkpoint:
        cfg.reset_checkpoint = True

    # Validate
    if cfg.backend == "api" and not cfg.anthropic_api_key:
        print("ERROR: ANTHROPIC_API_KEY not set (required for --backend api).", file=sys.stderr)
        sys.exit(1)
    if not cfg.input_csv.exists():
        print(f"ERROR: Input file not found: {cfg.input_csv}", file=sys.stderr)
        sys.exit(1)

    return cfg
