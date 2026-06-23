#!/usr/bin/env python3
"""
Run 5,000 LinkedIn searches via Apify, collect results, score them,
and output an enriched dataset with LinkedIn URLs and confidence scores.

Uses the new query format: "FirstName" "LastName" "Company" "LinkedIn"
"""

import json
import time
import csv
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from collections import defaultdict

from linkedin_confidence_scorer import (
    compute_confidence_score,
    parse_query_fields,
)

APIFY_TOKEN = os.environ["APIFY_TOKEN"]
ACTOR_ID = "apify~google-search-scraper"
BASE_URL = "https://api.apify.com/v2"
BATCH_SIZE = 500
POLL_INTERVAL = 15
MAX_POLLS = 200

BASE_DIR = "/Users/nathaniel/Desktop/Cl3"
QUERIES_FILE = os.path.join(BASE_DIR, "linkedin_search_queries.txt")
SOURCE_FILE = os.path.join(BASE_DIR, "All WE contacts_vAIM_1.0.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "linkedin_5000_enriched.csv")
PROGRESS_FILE = os.path.join(BASE_DIR, "search_5000_progress.json")


def api_request(method, path, body=None):
    """Make an API request to Apify."""
    url = f"{BASE_URL}{path}?token={APIFY_TOKEN}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        error_body = e.read().decode()
        print(f"  API Error {e.code}: {error_body[:200]}")
        raise


def start_batch(queries):
    """Start a Google Search scraper run."""
    input_data = {
        "queries": "\n".join(queries),
        "maxPagesPerQuery": 1,
        "mobileResults": False,
        "countryCode": "us",
        "languageCode": "",
        "saveHtml": False,
        "saveHtmlToKeyValueStore": False,
        "includeUnfilteredResults": False,
    }
    result = api_request("POST", f"/acts/{ACTOR_ID}/runs", input_data)
    return result["data"]["id"], result["data"].get("defaultDatasetId", "")


def poll_run(run_id):
    """Poll until terminal state."""
    for i in range(MAX_POLLS):
        result = api_request("GET", f"/actor-runs/{run_id}")
        status = result["data"]["status"]
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            return result["data"]
        if i % 4 == 0:
            msg = result["data"].get("statusMessage", "")[:80]
            print(f"    [{run_id[:8]}] {status} - {msg}")
        time.sleep(POLL_INTERVAL)
    return None


def get_dataset_items(dataset_id, limit=1000, offset=0):
    """Fetch dataset items."""
    url = (f"{BASE_URL}/datasets/{dataset_id}/items"
           f"?token={APIFY_TOKEN}&limit={limit}&offset={offset}&format=json&clean=true")
    req = Request(url)
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"batches": {}}


