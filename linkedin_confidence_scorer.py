#!/usr/bin/env python3
"""
LinkedIn Profile Match Confidence Scoring Engine.

Scoring logic:
- First name AND last name match in profile title or URL slug = 80% confidence
- Additional signals (company, location, slug quality, position) add up to 20% more
- Source-data bonuses (city/state cross-check, middle initial) can add further points
- Total max = 100%

Supports multi-pass query formats:
  Pass 1: "First" "Last" "Company" "LinkedIn"
  Pass 2: "First" "Last" "City" "State" "LinkedIn"
  Pass 3: "First" "Last" "LinkedIn"
  Pass 4: "Nickname" "Last" "City" "State" "LinkedIn"
  Pass 5: "First" "Last" "BusinessName2" "LinkedIn"
"""

import csv
import json
import re
import os
from collections import defaultdict
from urllib.parse import urlparse

# ─── File paths ───────────────────────────────────────────────────────────────

BASE_DIR = "/Users/nathaniel/Desktop/Cl3"
RESULTS_CSV = os.path.join(BASE_DIR, "linkedin_results_batch1.csv")
SOURCE_CSV = os.path.join(BASE_DIR, "All WE contacts_vAIM_1.0.csv")

OUTPUT_SCORED = os.path.join(BASE_DIR, "linkedin_results_scored.csv")
OUTPUT_HIGH_CONF = os.path.join(BASE_DIR, "linkedin_high_confidence.csv")
OUTPUT_REFORMULATED = os.path.join(BASE_DIR, "reformulated_queries.txt")
OUTPUT_SUMMARY = os.path.join(BASE_DIR, "match_summary.json")

# ─── Nickname Dictionary (bidirectional) ──────────────────────────────────────

NICKNAME_MAP_FORWARD = {
    "william": ["bill", "will", "willy", "billy"],
    "richard": ["rick", "dick", "rich"],
    "robert": ["bob", "rob", "bobby", "robbie"],
    "james": ["jim", "jimmy", "jamie"],
    "john": ["jack", "johnny", "jon"],
    "michael": ["mike", "mikey"],
    "thomas": ["tom", "tommy"],
    "charles": ["charlie", "chuck", "chas"],
    "daniel": ["dan", "danny"],
    "david": ["dave", "davey"],
    "joseph": ["joe", "joey"],
    "edward": ["ed", "eddie", "ted", "teddy"],
    "andrew": ["andy", "drew"],
    "anthony": ["tony"],
    "christopher": ["chris"],
    "donald": ["don", "donny"],
    "douglas": ["doug"],
    "elizabeth": ["liz", "beth", "betsy", "lizzy", "eliza"],
    "margaret": ["maggie", "meg", "peggy", "marge"],
    "patricia": ["pat", "patty", "trish"],
    "jennifer": ["jen", "jenny"],
    "catherine": ["cathy", "kate", "katie", "cat"],
    "katherine": ["kathy", "kate", "katie", "kat"],
    "susan": ["sue", "suzy", "susie"],
    "barbara": ["barb", "barbie"],
    "jessica": ["jess", "jessie"],
    "stephanie": ["steph"],
    "christine": ["chris", "chrissy", "tina"],
    "christina": ["chris", "chrissy", "tina"],
    "nicholas": ["nick", "nicky"],
    "timothy": ["tim", "timmy"],
    "stephen": ["steve"],
    "steven": ["steve"],
    "matthew": ["matt"],
    "jonathan": ["jon", "jonny"],
    "benjamin": ["ben", "benny"],
    "kenneth": ["ken", "kenny"],
    "gregory": ["greg"],
    "ronald": ["ron", "ronny"],
    "lawrence": ["larry"],
    "raymond": ["ray"],
    "gerald": ["gerry", "jerry"],
    "frederick": ["fred", "freddy"],
    "samuel": ["sam", "sammy"],
    "alexander": ["alex"],
    "alexandra": ["alex", "lexi"],
    "nathaniel": ["nate", "nathan"],
    "theodore": ["ted", "teddy", "theo"],
    "phillip": ["phil"],
    "philip": ["phil"],
    "walter": ["walt"],
    "eugene": ["gene"],
    "leonard": ["leo", "lenny"],
    "harold": ["harry", "hal"],
    "henry": ["hank", "harry"],
    "arthur": ["art"],
    "albert": ["al", "bert"],
    "clifford": ["cliff"],
    "peter": ["pete"],
    "francis": ["frank", "fran"],
    "frank": ["frankie"],
    "victoria": ["vicki", "vicky", "tori"],
    "deborah": ["deb", "debbie"],
    "rebecca": ["becky", "becca"],
    "pamela": ["pam"],
    "dorothy": ["dot", "dotty"],
    "virginia": ["ginny", "ginger"],
}


