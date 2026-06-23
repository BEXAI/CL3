# LinkedIn Profile Enrichment System — Workstream Description

## Overview

This system takes a source dataset of 25,003 high-net-worth individual (HNWI) contact records and automatically finds their LinkedIn profile URLs using a multi-pass Google search pipeline. The system achieved an **87.4% high-confidence match rate** (21,864 out of 25,003 records matched).

---

## System Architecture

### Data Flow

```
Source CSV (25,003 rows)
    |
    v
[Pass 1] "FirstName" "LastName" "CompanyName" "LinkedIn"
    |  ~28% matched
    v
[Pass 2] "FirstName" "LastName" "City" "State" "LinkedIn"
    |  ~55% cumulative
    v
[Pass 3] "FirstName" "LastName" "LinkedIn"
    |  ~87% cumulative
    v
[Pass 4] "Nickname" "LastName" "City" "State" "LinkedIn"
    |  ~87.5% cumulative
    v
[Pass 5] "FirstName" "LastName" "BusinessName2" "LinkedIn"
    |  ~87.5% cumulative
    v
[Enhanced Scoring] — re-score all results with location/middle-initial bonuses
    |
    v
Final Enriched CSV (25,003 rows + LinkedIn URL, title, confidence score)
```

### Processing Batches

The dataset is processed in batches of 5,000 rows. Each batch runs independently through all 5 passes. Within each pass, queries are sent to the Apify Google Search Scraper in sub-batches of 500 queries.

| Batch | Row Range | Output File |
|-------|-----------|-------------|
| 1 | 1–5,000 | `linkedin_5000_final.csv` |
| 2 | 5,001–10,000 | `linkedin_batch2_final.csv` |
| 3 | 10,001–15,000 | `linkedin_batch3_final.csv` |
| 4 | 15,001–20,000 | `linkedin_batch4_final.csv` |
| 5 | 20,001–25,003 | `linkedin_batch5_final.csv` |
| **Master** | **1–25,003** | **`linkedin_master_25003.csv`** |

---

## Multi-Pass Query Strategy

### Why Multi-Pass?

A single search query format cannot reliably find LinkedIn profiles for all individuals. The main bottleneck is the **company name** — obscure LLCs, foundations, and holding companies that don't appear on anyone's LinkedIn profile cause Google to return zero results. The multi-pass approach progressively relaxes the search constraints:

### Pass 1: Name + Company (Baseline)
- **Query:** `"FirstName" "LastName" "CompanyName" "LinkedIn"`
- **Rationale:** The most specific query. When it works, it produces the highest-confidence matches because both name and company can be verified.
- **Typical yield:** ~28% of rows

### Pass 2: Name + Location (Drop Company)
- **Query:** `"FirstName" "LastName" "City" "State" "LinkedIn"`
- **Rationale:** For the ~72% of rows where the company name killed the search, substituting city and state provides geographic disambiguation without the restrictive company requirement. Google will find LinkedIn profiles that mention the person's metro area.
- **Typical yield:** ~26% additional (cumulative ~54%)

### Pass 3: Name Only
- **Query:** `"FirstName" "LastName" "LinkedIn"`
- **Rationale:** For names that are sufficiently unique (which most are in this dataset), the name alone plus "LinkedIn" is enough for Google to surface the correct profile. The confidence scorer then verifies the match by checking the name against the profile title and URL slug.
- **Typical yield:** ~33% additional (cumulative ~87%)

### Pass 4: Nickname Variants
- **Query:** `"Nickname" "LastName" "City" "State" "LinkedIn"`
- **Rationale:** Some individuals use informal names on LinkedIn (William goes by Bill, Richard by Rick, etc.). The system has a built-in dictionary of 70+ formal-to-nickname mappings and generates variant queries for still-unmatched rows.
- **Typical yield:** ~0.5% additional

### Pass 5: Alternative Business Name
- **Query:** `"FirstName" "LastName" "BusinessName2" "LinkedIn"`
- **Rationale:** The source data includes up to 3 business names per individual. Business Name 2 is often a better-known parent company (e.g., "Eli Lilly And Company" vs. "Eli Lilly And Company Foundation"). This pass tries the alternative company name for remaining unmatched rows.
- **Typical yield:** ~0.05% additional

---

## Confidence Scoring Engine

Every LinkedIn result returned by Google is scored against the source data to determine match quality. Only matches scoring **80% or higher** are classified as high-confidence.