def save_progress(progress):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def main():
    print("=" * 70)
    print("LinkedIn Search: 5,000 Queries via Apify")
    print("=" * 70)

    # Load queries
    with open(QUERIES_FILE) as f:
        all_queries = [line.strip() for line in f if line.strip()]
    queries = all_queries[:5000]
    print(f"Total queries to run: {len(queries)}")

    num_batches = (len(queries) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Batches: {num_batches} x {BATCH_SIZE}")
    print()

    progress = load_progress()

    # Phase 1: Start all batches
    print("PHASE 1: Starting batches...")
    for batch_num in range(num_batches):
        batch_key = str(batch_num)
        if batch_key in progress["batches"] and progress["batches"][batch_key].get("run_id"):
            print(f"  Batch {batch_num}: already started ({progress['batches'][batch_key]['run_id'][:8]}...)")
            continue

        start = batch_num * BATCH_SIZE
        end = min(start + BATCH_SIZE, len(queries))
        batch_queries = queries[start:end]

        print(f"  Starting batch {batch_num} ({len(batch_queries)} queries)...", end=" ")
        run_id, dataset_id = start_batch(batch_queries)
        print(f"run_id={run_id[:12]}")

        progress["batches"][batch_key] = {
            "run_id": run_id,
            "dataset_id": dataset_id,
            "status": "RUNNING",
        }
        save_progress(progress)
        time.sleep(2)

    print()

    # Phase 2: Poll all batches to completion
    print("PHASE 2: Waiting for completion...")
    for batch_key, info in sorted(progress["batches"].items(), key=lambda x: int(x[0])):
        if info.get("status") == "SUCCEEDED":
            print(f"  Batch {batch_key}: already SUCCEEDED")
            continue

        run_id = info["run_id"]
        print(f"  Polling batch {batch_key} ({run_id[:12]})...")
        run_data = poll_run(run_id)

        if run_data is None:
            print(f"    WARNING: Batch {batch_key} timed out!")
            continue

        status = run_data["status"]
        dataset_id = run_data.get("defaultDatasetId", info.get("dataset_id", ""))
        progress["batches"][batch_key]["status"] = status
        progress["batches"][batch_key]["dataset_id"] = dataset_id
        save_progress(progress)
        print(f"    Batch {batch_key}: {status}")

    print()

    # Phase 3: Collect results from all datasets
    print("PHASE 3: Collecting results...")
    all_results = []  # list of dicts per query

    for batch_key, info in sorted(progress["batches"].items(), key=lambda x: int(x[0])):
        if info.get("status") != "SUCCEEDED":
            print(f"  Skipping batch {batch_key} (status: {info.get('status')})")
            continue

        dataset_id = info["dataset_id"]
        print(f"  Fetching batch {batch_key} (dataset {dataset_id})...")
        offset = 0

        while True:
            items = get_dataset_items(dataset_id, limit=1000, offset=offset)
            if not items:
                break

            for item in items:
                query = item.get("searchQuery", {}).get("term", "")
                organic = item.get("organicResults", [])

                # Extract LinkedIn URLs from organic results
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

                all_results.append({
                    "query": query,
                    "linkedin_matches": linkedin_matches,
                    "total_organic": len(organic),
                })

            if len(items) < 1000:
                break
            offset += 1000

    print(f"  Collected {len(all_results)} query results")
    print()

    # Phase 4: Score and build enriched output
    print("PHASE 4: Scoring and building output...")

    # Load source data for row matching
    source_rows = []
    with open(SOURCE_FILE, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= 5000:
                break
            source_rows.append(row)
    print(f"  Loaded {len(source_rows)} source rows")

    # Build query -> result mapping
    query_result_map = {}
    for result in all_results:
        query_result_map[result["query"]] = result

    # Process each row
    enriched_rows = []
    match_count = 0

    for i, source_row in enumerate(source_rows):
        # Reconstruct query for this row
        first = source_row.get("First Name", "").strip()
        last = source_row.get("Last Name", "").strip()
        company = source_row.get("Business name", "").strip()

        parts = []
        if first:
            parts.append(f'"{first}"')
        if last:
            parts.append(f'"{last}"')
        if company:
            parts.append(f'"{company}"')
        parts.append('"LinkedIn"')
        query = ' '.join(parts)

        # Find result for this query
        result = query_result_map.get(query, None)

        best_url = ""
        best_title = ""
        best_description = ""
        best_score = 0
        best_signals = ""

        if result and result["linkedin_matches"]:
            fields = parse_query_fields(query)
            source_data = {
                "source_city": source_row.get("City", ""),
                "source_state": source_row.get("State", ""),
                "middle_name": source_row.get("Middle Name", ""),
            }

            for match in result["linkedin_matches"]:
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

            if best_score >= 80:
                match_count += 1

        # Build enriched row (source columns + new columns)
        enriched = dict(source_row)
        enriched["LinkedIn_URL"] = best_url
        enriched["LinkedIn_Title"] = best_title
        enriched["LinkedIn_Description"] = best_description
        enriched["Confidence_Score"] = best_score
        enriched["Match_Signals"] = best_signals

        enriched_rows.append(enriched)

    # Write output
    if enriched_rows:
        fieldnames = list(enriched_rows[0].keys())
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(enriched_rows)

    print(f"  Written: {OUTPUT_FILE}")
    print(f"  Total rows: {len(enriched_rows)}")
    print(f"  High confidence matches (>=80%): {match_count}")
    print(f"  Match rate: {match_count / max(len(enriched_rows), 1) * 100:.1f}%")
    print()
    print("DONE!")


if __name__ == "__main__":
    main()