def build_nickname_lookup():
    """Build bidirectional nickname lookup: given any name variant, return all equivalents."""
    lookup = defaultdict(set)
    for formal, variants in NICKNAME_MAP_FORWARD.items():
        group = set([formal] + variants)
        for name in group:
            lookup[name].update(group)
    return dict(lookup)


NICKNAME_LOOKUP = build_nickname_lookup()

# ─── Company suffix patterns to strip ─────────────────────────────────────────

COMPANY_SUFFIXES = re.compile(
    r"\b(llc|inc|corp|co|ltd|lp|llp|pllc|plc|group|holdings|partners|partnership)\b\.?",
    re.IGNORECASE,
)

# ─── Helper Functions ─────────────────────────────────────────────────────────


def normalize(text):
    """Lowercase and strip extra whitespace."""
    if not text:
        return ""
    return " ".join(text.lower().split())


def parse_slug(url):
    """Extract the slug from a LinkedIn /in/ URL, split into parts."""
    try:
        path = urlparse(url).path
        match = re.search(r"/in/([^/]+)", path)
        if match:
            slug = match.group(1)
            # Strip trailing hash digits (e.g., -12345)
            slug_clean = re.sub(r"-\d+$", "", slug)
            return slug_clean.split("-")
        return []
    except Exception:
        return []


def strip_company_suffixes(name):
    """Remove common corporate suffixes from company name."""
    cleaned = COMPANY_SUFFIXES.sub("", name)
    return " ".join(cleaned.split()).strip()


def get_name_variants(first_name):
    """Get all nickname variants for a first name."""
    key = first_name.lower().strip()
    return NICKNAME_LOOKUP.get(key, {key})


def parse_query_fields(query):
    """
    Parse a search query. Handles multiple formats:
    - Pass 1: "First" "Last" "Company" "LinkedIn"
    - Pass 2: "First" "Last" "City" "State" "LinkedIn"
    - Pass 3: "First" "Last" "LinkedIn"
    - Pass 4: "Nickname" "Last" "City" "State" "LinkedIn"  (same as Pass 2)
    - Pass 5: "First" "Last" "BusinessName2" "LinkedIn"  (same as Pass 1)
    - Old: site:linkedin.com/in/ "First Last" "City" "State" "Company"
    Returns dict with first_name, last_name, company.
    """
    # Extract all quoted strings
    quoted = re.findall(r'"([^"]+)"', query)
    result = {"first_name": "", "last_name": "", "company": ""}

    if not quoted:
        return result

    # Filter out "LinkedIn"
    parts = [q for q in quoted if q.lower() != "linkedin"]

    # Detect old format: first part contains a space (full name)
    if parts and " " in parts[0]:
        # Old format: "First Last" "City" "State" "Company"
        name_parts = parts[0].split()
        result["first_name"] = name_parts[0]
        result["last_name"] = name_parts[-1]
        if len(parts) >= 4:
            result["company"] = parts[3]
        elif len(parts) == 3 and len(parts[2]) > 2:
            result["company"] = parts[2]
    else:
        # New formats: parts are non-LinkedIn quoted strings
        if len(parts) >= 1:
            result["first_name"] = parts[0]
        if len(parts) >= 2:
            result["last_name"] = parts[1]
        if len(parts) == 3:
            # 3 parts = "First" "Last" "Company" (Pass 1/5)
            result["company"] = parts[2]
        elif len(parts) == 4:
            # 4 parts = "First" "Last" "City" "State" (Pass 2/4)
            # No company — city+state are disambiguation, not scored as company
            pass
        # len(parts) == 2: "First" "Last" only (Pass 3) — no company

    return result


