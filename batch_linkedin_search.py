#!/usr/bin/env python3
"""
Batch LinkedIn Profile Search via Apify Google Search Scraper.
Processes queries in batches, polls for completion, and extracts LinkedIn URLs.
"""

import json
import time
import sys
import os
import csv
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from linkedin_confidence_scorer import (
    compute_confidence_score,
    parse_query_fields,
)

APIFY_TOKEN = os.environ["APIFY_TOKEN"]
ACTOR_ID = "apify~google-search-scraper"
BASE_URL = "https://api.apify.com/v2"
BATCH_SIZE = 500  # queries per run
MAX_WAIT_POLLS = 200  # max polls per run (~33 min at 10s intervals)
POLL_INTERVAL = 10  # seconds between polls

INPUT_FILE = "/Users/nathaniel/Desktop/Cl3/linkedin_search_queries.txt"
OUTPUT_FILE = "/Users/nathaniel/Desktop/Cl3/linkedin_results_batch1.csv"
PROGRESS_FILE = "/Users/nathaniel/Desktop/Cl3/batch_progress.json"


def api_request(method, path, body=None):
    """Make an API request to Apify."""
    url = f"{BASE_URL}{path}?token={APIFY_TOKEN}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        error_body = e.read().decode()
        print(f"  API Error {e.code}: {error_body[:200]}")
        raise


def start_batch(queries, batch_num):
    """Start an actor run with a batch of queries."""
    query_text = "\n".join(queries)
    input_data = {
        "queries": query_text,
        "maxPagesPerQuery": 1,
        "mobileResults": False,
        "languageCode": "",
        "saveHtml": False,
        "saveHtmlToKeyValueStore": False,
        "includeUnfilteredResults": False,
    }
    print(f"  Starting batch {batch_num} ({len(queries)} queries)...")
    result = api_request("POST", f"/acts/{ACTOR_ID}/runs", input_data)
    run_id = result["data"]["id"]
    print(f"  Run ID: {run_id}")
    return run_id


def poll_run(run_id):
    """Poll a run until it reaches a terminal state."""
    for i in range(MAX_WAIT_POLLS):
        result = api_request("GET", f"/actor-runs/{run_id}")
        status = result["data"]["status"]
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            return result["data"]
        if i % 6 == 0:  # print every 60s
            print(f"    Run {run_id[:8]}... status: {status} (poll {i+1})")
        time.sleep(POLL_INTERVAL)
    return None


def get_dataset_items(dataset_id, limit=1000, offset=0):
    """Fetch items from a dataset."""
    url = f"{BASE_URL}/datasets/{dataset_id}/items?token={APIFY_TOKEN}&limit={limit}&offset={offset}&format=json&clean=true"
    req = Request(url)
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def extract_linkedin_urls(item):
    """Extract LinkedIn profile URLs from organic results."""
    linkedin_urls = []
    organic = item.get("organicResults", [])
    for result in organic:
        url = result.get("url", "")
        if "linkedin.com/in/" in url:
            linkedin_urls.append({
                "linkedin_url": url,
                "title": result.get("title", ""),
                "description": result.get("description", ""),
                "position": result.get("position", ""),
            })
    return linkedin_urls


