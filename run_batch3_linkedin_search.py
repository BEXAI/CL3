#!/usr/bin/env python3
"""LinkedIn Search: Batch 3 -- Rows 10001 to 15000."""

from pathlib import Path
from pipeline_core import BatchConfig, run_pipeline

BASE_DIR = Path(__file__).resolve().parent

config = BatchConfig(
    batch_name="Batch 3",
    row_start=10000,
    row_end=15000,
    source_file=str(BASE_DIR / "All WE contacts_vAIM_1.0.csv"),
    enriched_file=str(BASE_DIR / "linkedin_batch3_enriched.csv"),
    output_file=str(BASE_DIR / "linkedin_batch3_final.csv"),
    progress_file=str(BASE_DIR / "batch3_progress.json"),
    summary_file=str(BASE_DIR / "batch3_summary.json"),
)

if __name__ == "__main__":
    run_pipeline(config)