# ─── Scoring Functions ────────────────────────────────────────────────────────


def _dehyphen(text):
    """Strip hyphens for comparison (Granville-Smith -> granvillesmith)."""
    return text.replace("-", "")


NAME_SUFFIXES = re.compile(r"\b(jr|sr|ii|iii|iv|v|esq|md|phd|dds|dvm)\b\.?", re.IGNORECASE)


def _strip_name_suffixes(text):
    """Remove personal suffixes like Jr, III, etc."""
    return NAME_SUFFIXES.sub("", text).strip()


def name_matches(first_name, last_name, title, url, middle_name="",
                  _slug_parts=None, _first_variants=None):
    """
    Check if first name AND last name match in title or URL slug.
    Returns (matched: bool, detail: str)
    Considers nickname variants, hyphenated names, and suffixes.
    """
    first_lower = first_name.lower().strip()
    last_lower = last_name.lower().strip()
    title_lower = normalize(_strip_name_suffixes(title))
    slug_parts = _slug_parts if _slug_parts is not None else parse_slug(url)

    if not first_lower or not last_lower:
        return False, "missing_name"

    first_variants = _first_variants if _first_variants is not None else get_name_variants(first_lower)

    # --- Check title ---
    # Direct check (word-boundary to avoid substring false positives like "Al" in "general")
    for variant in first_variants:
        if re.search(rf"\b{re.escape(variant)}\b", title_lower) and re.search(rf"\b{re.escape(last_lower)}\b", title_lower):
            if variant == first_lower:
                return True, "exact_name_in_title"
            else:
                return True, f"nickname_{variant}_in_title"

    # Hyphenated name check: dehyphenate both sides and retry
    if "-" in last_lower or "-" in title_lower:
        title_dehyph = _dehyphen(title_lower)
        last_dehyph = _dehyphen(last_lower)
        for variant in first_variants:
            if re.search(rf"\b{re.escape(variant)}\b", title_dehyph) and re.search(rf"\b{re.escape(last_dehyph)}\b", title_dehyph):
                if variant == first_lower:
                    return True, "exact_name_in_title_dehyphen"
                else:
                    return True, f"nickname_{variant}_in_title_dehyphen"

    # Check "First Middle Last" pattern in title (middle name between first/last)
    if middle_name:
        mid_lower = middle_name.lower().strip()
        for variant in first_variants:
            pattern = rf"\b{re.escape(variant)}\b.*\b{re.escape(mid_lower)}\b.*\b{re.escape(last_lower)}\b"
            if re.search(pattern, title_lower):
                return True, "full_name_with_middle_in_title"

    # --- Check slug ---
    for variant in first_variants:
        if variant in slug_parts and last_lower in slug_parts:
            if variant == first_lower:
                return True, "exact_name_in_slug"
            else:
                return True, f"nickname_{variant}_in_slug"

    # Hyphenated slug check
    if "-" in last_lower:
        # Slug splits on hyphens, so "granville-smith" -> ["granville", "smith"]
        # Check if all parts of hyphenated last name are in slug
        last_parts = last_lower.split("-")
        for variant in first_variants:
            if variant in slug_parts and all(p in slug_parts for p in last_parts):
                return True, "hyphen_name_in_slug"

    return False, "no_name_match"


