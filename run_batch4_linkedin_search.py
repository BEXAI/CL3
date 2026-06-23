#!/usr/bin/env python3
"""LinkedIn Search: Batch 4 -- Rows 15001 to 20000."""

from pathlib import Path
from pipeline_core import BatchConfig, run_pipeline

BASE_DIR = Path(__file__).resolve().parent

config = BatchConfig(
    batch_name="Batch 4",
    row_start=15000,
    row_end=20000,
    source_file=str(BASE_DIR / "All WE contacts_vAIM_1.0.csv"),
    enriched_file=str(BASE_DIR / "linkedin_batch4_enriched.csv"),
    output_file=str(BASE_DIR / "linkedin_batch4_final.csv"),
    progress_file=str(BASE_DIR / "batch4_progress.json"),
    summary_file=str(BASE_DIR / "batch4_summary.json"),
)

if __name__ == "__main__":
    run_pipeline(config)
