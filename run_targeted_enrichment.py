#!/usr/bin/env python3
"""
Targeted LinkedIn Enrichment for 3,134 High-Value Prospects.

These prospects did not match in the Phase 1 multi-pass search (5 passes).
This script runs NEW search strategies through Apify's google-search-scraper:

Strategy A: site:linkedin.com/in/ "First Last" (direct site-restricted search)
Strategy B: "First" "Last" LinkedIn profile (without quotes around LinkedIn)
Strategy C: "First" "Last" "Company" site:linkedin.com (site-restricted with company)

Architecture:
- Reads agentic_enrichment_input.csv (3,134 rows with 148 columns)
- Generates 3 search strategies per row
- Processes in batches of 500 through Apify google-search-scraper
- Scores results using linkedin_confidence_scorer
- Outputs targeted_enrichment_results.csv (all rows with updated LinkedIn columns)
- Outputs targeted_enrichment_summary.json (stats on new matches)
"""

import csv
import itertools
import json
import os
import sys
import time
from collections import defaultdict

# Import from existing pipeline infrastructure
from pipeline_core import (
    BatchConfig,
    api_request,
    load_progress,
    sanitize_field,
    save_progress,
    start_batch,
    poll_batches_concurrent,
    get_dataset_items,
)

from linkedin_confidence_scorer import (
    compute_confidence_score,
    parse_query_fields,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = "/Users/nathaniel/Desktop/Cl3"
INPUT_FILE = os.path.join(BASE_DIR, "agentic_enrichment_input.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "targeted_enrichment_results.csv")
SUMMARY_FILE = os.path.join(BASE_DIR, "targeted_enrichment_summary.json")
PROGRESS_FILE = os.path.join(BASE_DIR, "targeted_enrichment_progress.json")

BATCH_SIZE = 500
HIGH_CONFIDENCE_THRESHOLD = 80

# ---------------------------------------------------------------------------
# Query Generation Strategies
# ---------------------------------------------------------------------------


def generate_strategy_a_query(row):
    """
    Strategy A: site:linkedin.com/in/ "First Last"
    Direct site-restricted search with full name in quotes.
    """
    first = sanitize_field(row.get("First Name", ""))
    last = sanitize_field(row.get("Last Name", ""))
    if not first or not last:
        return None
    return f'site:linkedin.com/in/ "{first} {last}"'


def generate_strategy_b_query(row):
    """
    Strategy B: "First" "Last" LinkedIn profile
    Individual quoted names + LinkedIn profile (without quotes).
    """
    first = sanitize_field(row.get("First Name", ""))
    last = sanitize_field(row.get("Last Name", ""))
    if not first or not last:
        return None
    return f'"{first}" "{last}" LinkedIn profile'


def generate_strategy_c_query(row):
    """
    Strategy C: "First" "Last" "Company" site:linkedin.com
    Site-restricted with company name for disambiguation.
    """
    first = sanitize_field(row.get("First Name", ""))
    last = sanitize_field(row.get("Last Name", ""))
    company = sanitize_field(row.get("Business name", ""))
    if not first or not last or not company:
        return None
    return f'"{first}" "{last}" "{company}" site:linkedin.com'


# ---------------------------------------------------------------------------
# Apify Pass Execution
# ---------------------------------------------------------------------------


def run_apify_pass(pass_name, queries_list, progress, config):
    """
    Run a list of queries through Apify google-search-scraper.
    Returns {query: [matches]}.
    Reuses the pipeline_core infrastructure.
    """
    if not queries_list:
        print(f"  No queries for {pass_name}")
        return {}

    num_batches = (len(queries_list) + config.batch_size - 1) // config.batch_size
    print(f"  {pass_name}: {len(queries_list)} queries in {num_batches} batches")

    pass_prog = progress.setdefault(pass_name, {"batches": {}})

    # Start batches
    for batch_num in range(num_batches):
        batch_key = str(batch_num)
        if batch_key in pass_prog["batches"] and pass_prog["batches"][batch_key].get("run_id"):
            print(f"    Batch {batch_num}: already started")
            continue
        start_idx = batch_num * config.batch_size
        end_idx = min(start_idx + config.batch_size, len(queries_list))
        batch_queries = queries_list[start_idx:end_idx]
        print(f"    Starting batch {batch_num} ({len(batch_queries)} queries)...", end=" ")
        run_id, dataset_id = start_batch(batch_queries)
        print(f"run_id={run_id[:12]}")
        pass_prog["batches"][batch_key] = {
            "run_id": run_id,
            "dataset_id": dataset_id,
            "status": "RUNNING",
        }
        save_progress(progress, config.progress_file)
        time.sleep(2)

    # Poll to completion (round-robin concurrent)
    poll_batches_concurrent(pass_prog, config)
    save_progress(progress, config.progress_file)

    # Collect results
    query_results = {}
    for batch_key, info in sorted(pass_prog["batches"].items(), key=lambda x: int(x[0])):
        if info.get("status") != "SUCCEEDED":
            continue
        dataset_id = info["dataset_id"]
        offset = 0
        while True:
            items = get_dataset_items(dataset_id, limit=1000, offset=offset)
            if not items:
                break
            for item in items:
                query = item.get("searchQuery", {}).get("term", "")
                organic = item.get("organicResults", [])
                linkedin_matches = []
                for result in organic:
                    url = result.get("url", "")
                    if "linkedin.com/in/" in url:
                        linkedin_matches.append({
                            "linkedin_url": url,
                            "title": result.get("title", ""),
                            "description": result.get("description", ""),
                            "position": result.get("position", ""),
                        })
                query_results[query] = linkedin_matches
            if len(items) < 1000:
                break
            offset += 1000

    return query_results


def score_results_for_row(source_row, linkedin_matches, query):
    """
    Score all LinkedIn matches for a single source row. Returns best match.

    This is a specialized version that handles the new query formats.
    For Strategy A/B/C, we need to parse the query appropriately.
    """
    if not linkedin_matches:
        return "", "", "", 0, ""

    # Parse query to extract fields for scoring
    # Strategy A: site:linkedin.com/in/ "First Last"
    # Strategy B: "First" "Last" LinkedIn profile
    # Strategy C: "First" "Last" "Company" site:linkedin.com

    # Extract quoted strings
    import re
    quoted = re.findall(r'"([^"]+)"', query)

    fields = {"first_name": "", "last_name": "", "company": ""}

    if "site:linkedin.com/in/" in query:
        # Strategy A: "First Last" is in quotes
        if quoted and " " in quoted[0]:
            name_parts = quoted[0].split()
            fields["first_name"] = name_parts[0]
            fields["last_name"] = name_parts[-1]
    elif "LinkedIn profile" in query:
        # Strategy B: "First" "Last" LinkedIn profile
        if len(quoted) >= 2:
            fields["first_name"] = quoted[0]
            fields["last_name"] = quoted[1]
    elif "site:linkedin.com" in query:
        # Strategy C: "First" "Last" "Company" site:linkedin.com
        if len(quoted) >= 2:
            fields["first_name"] = quoted[0]
            fields["last_name"] = quoted[1]
        if len(quoted) >= 3:
            fields["company"] = quoted[2]

    # Fallback: try to parse as standard format
    if not fields["first_name"] or not fields["last_name"]:
        fields = parse_query_fields(query)

    source_data = {
        "source_city": source_row.get("City", ""),
        "source_state": source_row.get("State", ""),
        "middle_name": source_row.get("Middle Name", ""),
    }

    best_url = ""
    best_title = ""
    best_description = ""
    best_score = 0
    best_signals = ""

    for match in linkedin_matches:
        row_data = {
            "profile_title": match["title"],
            "description": match["description"],
            "linkedin_url": match["linkedin_url"],
            "result_position": match["position"],
        }
        score, signals = compute_confidence_score(row_data, fields, source_data)
        if score > best_score:
            best_score = score
            best_url = match["linkedin_url"]
            best_title = match["title"]
            best_description = match["description"]
            best_signals = "; ".join(
                f"{k}={v['score']}({v['detail']})" for k, v in signals.items()
            )

    return best_url, best_title, best_description, best_score, best_signals


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------


def main():
    print("=" * 70)
    print("TARGETED LinkedIn Enrichment for 3,134 High-Value Prospects")
    print("=" * 70)
    print()
    print("NEW Search Strategies:")
    print("  Strategy A: site:linkedin.com/in/ \"First Last\"")
    print("  Strategy B: \"First\" \"Last\" LinkedIn profile")
    print("  Strategy C: \"First\" \"Last\" \"Company\" site:linkedin.com")
    print()

    # Load source data
    print("[1/5] Loading agentic_enrichment_input.csv...")
    if not os.path.exists(INPUT_FILE):
        print(f"  ERROR: Input file not found: {INPUT_FILE}")
        sys.exit(1)

    source_rows = []
    with open(INPUT_FILE, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            source_rows.append(row)

    total = len(source_rows)
    if total == 0:
        print("  ERROR: No source rows loaded.")
        sys.exit(1)

    print(f"  Loaded {total} source rows")
    print()

    # Create config
    config = BatchConfig(
        batch_name="targeted_enrichment",
        row_start=0,
        row_end=total,
        source_file=INPUT_FILE,
        enriched_file=OUTPUT_FILE,
        output_file=OUTPUT_FILE,
        progress_file=PROGRESS_FILE,
        summary_file=SUMMARY_FILE,
        batch_size=BATCH_SIZE,
    )

    progress = load_progress(PROGRESS_FILE)

    # Generate queries for each strategy
    print("[2/5] Generating queries for 3 strategies...")

    query_to_indices = defaultdict(list)
    all_queries = []

    for i, row in enumerate(source_rows):
        # Strategy A
        query_a = generate_strategy_a_query(row)
        if query_a:
            query_to_indices[query_a].append((i, "strategy_a"))
            all_queries.append(query_a)

        # Strategy B
        query_b = generate_strategy_b_query(row)
        if query_b:
            query_to_indices[query_b].append((i, "strategy_b"))
            all_queries.append(query_b)

        # Strategy C
        query_c = generate_strategy_c_query(row)
        if query_c:
            query_to_indices[query_c].append((i, "strategy_c"))
            all_queries.append(query_c)

    unique_queries = list(dict.fromkeys(all_queries))
    print(f"  Total queries generated: {len(all_queries)}")
    print(f"  Unique queries: {len(unique_queries)}")
    print()

    # Run queries through Apify
    print("[3/5] Running queries through Apify...")
    results = run_apify_pass("targeted_enrichment", unique_queries, progress, config)
    print()

    # Score results and build best matches per row
    print("[4/5] Scoring results and selecting best matches...")
    best_per_row = {}

    # Initialize all rows with empty results
    for i in range(total):
        best_per_row[i] = {
            "url": "",
            "title": "",
            "description": "",
            "score": 0,
            "signals": "",
            "strategy": "",
        }

    # Process each query and update best matches
    for query, indices_list in query_to_indices.items():
        matches = results.get(query, [])

        for i, strategy in indices_list:
            row = source_rows[i]
            url, title, desc, score, signals = score_results_for_row(row, matches, query)

            # Update if this is a better match
            if score > best_per_row[i]["score"]:
                best_per_row[i] = {
                    "url": url,
                    "title": title,
                    "description": desc,
                    "score": score,
                    "signals": signals,
                    "strategy": strategy,
                }

    # Count results
    high_conf = sum(1 for i in range(total) if best_per_row[i]["score"] >= HIGH_CONFIDENCE_THRESHOLD)
    medium_conf = sum(1 for i in range(total) if 40 <= best_per_row[i]["score"] < HIGH_CONFIDENCE_THRESHOLD)
    low_conf = sum(1 for i in range(total) if 0 < best_per_row[i]["score"] < 40)
    no_match = sum(1 for i in range(total) if best_per_row[i]["score"] == 0)

    print(f"  High confidence (>={HIGH_CONFIDENCE_THRESHOLD}%): {high_conf} ({high_conf/total*100:.1f}%)")
    print(f"  Medium confidence (40-79%): {medium_conf} ({medium_conf/total*100:.1f}%)")
    print(f"  Low confidence (<40%): {low_conf} ({low_conf/total*100:.1f}%)")
    print(f"  No match: {no_match} ({no_match/total*100:.1f}%)")
    print()

    # Strategy breakdown
    strategy_stats = defaultdict(int)
    for i in range(total):
        if best_per_row[i]["score"] >= HIGH_CONFIDENCE_THRESHOLD:
            strategy_stats[best_per_row[i]["strategy"]] += 1

    print("  High-confidence matches by strategy:")
    for strategy in ["strategy_a", "strategy_b", "strategy_c"]:
        count = strategy_stats.get(strategy, 0)
        print(f"    {strategy}: {count}")
    print()

    # Write output CSV
    print("[5/5] Writing output files...")

    # Preserve ALL 148 original columns
    fieldnames_base = list(source_rows[0].keys())

    # Update or add LinkedIn columns
    linkedin_columns = [
        "LinkedIn_URL",
        "LinkedIn_Title",
        "LinkedIn_Description",
        "Confidence_Score",
        "Match_Signals",
    ]

    # Remove existing LinkedIn columns from base (if present) to avoid duplicates
    fieldnames_base = [f for f in fieldnames_base if f not in linkedin_columns]

    # Build final fieldnames
    output_fieldnames = fieldnames_base + linkedin_columns

    output_rows = []
    for i, row in enumerate(source_rows):
        out_row = dict(row)
        out_row["LinkedIn_URL"] = best_per_row[i]["url"]
        out_row["LinkedIn_Title"] = best_per_row[i]["title"]
        out_row["LinkedIn_Description"] = best_per_row[i]["description"]
        out_row["Confidence_Score"] = best_per_row[i]["score"]
        out_row["Match_Signals"] = best_per_row[i]["signals"]
        output_rows.append(out_row)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"  Written: {OUTPUT_FILE} ({total} rows)")

    # Write summary JSON
    summary = {
        "total_rows": total,
        "unique_queries": len(unique_queries),
        "total_queries_generated": len(all_queries),
        "high_confidence_matches": high_conf,
        "medium_confidence_matches": medium_conf,
        "low_confidence_matches": low_conf,
        "no_match": no_match,
        "match_rate_pct": round(high_conf / total * 100, 1),
        "strategy_breakdown": dict(strategy_stats),
        "search_strategies": [
            "Strategy A: site:linkedin.com/in/ \"First Last\"",
            "Strategy B: \"First\" \"Last\" LinkedIn profile",
            "Strategy C: \"First\" \"Last\" \"Company\" site:linkedin.com",
        ],
    }

    with open(SUMMARY_FILE, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"  Written: {SUMMARY_FILE}")
    print()

    # Print summary
    print("=" * 70)
    print("TARGETED ENRICHMENT SUMMARY")
    print("=" * 70)
    print(f"  Total prospects:                  {total}")
    print(f"  Unique queries generated:         {len(unique_queries)}")
    print()
    print(f"  High confidence matches (>=80%):  {high_conf} ({high_conf/total*100:.1f}%)")
    print(f"  Medium confidence (40-79%):       {medium_conf} ({medium_conf/total*100:.1f}%)")
    print(f"  Low/no match:                     {low_conf + no_match} ({(low_conf+no_match)/total*100:.1f}%)")
    print()
    print(f"  New matches found:                {high_conf}")
    print(f"  Match rate:                       {summary['match_rate_pct']}%")
    print()
    print("DONE!")


if __name__ == "__main__":
    main()