def score_company_bonus(company, title, description, _normalized_text=None):
    """
    Company match bonus (0–8 pts out of the 20 bonus pts).
    """
    if not company or not company.strip():
        return 0, "no_company_data"

    text = _normalized_text if _normalized_text is not None else normalize(title + " " + description)
    company_clean = strip_company_suffixes(company).lower().strip()

    if not company_clean:
        return 0, "no_company_data"

    # Full company name match (word boundary for short names to avoid false positives)
    if len(company_clean) < 4:
        if re.search(rf"\b{re.escape(company_clean)}\b", text):
            return 8, "full_company_match"
    elif company_clean in text:
        return 8, "full_company_match"

    # Partial match: >=50% of significant words (3+ chars)
    words = [w for w in company_clean.split() if len(w) >= 3]
    if words:
        matches = sum(1 for w in words if w in text)
        if matches / len(words) >= 0.5:
            return 5, f"partial_company_{matches}/{len(words)}"

    return 0, "no_company_match"


def score_position_bonus(position):
    """Position bonus (0–5 pts). Top results are more likely correct."""
    try:
        pos = int(position)
    except (ValueError, TypeError):
        return 0, "no_position"

    if pos == 1:
        return 5, "position_1"
    elif pos == 2:
        return 4, "position_2"
    elif pos == 3:
        return 3, "position_3"
    elif pos <= 5:
        return 2, f"position_{pos}"
    else:
        return 0, f"position_{pos}"


def score_slug_bonus(first_name, last_name, url, _slug_parts=None, _first_variants=None):
    """
    URL slug quality bonus (0–4 pts). Slug containing both names = strong signal.
    """
    slug_parts = _slug_parts if _slug_parts is not None else parse_slug(url)
    if not slug_parts:
        return 0, "no_slug"

    first_lower = first_name.lower().strip()
    last_lower = last_name.lower().strip()
    first_variants = _first_variants if _first_variants is not None else get_name_variants(first_lower)

    # Slug has first+last
    if last_lower in slug_parts and (
        first_lower in slug_parts or any(v in slug_parts for v in first_variants)
    ):
        return 4, "slug_first_last"

    # Slug has just last name
    if last_lower in slug_parts:
        return 2, "slug_last_name"

    return 0, "slug_unrelated"


def score_location_bonus(title, description, _normalized_text=None):
    """
    Location info present bonus (0–3 pts).
    If LinkedIn description mentions a location, it's slightly more credible.
    """
    text = _normalized_text if _normalized_text is not None else normalize(title + " " + description)
    # Look for common location patterns in LinkedIn descriptions
    if re.search(r"\b(united states|area|metro|greater)\b", text):
        return 3, "has_location_context"
    # State or city-like pattern (capitalized word followed by comma)
    if re.search(r"[a-z]+,\s*[a-z]", text):
        return 2, "has_location_hint"
    return 0, "no_location_signal"


# ─── US State Names (for location cross-check) ──────────────────────────────

STATE_ABBREV_TO_NAME = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut", "DE": "delaware",
    "FL": "florida", "GA": "georgia", "HI": "hawaii", "ID": "idaho",
    "IL": "illinois", "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota", "MS": "mississippi",
    "MO": "missouri", "MT": "montana", "NE": "nebraska", "NV": "nevada",
    "NH": "new hampshire", "NJ": "new jersey", "NM": "new mexico", "NY": "new york",
    "NC": "north carolina", "ND": "north dakota", "OH": "ohio", "OK": "oklahoma",
    "OR": "oregon", "PA": "pennsylvania", "RI": "rhode island", "SC": "south carolina",
    "SD": "south dakota", "TN": "tennessee", "TX": "texas", "UT": "utah",
    "VT": "vermont", "VA": "virginia", "WA": "washington", "WV": "west virginia",
    "WI": "wisconsin", "WY": "wyoming", "DC": "district of columbia",
}