### Scoring Breakdown

| Signal | Points | Description |
|--------|--------|-------------|
| **Name Match** | 80 | First name AND last name found in LinkedIn profile title or URL slug. Considers nickname variants, hyphenated names, and name suffixes (Jr, III, etc.) |
| Company Match | up to 8 | Company name (stripped of LLC/Inc suffixes) found in profile description |
| Search Position | up to 5 | Google result position (1st result = 5 pts, 2nd = 4 pts, etc.) |
| URL Slug Quality | up to 4 | LinkedIn URL slug contains both first and last name |
| Location Context | up to 3 | Profile description contains location-related terms (metro area, state, etc.) |
| Source City/State Match | up to 5 | City or state from source data found in LinkedIn profile text |
| Middle Initial Match | up to 3 | Middle initial from source data matches initial in profile title or URL |
| **Maximum Score** | **100** | |

A score of 80+ means the person's name was definitively found in the profile, plus at least some corroborating signals.

### Name Matching Features
- **Nickname recognition:** 70+ name mappings (William/Bill, Robert/Bob, etc.)
- **Hyphenated name handling:** "Granville-Smith" matches both hyphenated and split forms
- **Suffix stripping:** Jr, Sr, III, MD, PhD, Esq removed before comparison
- **Middle name detection:** "William J. Ruh" pattern recognized in titles

---

## External Service

### Apify Google Search Scraper

- **Service:** Apify (https://apify.com)
- **Actor:** `apify/google-search-scraper` — https://apify.com/apify/google-search-scraper
- **What it does:** Executes Google searches programmatically and returns structured results (URLs, titles, descriptions, positions)
- **Configuration:** 1 page per query, US country code, no HTML saving
- **Batch size:** 500 queries per Apify run
- **Cost:** Approximately $6 per 5,000 rows (all 5 passes)

---

## Resume & Fault Tolerance

Each batch script writes progress to a JSON file (`batch{N}_progress.json`) after every Apify sub-batch completes. If the process is interrupted for any reason (network error, credit limit, timeout), re-running the same script will:

1. Skip all previously completed Apify runs
2. Resume from the exact pass and sub-batch where it stopped
3. Produce the same final output

This was used in production when an Apify credit limit was hit mid-run — the script resumed seamlessly after credits were added.

---

## Output Format

The master output file (`linkedin_master_25003.csv`) contains all 142 original source columns plus 6 new columns appended:

| Column | Description |
|--------|-------------|
| `LinkedIn_URL` | Full LinkedIn profile URL (e.g., `https://www.linkedin.com/in/john-smith-12345`) |
| `LinkedIn_Title` | Google's title for the LinkedIn result (typically "Name - Title - Company") |
| `LinkedIn_Description` | Google's description snippet for the LinkedIn result |
| `Confidence_Score` | 0–100 integer score (80+ = high confidence match) |
| `Match_Signals` | Detailed scoring breakdown showing which signals contributed |
| `Match_Pass` | Which pass found this match (`pass1`, `pass2`, `pass3`, `pass4`, `pass5`, or `rescore`) |

---

## Results Summary

| Metric | Value |
|--------|-------|
| Total records processed | 25,003 |
| High-confidence matches (>=80%) | 21,864 (87.4%) |
| Low-confidence with URL (<80%) | 2,732 (10.9%) |
| No LinkedIn URL found | 407 (1.6%) |

### Per-Batch Results

| Batch | Rows | High Confidence | Rate |
|-------|------|----------------|------|
| 1 | 1–5,000 | 4,358 | 87.2% |
| 2 | 5,001–10,000 | 4,354 | 87.1% |
| 3 | 10,001–15,000 | 4,416 | 88.3% |
| 4 | 15,001–20,000 | 4,390 | 87.8% |
| 5 | 20,001–25,003 | 4,346 | 86.9% |

### Per-Pass Contribution (Averaged Across All Batches)

| Pass | Strategy | Avg New Matches | Avg Cumulative Rate |
|------|----------|-----------------|---------------------|
| 1 | Name + Company | ~1,425 (28.5%) | 28.5% |
| 2 | Name + Location | ~1,298 (26.0%) | 54.5% |
| 3 | Name Only | ~1,624 (32.5%) | 87.0% |
| 4 | Nicknames | ~24 (0.5%) | 87.4% |
| 5 | Alt Company | ~2 (0.05%) | 87.5% |
