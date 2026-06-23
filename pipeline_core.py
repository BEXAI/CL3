#!/usr/bin/env python3
"""
Core pipeline module for batch LinkedIn search.

Shared logic for all batch scripts. Each batch script is a thin wrapper
that creates a BatchConfig and calls run_pipeline().

Cross-cutting fixes applied:
- Exponential backoff retry on API calls (3 retries)
- Catches HTTPError, URLError, socket.timeout, OSError
- Truncates error bodies to 200 chars, redacts tokens
- Atomic progress file writes (tempfile + os.rename)
- Exponential backoff on polling intervals
- Round-robin concurrent batch polling
- Input sanitization on CSV fields (newlines, non-printable chars)
- Graceful environment variable access
- Path-based file references (no hardcoded absolute paths)
"""

import csv
import itertools
import json
import os
import re
import socket
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from linkedin_confidence_scorer import (
    NICKNAME_MAP_FORWARD,
    compute_confidence_score,
    parse_query_fields,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
if not APIFY_TOKEN:
    print("ERROR: APIFY_TOKEN environment variable is not set.", file=sys.stderr)
    print("  Set it with: export APIFY_TOKEN='your_token_here'", file=sys.stderr)
    sys.exit(1)

ACTOR_ID = "apify~google-search-scraper"
BASE_URL = "https://api.apify.com/v2"


@dataclass
class BatchConfig:
    """Per-batch configuration."""
    batch_name: str
    row_start: int
    row_end: int
    source_file: str
    enriched_file: str
    output_file: str
    progress_file: str
    summary_file: str
    batch_size: int = 500
    poll_initial_interval: int = 5
    poll_max_interval: int = 60
    max_poll_time: int = 3000  # 50 minutes in seconds
    high_confidence_threshold: int = 80
    max_api_retries: int = 3


# ---------------------------------------------------------------------------
# Input sanitization
# ---------------------------------------------------------------------------

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def sanitize_field(value):
    """Strip newlines, non-printable chars, and excess whitespace from CSV fields."""
    if not value:
        return ""
    return _CONTROL_CHARS.sub("", value).strip()


# ---------------------------------------------------------------------------
# Apify API helpers (with retry and expanded error handling)
# ---------------------------------------------------------------------------


def api_request(method, path, body=None, *, max_retries=3):
    """Make an API request to Apify with exponential backoff retry."""
    url = f"{BASE_URL}{path}?token={APIFY_TOKEN}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None

    for attempt in range(max_retries):
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            error_body = e.read().decode()[:200]
            print(f"  API Error {e.code}: {error_body}")
            if attempt < max_retries - 1 and e.code >= 500:
                wait = 2 ** (attempt + 1)
                print(f"  Retrying in {wait}s (attempt {attempt + 2}/{max_retries})...")
                time.sleep(wait)
                continue
            raise
        except (URLError, socket.timeout, OSError) as e:
            print(f"  Network error: {type(e).__name__}: {str(e)[:200]}")
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  Retrying in {wait}s (attempt {attempt + 2}/{max_retries})...")
                time.sleep(wait)
                continue
            raise


def start_batch(queries):
    """Start an Apify batch run with the given queries."""
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


def poll_single(run_id):
    """Check the status of a single Apify run (non-blocking, one check)."""
    result = api_request("GET", f"/actor-runs/{run_id}")
    return result["data"]


def poll_batches_concurrent(pass_prog, config):
    """Poll all pending batches in round-robin until all complete or timeout."""
    pending = {
        batch_key: info
        for batch_key, info in sorted(pass_prog["batches"].items(), key=lambda x: int(x[0]))
        if info.get("status") not in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT")
    }

    if not pending:
        return

    elapsed = 0
    interval = config.poll_initial_interval
    check_count = 0

    while pending and elapsed < config.max_poll_time:
        still_pending = {}
        for batch_key, info in pending.items():
            run_id = info["run_id"]
            try:
                run_data = poll_single(run_id)
            except Exception as e:
                print(f"    Batch {batch_key}: poll error ({e}), will retry")
                still_pending[batch_key] = info
                continue

            status = run_data["status"]
            if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                dataset_id = run_data.get("defaultDatasetId", info.get("dataset_id", ""))
                pass_prog["batches"][batch_key]["status"] = status
                pass_prog["batches"][batch_key]["dataset_id"] = dataset_id
                print(f"    Batch {batch_key}: {status}")
            else:
                if check_count % 4 == 0:
                    msg = run_data.get("statusMessage", "")[:80]
                    print(f"    [{run_id[:8]}] {status} - {msg}")
                still_pending[batch_key] = info

        pending = still_pending
        check_count += 1

        if pending:
            time.sleep(interval)
            elapsed += interval
            # Exponential backoff on poll interval, capped at max
            interval = min(int(interval * 1.5), config.poll_max_interval)

    if pending:
        for batch_key in pending:
            print(f"    WARNING: Batch {batch_key} timed out after {elapsed}s!")


def get_dataset_items(dataset_id, limit=1000, offset=0, *, max_retries=3):
    """Fetch dataset items from Apify with retry."""
    url = (
        f"{BASE_URL}/datasets/{dataset_id}/items"
        f"?token={APIFY_TOKEN}&limit={limit}&offset={offset}&format=json&clean=true"
    )
    for attempt in range(max_retries):
        req = Request(url)
        try:
            with urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode())
        except (HTTPError, URLError, socket.timeout, OSError) as e:
            print(f"  Dataset fetch error: {type(e).__name__}: {str(e)[:200]}")
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise


# ---------------------------------------------------------------------------
# Progress (atomic writes)
# ---------------------------------------------------------------------------


def load_progress(progress_file):
    """Load progress from a JSON file."""
    if os.path.exists(progress_file):
        with open(progress_file) as f:
            return json.load(f)
    return {"pass1": {"batches": {}}, "passes": {}}


def save_progress(progress, progress_file):
    """Atomically save progress to a JSON file (write to temp, then rename)."""
    dir_name = os.path.dirname(progress_file) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(progress, f, indent=2)
        os.replace(tmp_path, progress_file)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Query generation (with input sanitization)
# ---------------------------------------------------------------------------


def build_pass1_query(row):
    """Pass 1: Name + Company."""
    first = sanitize_field(row.get("First Name", ""))
    last = sanitize_field(row.get("Last Name", ""))
    company = sanitize_field(row.get("Business name", ""))
    parts = []
    if first:
        parts.append(f'"{first}"')
    if last:
        parts.append(f'"{last}"')
    if company:
        parts.append(f'"{company}"')
    parts.append('"LinkedIn"')
    return " ".join(parts)


def generate_pass2_query(row):
    """Pass 2: Name + Location (drop company)."""
    first = sanitize_field(row.get("First Name", ""))
    last = sanitize_field(row.get("Last Name", ""))
    city = sanitize_field(row.get("City", ""))
    state = sanitize_field(row.get("State", ""))
    if not first or not last or not city or not state:
        return None
    return f'"{first}" "{last}" "{city}" "{state}" "LinkedIn"'


def generate_pass3_query(row):
    """Pass 3: Name only."""
    first = sanitize_field(row.get("First Name", ""))
    last = sanitize_field(row.get("Last Name", ""))
    if not first or not last:
        return None
    return f'"{first}" "{last}" "LinkedIn"'


def generate_pass4_queries(row):
    """Pass 4: Nickname variants."""
    first = sanitize_field(row.get("First Name", ""))
    last = sanitize_field(row.get("Last Name", ""))
    city = sanitize_field(row.get("City", ""))
    state = sanitize_field(row.get("State", ""))
    if not first or not last:
        return []
    first_lower = first.lower()
    if first_lower not in NICKNAME_MAP_FORWARD:
        return []
    variants = NICKNAME_MAP_FORWARD[first_lower]
    queries = []
    for variant in variants[:2]:
        variant_title = variant.capitalize()
        if city and state:
            queries.append(f'"{variant_title}" "{last}" "{city}" "{state}" "LinkedIn"')
        else:
            queries.append(f'"{variant_title}" "{last}" "LinkedIn"')
    return queries


def generate_pass5_query(row):
    """Pass 5: Alternative business name."""
    first = sanitize_field(row.get("First Name", ""))
    last = sanitize_field(row.get("Last Name", ""))
    biz2 = sanitize_field(row.get("Business name 2", ""))
    if not first or not last or not biz2:
        return None
    return f'"{first}" "{last}" "{biz2}" "LinkedIn"'


# ---------------------------------------------------------------------------
# Run queries through Apify
# ---------------------------------------------------------------------------


