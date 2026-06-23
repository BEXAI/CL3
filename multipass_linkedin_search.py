#!/usr/bin/env python3
"""
Multi-Pass LinkedIn Search Pipeline.

Reads linkedin_5000_enriched.csv (Pass 1 results), identifies unmatched rows,
and runs Passes 2-5 with progressively relaxed queries through Apify.
Merges all results into linkedin_5000_final.csv with best match per row.

Pass 1 (already done): "First" "Last" "Company" "LinkedIn"
Pass 2: "First" "Last" "City" "State" "LinkedIn"
Pass 3: "First" "Last" "LinkedIn"
Pass 4: "Nickname" "Last" "City" "State" "LinkedIn"
Pass 5: "First" "Last" "BusinessName2" "LinkedIn"
"""

import csv
import json
import os
import sys
from pathlib import Path

from linkedin_confidence_scorer import (
    compute_confidence_score,
    parse_query_fields,
)
from pipeline_core import (
    BatchConfig,
    generate_pass2_query,
    generate_pass3_query,
    generate_pass4_queries,
    generate_pass5_query,
    load_progress,
    run_apify_pass,
    sanitize_field,
    save_progress,
    score_results_for_row,
)

BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = str(BASE_DIR / "linkedin_5000_enriched.csv")
OUTPUT_FILE = str(BASE_DIR / "linkedin_5000_final.csv")
PROGRESS_FILE = str(BASE_DIR / "multipass_progress.json")

HIGH_CONFIDENCE_THRESHOLD = 80

# Reuse BatchConfig for polling/batch settings only
_config = BatchConfig(
    batch_name="Multipass",
    row_start=0,
    row_end=5000,
    source_file=INPUT_FILE,
    enriched_file=INPUT_FILE,
    output_file=OUTPUT_FILE,
    progress_file=PROGRESS_FILE,
    summary_file=str(BASE_DIR / "multipass_summary.json"),
)