def score_location_from_source(title, description, source_city="", source_state="",
                               _normalized_text=None):
    """
    Cross-check city/state from source data against LinkedIn profile text.
    Returns (bonus: int, detail: str).
    - City found → +5 pts
    - State found → +3 pts
    - Both → +5 pts (don't stack beyond city match)
    """
    if not source_city and not source_state:
        return 0, "no_source_location"

    text = _normalized_text if _normalized_text is not None else normalize(title + " " + description)
    if not text:
        return 0, "no_profile_text"

    city_lower = normalize(source_city)
    state_lower = source_state.strip().upper()

    city_found = False
    state_found = False

    if city_lower and len(city_lower) >= 3 and city_lower in text:
        city_found = True

    if state_lower:
        # Check state abbreviation (e.g., "FL", "NY")
        state_full = STATE_ABBREV_TO_NAME.get(state_lower, "")
        if state_full and state_full in text:
            state_found = True
        # Also check the abbreviation itself with word boundary (e.g., ", FL" or "FL ")
        if re.search(rf"\b{re.escape(state_lower.lower())}\b", text):
            state_found = True

    if city_found:
        return 5, f"city_match_{source_city}"
    if state_found:
        return 3, f"state_match_{source_state}"
    return 0, "no_location_match"


def score_middle_initial_bonus(title, description, url, source_middle_name="",
                               _normalized_text=None, _slug_parts=None):
    """
    If the LinkedIn profile contains a middle initial that matches the source
    middle name, award a bonus.
    Returns (bonus: int, detail: str).
    """
    if not source_middle_name or len(source_middle_name.strip()) == 0:
        return 0, "no_middle_name"

    mid_initial = source_middle_name.strip()[0].lower()
    text = _normalized_text if _normalized_text is not None else normalize(title + " " + description)
    slug_parts = _slug_parts if _slug_parts is not None else parse_slug(url)

    # Check for middle initial pattern in title: "William J. Ruh" (require period after initial)
    pattern = rf"\b{re.escape(mid_initial)}\.(?:\s|$)"
    if re.search(pattern, text):
        return 3, f"middle_initial_{mid_initial}_in_title"

    # Check slug for middle initial (e.g., "william-j-ruh")
    if mid_initial in slug_parts and len(mid_initial) == 1:
        return 3, f"middle_initial_{mid_initial}_in_slug"

    return 0, "no_middle_initial_match"


def compute_confidence_score(row, fields, source_data=None):
    """
    Compute confidence score for a single result row.

    Logic:
    - Name match (first + last) = 80%
    - Bonus signals add up to 20% max:
        - Company match: up to 8%
        - Position bonus: up to 5%
        - Slug quality: up to 4%
        - Location context: up to 3%
    - Source-data bonuses (if provided):
        - City/State cross-check: up to 5%
        - Middle initial match: up to 3%
    - Total: 0-100%

    Args:
        row: dict with profile_title, description, linkedin_url, result_position
        fields: dict with first_name, last_name, company (parsed from query)
        source_data: optional dict with source_city, source_state, middle_name
    """
    first_name = fields["first_name"]
    last_name = fields["last_name"]
    company = fields.get("company", "")

    title = row.get("profile_title", "")
    description = row.get("description", "")
    url = row.get("linkedin_url", "")
    position = row.get("result_position", "")

    middle_name = ""
    if source_data:
        middle_name = source_data.get("middle_name", "")

    # Pre-compute shared values to avoid redundant work across sub-functions
    slug_parts = parse_slug(url)
    normalized_text = normalize(title + " " + description)
    first_variants = get_name_variants(first_name.lower().strip())

    signals = {}

    # Primary signal: name match (80 pts)
    matched, name_detail = name_matches(
        first_name, last_name, title, url, middle_name,
        _slug_parts=slug_parts, _first_variants=first_variants,
    )
    if matched:
        name_score = 80
    else:
        name_score = 0
    signals["name"] = {"score": name_score, "detail": name_detail}

    # Bonus signals (up to 20 pts total)
    b1, d1 = score_company_bonus(company, title, description, _normalized_text=normalized_text)
    signals["company"] = {"score": b1, "detail": d1}

    b2, d2 = score_position_bonus(position)
    signals["position"] = {"score": b2, "detail": d2}

    b3, d3 = score_slug_bonus(
        first_name, last_name, url,
        _slug_parts=slug_parts, _first_variants=first_variants,
    )
    signals["slug"] = {"score": b3, "detail": d3}

    b4, d4 = score_location_bonus(title, description, _normalized_text=normalized_text)
    signals["location"] = {"score": b4, "detail": d4}

    # Source-data bonuses
    b5, d5 = 0, "no_source_data"
    b6, d6 = 0, "no_source_data"
    if source_data:
        b5, d5 = score_location_from_source(
            title, description,
            source_data.get("source_city", ""),
            source_data.get("source_state", ""),
            _normalized_text=normalized_text,
        )
        b6, d6 = score_middle_initial_bonus(
            title, description, url, middle_name,
            _normalized_text=normalized_text, _slug_parts=slug_parts,
        )
    signals["source_location"] = {"score": b5, "detail": d5}
    signals["middle_initial"] = {"score": b6, "detail": d6}

    total = name_score + b1 + b2 + b3 + b4 + b5 + b6
    # Cap at 100
    total = min(total, 100)

    return total, signals


