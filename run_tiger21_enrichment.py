#!/usr/bin/env python3
"""
Phase 1 LinkedIn enrichment for TIGER 21 chairs.

Reads tiger21_chairs.csv, maps columns to the standard pipeline format,
runs the full 5-pass Apify Google Search pipeline, then merges the
LinkedIn_URL column back into the original CSV.
"""

import csv
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Load .env BEFORE any pipeline imports (pipeline_core checks APIFY_TOKEN at import time)
load_dotenv(BASE_DIR / ".env")

TIGER21_CSV = BASE_DIR / "tiger21_chairs.csv"
MAPPED_SOURCE = BASE_DIR / "tiger21_source_mapped.csv"
ENRICHED_CHECKPOINT = str(BASE_DIR / "tiger21_enriched_checkpoint.csv")
ENRICHED_OUTPUT = str(BASE_DIR / "tiger21_enriched_output.csv")
PROGRESS_FILE = str(BASE_DIR / "tiger21_search_progress.json")
SUMMARY_FILE = str(BASE_DIR / "tiger21_search_summary.json")


def create_mapped_source():
    """Read tiger21_chairs.csv and write a mapped CSV with columns the pipeline expects."""
    rows = []
    with open(TIGER21_CSV, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        original_fieldnames = list(reader.fieldnames)
        for row in reader:
            rows.append(row)

    # Map columns: pipeline expects "Business name", "State", "Middle Name", "Business name 2"
    # TIGER21 has: "Company", "State/Country"
    # Note: Company is "TIGER 21" for all rows — useless for search, but Pass 1 will
    # naturally fail and the multi-pass system will recover via Passes 2-3.
    mapped_fieldnames = [
        "First Name", "Last Name", "Title", "Business name", "City", "State",
        "Email", "Groups", "Source", "Middle Name", "Business name 2",
    ]

    mapped_rows = []
    for row in rows:
        mapped = {
            "First Name": row.get("First Name", ""),
            "Last Name": row.get("Last Name", ""),
            "Title": row.get("Title", ""),
            "Business name": row.get("Company", ""),
            "City": row.get("City", ""),
            "State": row.get("State/Country", ""),
            "Email": row.get("Email", ""),
            "Groups": row.get("Groups", ""),
            "Source": row.get("Source", ""),
            "Middle Name": "",
            "Business name 2": "",
        }
        mapped_rows.append(mapped)

    with open(MAPPED_SOURCE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=mapped_fieldnames)
        writer.writeheader()
        writer.writerows(mapped_rows)

    print(f"Mapped {len(mapped_rows)} rows to {MAPPED_SOURCE}")
    return len(mapped_rows)


def merge_results_back():
    """Read pipeline output and merge LinkedIn_URL into the original tiger21_chairs.csv."""
    if not os.path.exists(ENRICHED_OUTPUT):
        print(f"ERROR: Pipeline output not found: {ENRICHED_OUTPUT}", file=sys.stderr)
        return

    # Read enriched output (keyed by First Name + Last Name)
    enriched = {}
    with open(ENRICHED_OUTPUT, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row.get("First Name", "").strip(), row.get("Last Name", "").strip())
            enriched[key] = {
                "LinkedIn_URL": row.get("LinkedIn_URL", ""),
                "LinkedIn_Confidence": row.get("Confidence_Score", ""),
                "LinkedIn_Match_Pass": row.get("Match_Pass", ""),
            }

    # Read original CSV
    original_rows = []
    with open(TIGER21_CSV, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        original_fieldnames = list(reader.fieldnames)
        for row in reader:
            original_rows.append(row)

    # Add new columns
    new_fieldnames = original_fieldnames + ["LinkedIn_URL", "LinkedIn_Confidence", "LinkedIn_Match_Pass"]

    matched = 0
    high_conf = 0
    for row in original_rows:
        key = (row.get("First Name", "").strip(), row.get("Last Name", "").strip())
        match = enriched.get(key, {})
        row["LinkedIn_URL"] = match.get("LinkedIn_URL", "")
        row["LinkedIn_Confidence"] = match.get("LinkedIn_Confidence", "")
        row["LinkedIn_Match_Pass"] = match.get("LinkedIn_Match_Pass", "")
        if row["LinkedIn_URL"]:
            matched += 1
            try:
                if int(float(row["LinkedIn_Confidence"])) >= 80:
                    high_conf += 1
            except (ValueError, TypeError):
                pass

    # Write updated original CSV
    with open(TIGER21_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=new_fieldnames)
        writer.writeheader()
        writer.writerows(original_rows)

    print()
    print("=" * 70)
    print("MERGE COMPLETE")
    print("=" * 70)
    print(f"  Updated: {TIGER21_CSV}")
    print(f"  Total rows:           {len(original_rows)}")
    print(f"  LinkedIn URLs found:  {matched}")
    print(f"  High confidence:      {high_conf}")
    print(f"  Match rate:           {matched / max(len(original_rows), 1) * 100:.1f}%")
    print()


def main():
    print("=" * 70)
    print("TIGER 21 Chairs — LinkedIn Enrichment (Phase 1)")
    print("=" * 70)
    print()

    # Step 1: Create mapped source CSV
    total_rows = create_mapped_source()

    # Step 2: Run the full 5-pass pipeline
    from pipeline_core import BatchConfig, run_pipeline

    config = BatchConfig(
        batch_name="tiger21-chairs",
        row_start=0,
        row_end=total_rows,
        source_file=str(MAPPED_SOURCE),
        enriched_file=ENRICHED_CHECKPOINT,
        output_file=ENRICHED_OUTPUT,
        progress_file=PROGRESS_FILE,
        summary_file=SUMMARY_FILE,
        batch_size=500,  # All 118 queries fit in a single batch
        high_confidence_threshold=80,
    )

    run_pipeline(config)

    # Step 3: Merge results back into original tiger21_chairs.csv
    merge_results_back()

    # Clean up temp mapped source
    if MAPPED_SOURCE.exists():
        MAPPED_SOURCE.unlink()
        print(f"Cleaned up temp file: {MAPPED_SOURCE}")

    print()
    print("DONE! tiger21_chairs.csv has been updated with LinkedIn URLs.")


if __name__ == "__main__":
    main()