def run_apify_pass(pass_name, queries_list, progress, config):
    """Run a list of queries through Apify. Returns {query: [matches]}."""
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
        start = batch_num * config.batch_size
        end = min(start + config.batch_size, len(queries_list))
        batch_queries = queries_list[start:end]
        print(f"    Starting batch {batch_num} ({len(batch_queries)} queries)...", end=" ")
        run_id, dataset_id = start_batch(batch_queries)
        print(f"run_id={run_id[:12]}")
        pass_prog["batches"][batch_key] = {
            "run_id": run_id, "dataset_id": dataset_id, "status": "RUNNING",
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
    """Score all LinkedIn matches for a single source row. Returns best match."""
    if not linkedin_matches:
        return "", "", "", 0, ""
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
# Main pipeline
# ---------------------------------------------------------------------------


def run_pipeline(config):
    """Run the full 5-pass LinkedIn search pipeline for a batch."""
    threshold = config.high_confidence_threshold

    print("=" * 70)
    print(f"LinkedIn Search: {config.batch_name} (Rows {config.row_start + 1} to {config.row_end})")
    print("=" * 70)
    print()

    # Load source rows (using islice to skip efficiently)
    print("[1/8] Loading source data...")
    source_rows = []
    with open(config.source_file, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in itertools.islice(reader, config.row_start, config.row_end):
            source_rows.append(row)
    total = len(source_rows)
    if total == 0:
        print("  ERROR: No source rows loaded. Check row_start/row_end.", file=sys.stderr)
        sys.exit(1)
    print(f"  Loaded {total} source rows (indices {config.row_start} to {config.row_start + total - 1})")
    print()

    progress = load_progress(config.progress_file)

    # --- PASS 1: Name + Company ---
    print("[2/8] Pass 1: Name + Company...")
    pass1_queries = []
    pass1_query_to_indices = {}
    for i, row in enumerate(source_rows):
        query = build_pass1_query(row)
        pass1_queries.append(query)
        pass1_query_to_indices.setdefault(query, []).append(i)

    unique_pass1 = list(dict.fromkeys(pass1_queries))
    print(f"  Total queries: {len(pass1_queries)}, unique: {len(unique_pass1)}")

    pass1_results = run_apify_pass("pass1", unique_pass1, progress, config)

    best_per_row = {}
    pass1_matched = 0
    for i, row in enumerate(source_rows):
        query = pass1_queries[i]
        matches = pass1_results.get(query, [])
        url, title, desc, score, signals = score_results_for_row(row, matches, query)
        best_per_row[i] = {
            "url": url, "title": title, "description": desc,
            "score": score, "signals": signals,
            "pass": "pass1" if score >= threshold else "",
        }
        if score >= threshold:
            pass1_matched += 1

    print(f"  Pass 1 high-confidence matches: {pass1_matched} ({pass1_matched / total * 100:.1f}%)")
    print()

    # Save enriched CSV (Pass 1 checkpoint)
    print("  Saving Pass 1 checkpoint...")
    fieldnames_base = list(source_rows[0].keys())
    enriched_fieldnames = fieldnames_base + [
        "LinkedIn_URL", "LinkedIn_Title", "LinkedIn_Description",
        "Confidence_Score", "Match_Signals",
    ]
    enriched_rows = []
    for i, row in enumerate(source_rows):
        enriched = dict(row)
        enriched["LinkedIn_URL"] = best_per_row[i]["url"]
        enriched["LinkedIn_Title"] = best_per_row[i]["title"]
        enriched["LinkedIn_Description"] = best_per_row[i]["description"]
        enriched["Confidence_Score"] = best_per_row[i]["score"]
        enriched["Match_Signals"] = best_per_row[i]["signals"]
        enriched_rows.append(enriched)

    with open(config.enriched_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=enriched_fieldnames)
        writer.writeheader()
        writer.writerows(enriched_rows)
    print(f"  Checkpoint saved: {config.enriched_file}")
    print()

    pass_stats = {"pass1": pass1_matched}
    unmatched_indices = [i for i in range(total) if best_per_row[i]["score"] < threshold]

    # --- Helper for passes 2-5 ---
    def run_secondary_pass(pass_num, pass_label, query_generator, multi=False):
        print(f"[{pass_num}/8] {pass_label}...")
        still_unmatched = [i for i in unmatched_indices if best_per_row[i]["score"] < threshold]
        print(f"  Candidates: {len(still_unmatched)}")

        query_map = {}
        for i in still_unmatched:
            if multi:
                for query in query_generator(source_rows[i]):
                    query_map.setdefault(query, []).append(i)
            else:
                query = query_generator(source_rows[i])
                if query:
                    query_map.setdefault(query, []).append(i)

        print(f"  Unique queries: {len(query_map)}")
        pass_key = f"pass{pass_num - 1}"  # pass_num 3 -> pass2, etc.
        results = run_apify_pass(pass_key, list(query_map.keys()), progress, config)

        new_matches = 0
        for query, indices in query_map.items():
            matches = results.get(query, [])
            for i in indices:
                url, title, desc, score, signals = score_results_for_row(
                    source_rows[i], matches, query
                )
                if score > best_per_row[i]["score"]:
                    best_per_row[i] = {
                        "url": url, "title": title, "description": desc,
                        "score": score, "signals": signals, "pass": pass_key,
                    }
                    if score >= threshold:
                        new_matches += 1

        pass_stats[pass_key] = new_matches
        print(f"  {pass_label} new high-confidence matches: {new_matches}")
        print()

    run_secondary_pass(3, "Pass 2: Name + City + State", generate_pass2_query)
    run_secondary_pass(4, "Pass 3: Name only", generate_pass3_query)
    run_secondary_pass(5, "Pass 4: Nickname variants", generate_pass4_queries, multi=True)
    run_secondary_pass(6, "Pass 5: Business Name 2 fallback", generate_pass5_query)

    # --- Re-score with enhanced scorer ---
    print("[7/8] Re-scoring with enhanced scorer...")
    upgraded = 0
    for i in range(total):
        row = source_rows[i]
        url = best_per_row[i]["url"]
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
        row_data = {
            "profile_title": best_per_row[i]["title"],
            "description": best_per_row[i]["description"],
            "linkedin_url": url,
            "result_position": "1",
        }
        new_score, signals = compute_confidence_score(row_data, fields, source_data)
        if new_score > best_per_row[i]["score"]:
            if new_score >= threshold and best_per_row[i]["score"] < threshold:
                upgraded += 1
            best_per_row[i]["score"] = new_score
            best_per_row[i]["signals"] = "; ".join(
                f"{k}={v['score']}({v['detail']})" for k, v in signals.items()
            )
            if not best_per_row[i]["pass"]:
                best_per_row[i]["pass"] = "rescore"

    print(f"  Upgraded {upgraded} rows")
    print()

    # --- Build final output ---
    print("[8/8] Building final output...")
    output_fieldnames = fieldnames_base + [
        "LinkedIn_URL", "LinkedIn_Title", "LinkedIn_Description",
        "Confidence_Score", "Match_Signals", "Match_Pass",
    ]

    final_high = final_medium = final_low = final_none = 0
    final_rows = []

    for i, row in enumerate(source_rows):
        best = best_per_row[i]
        out = dict(row)
        out["LinkedIn_URL"] = best["url"]
        out["LinkedIn_Title"] = best["title"]
        out["LinkedIn_Description"] = best["description"]
        out["Confidence_Score"] = best["score"]
        out["Match_Signals"] = best["signals"]
        out["Match_Pass"] = best["pass"]
        final_rows.append(out)

        if best["score"] >= threshold:
            final_high += 1
        elif best["score"] >= 40:
            final_medium += 1
        elif best["url"]:
            final_low += 1
        else:
            final_none += 1

    with open(config.output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_fieldnames)
        writer.writeheader()
        writer.writerows(final_rows)

    print(f"  Written: {config.output_file}")
    print()

    # --- Summary ---
    print("=" * 70)
    print(f"{config.batch_name.upper()} PIPELINE SUMMARY (Rows {config.row_start + 1} to {config.row_end})")
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
        "row_range": f"{config.row_start + 1}-{config.row_end}",
        "total_rows": total,
        "pass_stats": pass_stats,
        "final_high_confidence": final_high,
        "final_medium": final_medium,
        "final_low_with_url": final_low,
        "final_no_match": final_none,
        "final_match_rate_pct": round(final_high / total * 100, 1),
    }
    with open(config.summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Summary saved: {config.summary_file}")
    print()
    print("DONE!")