# ─── Query Reformulation ──────────────────────────────────────────────────────


def generate_reformulated_queries(fields):
    """
    Generate fallback query variants for a failed query.
    1. Drop company name
    2. Try nickname variants
    """
    first = fields["first_name"]
    last = fields["last_name"]
    company = fields.get("company", "")

    queries = []

    # Variant 1: Drop company, just name + LinkedIn
    if company:
        queries.append(f'"{first}" "{last}" "LinkedIn"')

    # Variant 2: Try nickname variants
    first_variants = get_name_variants(first.lower())
    for variant in sorted(first_variants):
        if variant.lower() != first.lower():
            variant_title = variant.capitalize()
            q = f'"{variant_title}" "{last}" "LinkedIn"'
            queries.append(q)
            break  # Only first variant

    return queries[:3]


# ─── Main Processing ─────────────────────────────────────────────────────────


def main():
    print("=" * 70)
    print("LinkedIn Profile Match Confidence Scoring Engine")
    print("=" * 70)
    print()

    # Load results
    print("[1/4] Loading search results...")
    if not os.path.exists(RESULTS_CSV):
        print(f"  ERROR: Results file not found: {RESULTS_CSV}")
        return

    results = []
    with open(RESULTS_CSV, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(row)

    total_rows = len(results)
    with_url = [r for r in results if r.get("linkedin_url")]
    no_match = [r for r in results if not r.get("linkedin_url")]
    print(f"  Total rows: {total_rows}")
    print(f"  With LinkedIn URL: {len(with_url)}")
    print(f"  No match (0 results): {len(no_match)}")
    print()

    # Group results by query
    print("[2/4] Scoring results...")
    query_groups = defaultdict(list)
    for row in results:
        query_groups[row["search_query"]].append(row)

    scored_results = []
    best_matches = []
    no_confident_match_queries = []
    score_distribution = {"high_80plus": 0, "medium_40_79": 0, "low_lt40": 0, "no_url": 0}

    for query, rows in query_groups.items():
        fields = parse_query_fields(query)

        query_scored = []
        for row in rows:
            url = row.get("linkedin_url", "")
            if not url:
                scored_results.append({
                    "search_query": query,
                    "first_name": fields["first_name"],
                    "last_name": fields["last_name"],
                    "company": fields.get("company", ""),
                    "linkedin_url": "",
                    "profile_title": "",
                    "description": row.get("description", ""),
                    "confidence_score": 0,
                    "match_signals": "no_linkedin_url",
                    "is_best_match": False,
                })
                score_distribution["no_url"] += 1
                continue

            score, signals = compute_confidence_score(row, fields)
            signal_summary = "; ".join(
                f"{k}={v['score']}({v['detail']})" for k, v in signals.items()
            )

            scored_row = {
                "search_query": query,
                "first_name": fields["first_name"],
                "last_name": fields["last_name"],
                "company": fields.get("company", ""),
                "linkedin_url": url,
                "profile_title": row.get("profile_title", ""),
                "description": row.get("description", ""),
                "confidence_score": score,
                "match_signals": signal_summary,
                "is_best_match": False,
            }
            query_scored.append((score, int(row.get("result_position") or 99), scored_row))
            scored_results.append(scored_row)

        # Select best match for this query
        if query_scored:
            query_scored.sort(key=lambda x: (-x[0], x[1]))
            best_score, best_pos, best_row = query_scored[0]
            best_row["is_best_match"] = True

            if best_score >= 80:
                score_distribution["high_80plus"] += 1
                best_matches.append(best_row)
            elif best_score >= 40:
                score_distribution["medium_40_79"] += 1
                best_matches.append(best_row)
            else:
                score_distribution["low_lt40"] += 1
                no_confident_match_queries.append((query, fields))
        else:
            no_confident_match_queries.append((query, fields))

    print(f"  Scored {len(scored_results)} rows across {len(query_groups)} queries")
    print(f"  High confidence (>=80%): {score_distribution['high_80plus']}")
    print(f"  Medium (40-79%): {score_distribution['medium_40_79']}")
    print(f"  Low (<40%): {score_distribution['low_lt40']}")
    print(f"  No URL: {score_distribution['no_url']}")
    print()

    # Write output files
    print("[3/4] Writing output files...")
    fieldnames = [
        "search_query", "first_name", "last_name", "company",
        "linkedin_url", "profile_title", "description", "confidence_score",
        "match_signals", "is_best_match",
    ]

    # All scored results
    with open(OUTPUT_SCORED, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(scored_results)
    print(f"  Written: {OUTPUT_SCORED} ({len(scored_results)} rows)")

    # High confidence only (best matches with score >= 80)
    high_conf = [r for r in scored_results if r["is_best_match"] and r["confidence_score"] >= 80]
    with open(OUTPUT_HIGH_CONF, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(high_conf)
    print(f"  Written: {OUTPUT_HIGH_CONF} ({len(high_conf)} rows)")

    # Reformulated queries
    print("[4/4] Generating reformulated queries...")
    reformulated = []
    for query, fields in no_confident_match_queries:
        new_queries = generate_reformulated_queries(fields)
        reformulated.extend(new_queries)

    reformulated = list(dict.fromkeys(reformulated))

    with open(OUTPUT_REFORMULATED, "w", encoding="utf-8") as f:
        for q in reformulated:
            f.write(q + "\n")
    print(f"  Written: {OUTPUT_REFORMULATED} ({len(reformulated)} queries)")

    # Summary stats
    summary = {
        "total_queries": len(query_groups),
        "total_result_rows": total_rows,
        "rows_with_linkedin_url": len(with_url),
        "rows_without_url": len(no_match),
        "score_distribution": {
            "high_confidence_gte80": score_distribution["high_80plus"],
            "medium_40_79": score_distribution["medium_40_79"],
            "low_lt40": score_distribution["low_lt40"],
            "no_url": score_distribution["no_url"],
        },
        "high_confidence_matches": len(high_conf),
        "reformulated_queries_generated": len(reformulated),
        "match_rate_percent": round(
            score_distribution["high_80plus"] / len(query_groups) * 100, 1
        ) if query_groups else 0,
    }

    with open(OUTPUT_SUMMARY, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Written: {OUTPUT_SUMMARY}")

    # Print summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total queries processed:          {summary['total_queries']}")
    print(f"  High confidence matches (>=80%):  {summary['high_confidence_matches']}")
    print(f"  Medium confidence (40-79%):       {score_distribution['medium_40_79']}")
    print(f"  Low/no match:                     {score_distribution['low_lt40'] + score_distribution['no_url']}")
    print(f"  Match rate:                       {summary['match_rate_percent']}%")
    print(f"  Reformulated queries:             {summary['reformulated_queries_generated']}")
    print()
    print("Done!")


if __name__ == "__main__":
    main()