def main():
    print("=" * 70)
    print("Multi-Pass LinkedIn Search Pipeline")
    print("=" * 70)
    print()

    # Load enriched CSV from Pass 1
    print("[1/7] Loading Pass 1 results...")
    if not os.path.exists(INPUT_FILE):
        print(f"  ERROR: {INPUT_FILE} not found. Run run_5000_linkedin_search.py first.",
              file=sys.stderr)
        sys.exit(1)

    rows = []
    with open(INPUT_FILE, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        original_fieldnames = list(reader.fieldnames)
        for row in reader:
            rows.append(row)

    total = len(rows)
    pass1_matched = [
        i for i, r in enumerate(rows)
        if int(float(r.get("Confidence_Score", "0"))) >= HIGH_CONFIDENCE_THRESHOLD
    ]
    unmatched_indices = [i for i in range(total) if i not in set(pass1_matched)]

    print(f"  Total rows: {total}")
    print(f"  Pass 1 high-confidence matches: {len(pass1_matched)}")
    print(f"  Unmatched (need further passes): {len(unmatched_indices)}")
    print()

    # Initialize best match per row from Pass 1 results
    best_per_row = {}
    for i, row in enumerate(rows):
        score = int(float(row.get("Confidence_Score", "0")))
        best_per_row[i] = {
            "url": row.get("LinkedIn_URL", ""),
            "title": row.get("LinkedIn_Title", ""),
            "description": row.get("LinkedIn_Description", ""),
            "score": score,
            "signals": row.get("Match_Signals", ""),
            "pass": "pass1" if score >= HIGH_CONFIDENCE_THRESHOLD else "",
        }

    progress = load_progress(PROGRESS_FILE)
    # Ensure passes sub-dict exists for this script's progress format
    progress.setdefault("passes", {})
    pass_stats = {"pass1": len(pass1_matched)}

    # Helper to run a secondary pass
    def run_secondary_pass(pass_num, pass_label, query_generator, multi=False):
        print(f"[{pass_num}/7] {pass_label}...")
        still_unmatched = [
            i for i in unmatched_indices
            if best_per_row[i]["score"] < HIGH_CONFIDENCE_THRESHOLD
        ]
        print(f"  Candidates: {len(still_unmatched)}")

        query_map = {}
        for i in still_unmatched:
            if multi:
                for query in query_generator(rows[i]):
                    query_map.setdefault(query, []).append(i)
            else:
                query = query_generator(rows[i])
                if query:
                    query_map.setdefault(query, []).append(i)

        print(f"  Unique queries: {len(query_map)}")
        pass_key = f"pass{pass_num}"
        # Use pipeline_core's run_apify_pass for API interaction
        # Store progress under passes sub-key
        pass_progress = progress["passes"]
        results = run_apify_pass(pass_key, list(query_map.keys()), pass_progress, _config)
        save_progress(progress, PROGRESS_FILE)

        new_matches = 0
        for query, indices in query_map.items():
            matches = results.get(query, [])
            for i in indices:
                url, title, desc, score, signals = score_results_for_row(
                    rows[i], matches, query
                )
                if score > best_per_row[i]["score"]:
                    best_per_row[i] = {
                        "url": url, "title": title, "description": desc,
                        "score": score, "signals": signals, "pass": pass_key,
                    }
                    if score >= HIGH_CONFIDENCE_THRESHOLD:
                        new_matches += 1

        pass_stats[pass_key] = new_matches
        print(f"  {pass_label} new high-confidence matches: {new_matches}")
        print()

    run_secondary_pass(2, "Pass 2: Name + City + State", generate_pass2_query)
    run_secondary_pass(3, "Pass 3: Name only", generate_pass3_query)
    run_secondary_pass(4, "Pass 4: Nickname variants", generate_pass4_queries, multi=True)
    run_secondary_pass(5, "Pass 5: Business Name 2 fallback", generate_pass5_query)

    # Re-score with enhanced scorer
    print("[6/7] Re-scoring with enhanced scorer...")
    upgraded = 0
    for i in range(total):
        row = rows[i]
        url = best_per_row[i]["url"] or row.get("LinkedIn_URL", "")
        if not url:
            continue

        first = sanitize_field(row.get("First Name", ""))
        last = sanitize_field(row.get("Last Name", ""))
        company = sanitize_field(row.get("Business name", ""))
        query = (
            f'"{first}" "{last}" "{company}" "LinkedIn"'
            if company
            else f'"{first}" "{last}" "LinkedIn"'
        )
        fields = parse_query_fields(query)
        source_data = {
            "source_city": row.get("City", ""),
            "source_state": row.get("State", ""),
            "middle_name": row.get("Middle Name", ""),
        }
        title = best_per_row[i]["title"] or row.get("LinkedIn_Title", "")
        desc = best_per_row[i]["description"] or row.get("LinkedIn_Description", "")
        row_data = {
            "profile_title": title,
            "description": desc,
            "linkedin_url": url,
            "result_position": "1",
        }
        new_score, signals = compute_confidence_score(row_data, fields, source_data)
        if new_score > best_per_row[i]["score"]:
            if (new_score >= HIGH_CONFIDENCE_THRESHOLD
                    and best_per_row[i]["score"] < HIGH_CONFIDENCE_THRESHOLD):
                upgraded += 1
            best_per_row[i]["score"] = new_score
            best_per_row[i]["signals"] = "; ".join(
                f"{k}={v['score']}({v['detail']})" for k, v in signals.items()
            )
            if not best_per_row[i]["pass"]:
                best_per_row[i]["pass"] = "rescore"

    print(f"  Upgraded {upgraded} rows")
    print()

    # Build final output
    print("[7/7] Building final output...")
    base_fieldnames = [
        f for f in original_fieldnames
        if f not in (
            "LinkedIn_URL", "LinkedIn_Title", "LinkedIn_Description",
            "Confidence_Score", "Match_Signals",
        )
    ]
    output_fieldnames = base_fieldnames + [
        "LinkedIn_URL", "LinkedIn_Title", "LinkedIn_Description",
        "Confidence_Score", "Match_Signals", "Match_Pass",
    ]

    final_high = final_medium = final_low = final_none = 0
    final_rows = []

    for i, row in enumerate(rows):
        best = best_per_row[i]
        out = {f: row.get(f, "") for f in base_fieldnames}
        out["LinkedIn_URL"] = best["url"]
        out["LinkedIn_Title"] = best["title"]
        out["LinkedIn_Description"] = best["description"]
        out["Confidence_Score"] = best["score"]
        out["Match_Signals"] = best["signals"]
        out["Match_Pass"] = best["pass"]
        final_rows.append(out)

        if best["score"] >= HIGH_CONFIDENCE_THRESHOLD:
            final_high += 1
        elif best["score"] >= 40:
            final_medium += 1
        elif best["url"]:
            final_low += 1
        else:
            final_none += 1

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_fieldnames)
        writer.writeheader()
        writer.writerows(final_rows)

    print(f"  Written: {OUTPUT_FILE}")
    print()

    # Summary
    print("=" * 70)
    print("MULTI-PASS PIPELINE SUMMARY")
    print("=" * 70)
    print()
    print(f"  Total rows:                        {total}")
    print()
    print("  Per-pass new high-confidence matches:")
    cumulative = 0
    for pass_name in ["pass1", "pass2", "pass3", "pass4", "pass5"]:
        count = pass_stats.get(pass_name, 0)
        cumulative += count
        pct = cumulative / total * 100
        print(f"    {pass_name}: +{count:>5}  (cumulative: {cumulative:>5} = {pct:.1f}%)")
    print()
    print("  Final distribution:")
    print(f"    High confidence (>=80%):  {final_high:>5}  ({final_high / total * 100:.1f}%)")
    print(f"    Medium (40-79%):          {final_medium:>5}  ({final_medium / total * 100:.1f}%)")
    print(f"    Low (<40% with URL):      {final_low:>5}  ({final_low / total * 100:.1f}%)")
    print(f"    No match:                 {final_none:>5}  ({final_none / total * 100:.1f}%)")
    print()

    summary = {
        "total_rows": total,
        "pass_stats": pass_stats,
        "final_high_confidence": final_high,
        "final_medium": final_medium,
        "final_low_with_url": final_low,
        "final_no_match": final_none,
        "final_match_rate_pct": round(final_high / total * 100, 1),
    }
    with open(_config.summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Summary saved: {_config.summary_file}")
    print()
    print("DONE!")


if __name__ == "__main__":
    main()
