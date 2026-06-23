#!/usr/bin/env python3
"""LinkedIn Search: Batch 5 -- Rows 20001 to 25003."""

from pathlib import Path
from pipeline_core import BatchConfig, run_pipeline

BASE_DIR = Path(__file__).resolve().parent

config = BatchConfig(
    batch_name="Batch 5",
    row_start=20000,
    row_end=25003,
    source_file=str(BASE_DIR / "All WE contacts_vAIM_1.0.csv"),
    enriched_file=str(BASE_DIR / "linkedin_batch5_enriched.csv"),
    output_file=str(BASE_DIR / "linkedin_batch5_final.csv"),
    progress_file=str(BASE_DIR / "batch5_progress.json"),
    summary_file=str(BASE_DIR / "batch5_summary.json"),
)

if __name__ == "__main__":
    run_pipeline(config)
