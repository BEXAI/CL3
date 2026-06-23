#!/usr/bin/env python3
"""
Merge enrichment results back into linkedin_master_25003.csv.

Reads:
  - linkedin_master_25003.csv (25,003 rows, 148 columns)
  - ultra_hnw_linkedin_results.csv (enrichment results from WebSearch)

Updates master rows where the new enrichment score exceeds the existing score.

Outputs:
  - linkedin_master_25003_enriched.csv (updated master)
  - enrichment_merge_summary.json (stats)
"""

import csv
import json
import os
import sys

BASE_DIR = "/Users/nathaniel/Desktop/Cl3"
MASTER_FILE = os.path.join(BASE_DIR, "linkedin_master_25003.csv")
ENRICHMENT_FILE = os.path.join(BASE_DIR, "ultra_hnw_linkedin_results.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "linkedin_master_25003_enriched.csv")
SUMMARY_FILE = os.path.join(BASE_DIR, "enrichment_merge_summary.json")


def safe_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def main():
    print("=" * 70)
    print("MERGE ENRICHMENT RESULTS INTO MASTER")
    print("=" * 70)

    # Load master
    print("\n[1/4] Loading master CSV...")
    if not os.path.exists(MASTER_FILE):
        print(f"  ERROR: {MASTER_FILE} not found")
        sys.exit(1)

    with open(MASTER_FILE, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        master_fieldnames = list(reader.fieldnames)
        master_rows = list(reader)

    print(f"  Loaded {len(master_rows)} master rows, {len(master_fieldnames)} columns")

    # Build lookup by name (First Name + Last Name) since enrichment results
    # use name-based matching. Also index by WE Record ID if available.
    name_to_indices = {}
    for i, row in enumerate(master_rows):
        first = row.get("First Name", "").strip().lower()
        last = row.get("Last Name", "").strip().lower()
        if first and last:
            key = f"{first}|{last}"
            name_to_indices.setdefault(key, []).append(i)

    # Load enrichment results
    print("\n[2/4] Loading enrichment results...")
    if not os.path.exists(ENRICHMENT_FILE):
        print(f"  WARNING: {ENRICHMENT_FILE} not found")
        print("  Proceeding with master data only (no new enrichment)")
        enrichment_rows = []
    else:
        with open(ENRICHMENT_FILE, encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            enrichment_rows = list(reader)
        print(f"  Loaded {len(enrichment_rows)} enrichment results")

    # Merge
    print("\n[3/4] Merging results...")
    updates = 0
    new_matches = 0
    improved_matches = 0

    for erow in enrichment_rows:
        first = erow.get("First Name", "").strip().lower()
        last = erow.get("Last Name", "").strip().lower()
        new_url = erow.get("LinkedIn_URL", "").strip()
        new_score = safe_float(erow.get("Confidence_Score", 0))

        if not new_url or new_score < 40:
            continue

        key = f"{first}|{last}"
        indices = name_to_indices.get(key, [])

        for idx in indices:
            existing_score = safe_float(master_rows[idx].get("Confidence_Score", 0))

            if new_score > existing_score:
                old_url = master_rows[idx].get("LinkedIn_URL", "").strip()
                master_rows[idx]["LinkedIn_URL"] = new_url
                master_rows[idx]["LinkedIn_Title"] = erow.get("LinkedIn_Title", "")
                master_rows[idx]["LinkedIn_Description"] = ""
                master_rows[idx]["Confidence_Score"] = str(int(new_score))
                master_rows[idx]["Match_Signals"] = "websearch_enrichment"
                master_rows[idx]["Match_Pass"] = "targeted_enrichment"

                updates += 1
                if not old_url:
                    new_matches += 1
                else:
                    improved_matches += 1

    print(f"  Total updates: {updates}")
    print(f"    New matches (was empty): {new_matches}")
    print(f"    Improved matches: {improved_matches}")

    # Write output
    print("\n[4/4] Writing output...")
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=master_fieldnames)
        writer.writeheader()
        writer.writerows(master_rows)

    print(f"  Written: {OUTPUT_FILE}")

    # Compute final stats
    total = len(master_rows)
    final_matched = sum(1 for r in master_rows if r.get("LinkedIn_URL", "").strip())
    final_high = sum(1 for r in master_rows if safe_float(r.get("Confidence_Score", 0)) >= 80)
    final_medium = sum(1 for r in master_rows if 40 <= safe_float(r.get("Confidence_Score", 0)) < 80)

    summary = {
        "total_rows": total,
        "enrichment_results_loaded": len(enrichment_rows),
        "total_updates": updates,
        "new_matches": new_matches,
        "improved_matches": improved_matches,
        "final_with_url": final_matched,
        "final_high_confidence": final_high,
        "final_medium_confidence": final_medium,
        "final_match_rate_pct": round(final_matched / max(total, 1) * 100, 1),
        "final_high_conf_pct": round(final_high / max(total, 1) * 100, 1),
    }

    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"  Written: {SUMMARY_FILE}")

    print("\n" + "=" * 70)
    print("MERGE SUMMARY")
    print("=" * 70)
    print(f"  Total rows:              {total}")
    print(f"  Updates applied:         {updates}")
    print(f"  Final with LinkedIn URL: {final_matched} ({summary['final_match_rate_pct']}%)")
    print(f"  Final high confidence:   {final_high} ({summary['final_high_conf_pct']}%)")
    print(f"  Final medium confidence: {final_medium}")
    print()


if __name__ == "__main__":
    main()