def load_progress():
    """Load progress from checkpoint file."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed_batches": [], "run_ids": {}, "total_results": 0}


def save_progress(progress):
    """Save progress to checkpoint file."""
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def main():
    # Load queries
    with open(INPUT_FILE) as f:
        all_queries = [line.strip() for line in f if line.strip()]

    total = len(all_queries)
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Total queries: {total}")
    print(f"Batch size: {BATCH_SIZE}")
    print(f"Number of batches: {num_batches}")
    print(f"Estimated cost: ~${total * 0.005:.2f}")
    print()

    progress = load_progress()

    # Phase 1: Start all batch runs
    print("=" * 60)
    print("PHASE 1: Starting batch runs")
    print("=" * 60)

    run_ids = {}
    for batch_num in range(num_batches):
        batch_key = str(batch_num)
        if batch_key in progress.get("run_ids", {}):
            run_ids[batch_key] = progress["run_ids"][batch_key]
            print(f"  Batch {batch_num} already started: {run_ids[batch_key]}")
            continue

        start = batch_num * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        batch_queries = all_queries[start:end]

        run_id = start_batch(batch_queries, batch_num)
        run_ids[batch_key] = run_id

        progress["run_ids"] = run_ids
        save_progress(progress)

        # Small delay between batch starts to avoid rate limits
        if batch_num < num_batches - 1:
            time.sleep(2)

    print(f"\nAll {num_batches} batches started.")
    print()

    # Phase 2: Poll all runs for completion
    print("=" * 60)
    print("PHASE 2: Waiting for runs to complete")
    print("=" * 60)

    completed_runs = {}
    for batch_key, run_id in run_ids.items():
        if batch_key in progress.get("completed_batches", []):
            print(f"  Batch {batch_key} already completed.")
            continue

        print(f"\n  Polling batch {batch_key} (run {run_id[:12]}...)...")
        run_data = poll_run(run_id)

        if run_data is None:
            print(f"  WARNING: Batch {batch_key} timed out on polling!")
            continue

        status = run_data["status"]
        print(f"  Batch {batch_key}: {status}")

        if status == "SUCCEEDED":
            dataset_id = run_data.get("defaultDatasetId")
            completed_runs[batch_key] = {
                "run_id": run_id,
                "dataset_id": dataset_id,
                "status": status,
            }
            if batch_key not in progress["completed_batches"]:
                progress["completed_batches"].append(batch_key)
            save_progress(progress)
        else:
            print(f"  ERROR: Batch {batch_key} ended with status {status}")
            msg = run_data.get("statusMessage", "")
            if msg:
                print(f"    Message: {msg}")

    print()

    # Phase 3: Collect results from all datasets
    print("=" * 60)
    print("PHASE 3: Collecting results")
    print("=" * 60)

    all_results = []
    for batch_key, info in sorted(completed_runs.items(), key=lambda x: int(x[0])):
        dataset_id = info["dataset_id"]
        if not dataset_id:
            continue

        print(f"  Fetching results from batch {batch_key} (dataset {dataset_id})...")
        offset = 0
        batch_items = 0

        while True:
            items = get_dataset_items(dataset_id, limit=1000, offset=offset)
            if not items:
                break

            for item in items:
                query = item.get("searchQuery", {}).get("term", "")
                linkedin_matches = extract_linkedin_urls(item)
                total_organic = len(item.get("organicResults", []))

                if linkedin_matches:
                    for match in linkedin_matches:
                        all_results.append({
                            "search_query": query,
                            "linkedin_url": match["linkedin_url"],
                            "profile_title": match["title"],
                            "description": match["description"],
                            "result_position": match["position"],
                            "total_organic_results": total_organic,
                            "batch": batch_key,
                        })
                else:
                    all_results.append({
                        "search_query": query,
                        "linkedin_url": "",
                        "profile_title": "",
                        "description": "NO LINKEDIN MATCH FOUND",
                        "result_position": "",
                        "total_organic_results": total_organic,
                        "batch": batch_key,
                    })
                batch_items += 1

            if len(items) < 1000:
                break
            offset += 1000

        print(f"    Got {batch_items} query results from batch {batch_key}")

    # Phase 4: Score and write output CSV
    print()
    print("=" * 60)
    print("PHASE 4: Scoring & writing results")
    print("=" * 60)

    if all_results:
        # Score each result
        print("  Scoring results...")
        from collections import defaultdict
        query_groups = defaultdict(list)
        for r in all_results:
            query_groups[r["search_query"]].append(r)

        for query, rows in query_groups.items():
            fields = parse_query_fields(query)
            scored_rows = []
            for row in rows:
                if row["linkedin_url"]:
                    score, signals = compute_confidence_score(row, fields)
                    row["confidence_score"] = score
                    row["match_signals"] = "; ".join(
                        f"{k}={v['score']}({v['detail']})" for k, v in signals.items()
                    )
                else:
                    row["confidence_score"] = 0
                    row["match_signals"] = "no_linkedin_url"
                row["is_best_match"] = False
                scored_rows.append(row)

            # Mark best match per query
            url_rows = [(r["confidence_score"], int(r.get("result_position") or 99), r)
                        for r in scored_rows if r["linkedin_url"]]
            if url_rows:
                url_rows.sort(key=lambda x: (-x[0], x[1]))
                url_rows[0][2]["is_best_match"] = True

        fieldnames = [
            "search_query", "linkedin_url", "profile_title",
            "description", "result_position", "total_organic_results", "batch",
            "confidence_score", "match_signals", "is_best_match",
        ]
        with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_results)

        linkedin_found = sum(1 for r in all_results if r["linkedin_url"])
        no_match = sum(1 for r in all_results if not r["linkedin_url"])
        high_conf = sum(1 for r in all_results if r.get("is_best_match") and r["confidence_score"] >= 80)

        print(f"  Results written to: {OUTPUT_FILE}")
        print(f"  Total rows: {len(all_results)}")
        print(f"  LinkedIn profiles found: {linkedin_found}")
        print(f"  No match: {no_match}")
        print(f"  Match rate: {linkedin_found / len(all_results) * 100:.1f}%")
        print(f"  High confidence matches (>=80%): {high_conf}")
    else:
        print("  No results collected!")

    progress["total_results"] = len(all_results)
    save_progress(progress)

    print()
    print("DONE!")


if __name__ == "__main__":
    main()
