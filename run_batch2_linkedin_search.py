#!/usr/bin/env python3
"""LinkedIn Search: Batch 2 -- Rows 5001 to 10000."""

from pathlib import Path
from pipeline_core import BatchConfig, run_pipeline

BASE_DIR = Path(__file__).resolve().parent

config = BatchConfig(
    batch_name="Batch 2",
    row_start=5000,
    row_end=10000,
    source_file=str(BASE_DIR / "All WE contacts_vAIM_1.0.csv"),
    enriched_file=str(BASE_DIR / "linkedin_batch2_enriched.csv"),
    output_file=str(BASE_DIR / "linkedin_batch2_final.csv"),
    progress_file=str(BASE_DIR / "batch2_progress.json"),
    summary_file=str(BASE_DIR / "batch2_summary.json"),
)

if __name__ == "__main__":
    run_pipeline(config)
