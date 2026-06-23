#!/usr/bin/env python3
"""
Phase 2 — Prospect Qualification & Propensity Scoring Engine.

Reads linkedin_master_25003.csv (Phase 1 output) and scores each prospect
across 6 dimensions to produce a founding-member propensity tier list.

Scoring Sections (100 pts max):
  1. Title Seniority        (0-25)  — LinkedIn title executive keywords
  2. Wealth Composite       (0-30)  — Net worth, assets, income, cash, stock
  3. Real Estate / Aviation (0-15)  — RE value, property count, aircraft, boat
  4. Philanthropy / Influence(0-15) — Donations, board seats, GuideStar
  5. Business Ownership     (0-10)  — Co. value, sales volume, D&B/Hoovers
  6. LinkedIn Profile Strength(0-5) — Confidence score reachability bonus

Tiers: Platinum (75-100), Gold (60-74), Silver (45-59), Bronze (30-44), Prospect (0-29)
"""

import csv
import json
import re
import os
import statistics
import sys
from collections import defaultdict

# ─── Configuration ────────────────────────────────────────────────────────────

BASE_DIR = "/Users/nathaniel/Desktop/Cl3"
INPUT_CSV = os.path.join(BASE_DIR, "linkedin_master_25003.csv")
OUTPUT_CSV = os.path.join(BASE_DIR, "prospect_scores_25003.csv")
TIER_SUMMARY_JSON = os.path.join(BASE_DIR, "tier_summary.json")

HIGH_CONFIDENCE_THRESHOLD = 80

# ─── Helper: Safe integer parsing ─────────────────────────────────────────────

def safe_int(value, default=0):
    """Parse a string to int, returning default for empty/non-numeric values."""
    if not value or not value.strip():
        return default
    try:
        return int(value.strip())
    except (ValueError, TypeError):
        return default


def rating_to_points(value_str, mapping, default=0):
    """
    Look up points for a rating value using a mapping dict.
    Mapping keys are ints; ranges like '0-4' are expanded at call sites.
    """
    val = safe_int(value_str, -1)
    if val < 0:
        return default
    if val in mapping:
        return mapping[val]
    return default


# ─── Section 1: Title Seniority (0-25 pts) ───────────────────────────────────

# Keyword tiers ordered highest to lowest. Each entry: (label, points, patterns)
# Patterns are compiled regexes with word boundaries.

SENIORITY_TIERS = [
    (
        "C-Suite",
        25,
        re.compile(
            r"\bceo\b|\bchief\s+executive\b|\bchairman\b|\bchairwoman\b|\bchairperson\b"
            r"|\bchief\s+operating\s+officer\b|\bcoo\b|\bchief\s+financial\s+officer\b|\bcfo\b"
            r"|\bchief\s+investment\s+officer\b|\bcio\b|\bchief\s+technology\s+officer\b|\bcto\b"
            r"|\bchief\s+medical\s+officer\b|\bcmo\b|\bchief\s+legal\s+officer\b|\bclo\b"
            r"|\bchief\s+strategy\s+officer\b|\bcso\b"
            r"|\bchief\s+(?:executive|operating|financial|investment|technology|medical|legal"
            r"|strategy|marketing|revenue|people|information|administrative|compliance|commercial"
            r"|digital|risk|data|product|human|growth|innovation|sustainability|communications?"
            r"|development|diversity|experience|transformation|security|nursing|scientific"
            r"|creative|analytics|procurement|supply)\b"
        ),
    ),
    (
        "Founder/Owner",
        22,
        re.compile(
            r"\bfounder\b|\bco-founder\b|\bcofounder\b|\bowner\b"
            r"|\bmanaging\s+(?:partner|member|director)\b|\bgeneral\s+partner\b|\bentrepreneur\b"
        ),
    ),
    (
        "President/EVP",
        18,
        re.compile(
            r"(?<!vice )\bpresident\b|\bexecutive\s+vice\s+president\b|\bevp\b"
            r"|\bgeneral\s+counsel\b|\bsenior\s+vice\s+president\b|\bsvp\b"
            r"|\bsenior\s+managing\s+director\b"
        ),
    ),
    (
        "VP/Director",
        14,
        re.compile(
            r"\bvice\s+president\b|\bvp\b|\bprincipal\b|\bpartner\b|\bdirector\b"
        ),
    ),
    (
        "Board/Investor",
        12,
        re.compile(
            r"\bboard\s+member\b|\bboard\s+of\s+directors\b|\btrustee\b"
            r"|\binvestor\b|\badvisory\s+board\b|\bboard\s+chair\b"
        ),
    ),
    (
        "Professional/Retired",
        8,
        re.compile(
            r"\bretired\b|\bformer\s+(?:ceo|president|chairman)\b"
            r"|\bphysician\b|\bsurgeon\b|\bprofessor\b|\battorney\b|\bcounsel\b"
        ),
    ),
    (
        "Other_Professional",
        4,
        re.compile(
            r"\bmanager\b|\bconsultant\b|\banalyst\b|\bengineer\b|\bspecialist\b|\bcoordinator\b"
        ),
    ),
    (
        "Unknown",
        0,
        re.compile(
            r"\bstudent\b|\bintern\b|\bassistant\b|\bentry\s+level\b"
            r"|\blooking\s+for\b|\bseeking\b"
        ),
    ),
]


def score_title_seniority(linkedin_title, linkedin_description, confidence_score):
    """
    Parse LinkedIn title for executive seniority keywords.
    Returns (points: int, label: str).
    Only scores if confidence_score >= 80 (high-confidence LinkedIn match).
    """
    if confidence_score < HIGH_CONFIDENCE_THRESHOLD:
        return 0, "No_LinkedIn_Match"

    # Normalize — treat literal "None" as empty
    title = (linkedin_title or "").strip()
    if title.lower() == "none":
        title = ""

    desc = (linkedin_description or "").strip()

    # Use title primarily; fall back to description if title is very short
    text = title.lower()
    if len(text) < 5 and desc:
        text = (title + " " + desc).lower()

    if not text.strip():
        return 0, "Unknown"

    # Scan tiers top-to-bottom, return first match
    for label, points, pattern in SENIORITY_TIERS:
        if pattern.search(text):
            return points, label

    # No keywords matched at all
    return 0, "Unknown"


# ─── Section 2: Wealth Composite (0-30 pts) ──────────────────────────────────

# Rating-to-points mappings (keys are integer rating values)
NET_WORTH_MAP = {12: 10, 11: 9, 10: 8, 9: 7, 8: 5, 7: 3, 6: 2, 5: 1, 4: 0, 3: 0, 2: 0, 1: 0, 0: 0}
TOTAL_ASSETS_MAP = {12: 8, 11: 7, 10: 6, 9: 5, 8: 3, 7: 2, 6: 1, 5: 0, 4: 0, 3: 0, 2: 0, 1: 0, 0: 0}
INCOME_MAP = {5: 5, 4: 4, 3: 2, 2: 1, 1: 0, 0: 0}
CASH_MAP = {4: 3, 3: 2, 2: 1, 1: 0, 0: 0}
STOCK_MAP = {8: 4, 7: 3, 6: 3, 5: 2, 4: 2, 3: 1, 2: 0, 1: 0, 0: 0}


def score_wealth(row):
    """
    Compute wealth composite score from source data rating columns.
    Returns int (0-30).
    """
    nw = rating_to_points(row.get("Net Worth Rating", ""), NET_WORTH_MAP)
    ta = rating_to_points(row.get("Total Asset Rating", ""), TOTAL_ASSETS_MAP)
    inc = rating_to_points(row.get("Income Rating", ""), INCOME_MAP)
    cash = rating_to_points(row.get("Cash on Hand Rating", ""), CASH_MAP)
    stk = rating_to_points(row.get("Stock Total Value Rating", ""), STOCK_MAP)
    return min(nw + ta + inc + cash + stk, 30)


# ─── Section 3: Real Estate + Aviation (0-15 pts) ────────────────────────────

RE_VALUE_MAP = {8: 6, 7: 5, 6: 4, 5: 3, 4: 2, 3: 1, 2: 1, 1: 0, 0: 0}


def score_real_estate_aviation(row):
    """
    Compute physical asset score from real estate and vehicle ownership.
    Returns int (0-15).
    """
    re_val = rating_to_points(row.get("Real Estate Value Rating", ""), RE_VALUE_MAP)

    count = safe_int(row.get("Real Estate Properties", ""), 0)
    re_count = 4 if count >= 10 else 3 if count >= 7 else 2 if count >= 4 else 1 if count >= 2 else 0

    aircraft = 3 if row.get("Aircraft Owner", "").strip().upper() == "Y" else 0
    boat = 2 if row.get("Boat Owner", "").strip().upper() == "Y" else 0

    return min(re_val + re_count + aircraft + boat, 15)


# ─── Section 4: Philanthropy + Influence (0-15 pts) ──────────────────────────

CHARITABLE_MAP = {14: 5, 13: 5, 12: 4, 11: 4, 10: 3, 9: 3, 8: 2, 7: 2, 6: 1, 5: 1, 4: 1, 3: 1, 2: 1, 1: 1, 0: 0}
POLITICAL_DON_MAP = {14: 3, 13: 3, 12: 2, 11: 2, 10: 2, 9: 1, 8: 1, 7: 0, 6: 0, 5: 0, 4: 0, 3: 0, 2: 0, 1: 0, 0: 0}

AFFILIATION_MAP = {
    "significant political support": 2,
    "older, significant political support": 2,
    "moderate political support": 1,
    "older, moderate political support": 1,
    "no political support": 0,
    "older with no political support": 0,
}


def score_philanthropy_influence(row):
    """
    Compute philanthropy and community influence score.
    Returns int (0-15).
    """
    charitable = rating_to_points(row.get("Charitable Donations Rating", ""), CHARITABLE_MAP)
    political = rating_to_points(row.get("Political Donations Rating", ""), POLITICAL_DON_MAP)

    board = 3 if row.get("Board Member", "").strip().upper() == "Y" else 0

    # GuideStar Foundation / Directors (only score valid values)
    _GUIDESTAR_VALID = {"High", "Medium", "Low", "Yes"}
    gs_found = row.get("QOM - GuideStar Foundation", "").strip()
    gs_dir = row.get("QOM - GuideStar Directors", "").strip()
    if gs_found == "High" or gs_dir == "High":
        foundation = 2
    elif gs_found in _GUIDESTAR_VALID or gs_dir in _GUIDESTAR_VALID:
        foundation = 1
    else:
        foundation = 0

    affiliation = row.get("Inclination: Affiliation", "").strip().lower()
    affil_pts = AFFILIATION_MAP.get(affiliation, 0)

    return min(charitable + political + board + foundation + affil_pts, 15)


# ─── Section 5: Business Ownership (0-10 pts) ────────────────────────────────

OWNERSHIP_MAP = {8: 4, 7: 4, 6: 3, 5: 3, 4: 2, 3: 2, 2: 1, 1: 1, 0: 0}
SALES_MAP = {8: 3, 7: 3, 6: 2, 5: 2, 4: 1, 3: 1, 2: 0, 1: 0, 0: 0}


def score_business_ownership(row):
    """
    Compute business ownership and scale score.
    Returns int (0-10).
    """
    own_val = rating_to_points(row.get("Co. Ownership Value Rating", ""), OWNERSHIP_MAP)
    sales = rating_to_points(row.get("Co. Sales Volume Rating", ""), SALES_MAP)

    db = 2 if row.get("QOM - D&B", "").strip() == "High" else 0
    hoovers = 1 if row.get("QOM - Hoovers", "").strip() == "High" else 0

    return min(own_val + sales + db + hoovers, 10)


# ─── Section 6: LinkedIn Profile Strength (0-5 pts) ──────────────────────────

def score_linkedin_strength(row):
    """
    Compute reachability bonus from LinkedIn profile match quality.
    Returns int (0-5).
    """
    conf = safe_int(row.get("Confidence_Score", ""), 0)
    has_url = bool(row.get("LinkedIn_URL", "").strip())

    if conf >= 90:
        return 5
    elif conf >= 80:
        return 4
    elif conf >= 40 and has_url:
        return 2
    elif has_url:
        return 1
    else:
        return 0


# ─── Tier Classification ─────────────────────────────────────────────────────

def classify_tier(total):
    """Assign member tier based on propensity total score."""
    if total >= 75:
        return "Platinum"
    elif total >= 60:
        return "Gold"
    elif total >= 45:
        return "Silver"
    elif total >= 30:
        return "Bronze"
    else:
        return "Prospect"


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("Phase 2 — Prospect Qualification & Propensity Scoring")
    print("=" * 70)
    print()

    # ── Step 1: Load input ──
    print("[1/5] Loading input data...")
    if not os.path.exists(INPUT_CSV):
        print(f"  ERROR: Input file not found: {INPUT_CSV}")
        sys.exit(1)

    rows = []
    with open(INPUT_CSV, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        original_fields = list(reader.fieldnames)
        for row in reader:
            rows.append(row)

    print(f"  Loaded {len(rows)} rows with {len(original_fields)} columns")
    print()

    # ── Step 2: Score all rows ──
    print("[2/5] Scoring all rows...")
    scored_rows = []
    section_totals = {
        "title_seniority": 0,
        "wealth": 0,
        "real_estate_aviation": 0,
        "philanthropy": 0,
        "business_ownership": 0,
        "linkedin_strength": 0,
    }
    seniority_label_counts = defaultdict(int)

    for i, row in enumerate(rows):
        conf_score = safe_int(row.get("Confidence_Score", ""), 0)

        # Section 1: Title seniority
        s1_pts, s1_label = score_title_seniority(
            row.get("LinkedIn_Title", ""),
            row.get("LinkedIn_Description", ""),
            conf_score,
        )

        # Section 2: Wealth
        s2_pts = score_wealth(row)

        # Section 3: Real estate + aviation
        s3_pts = score_real_estate_aviation(row)

        # Section 4: Philanthropy + influence
        s4_pts = score_philanthropy_influence(row)

        # Section 5: Business ownership
        s5_pts = score_business_ownership(row)

        # Section 6: LinkedIn strength
        s6_pts = score_linkedin_strength(row)

        # Total (capped at 100)
        total = min(s1_pts + s2_pts + s3_pts + s4_pts + s5_pts + s6_pts, 100)

        # Tier
        tier = classify_tier(total)

        # Append new columns to row
        row["Title_Seniority_Score"] = str(s1_pts)
        row["Title_Seniority_Label"] = s1_label
        row["Wealth_Score"] = str(s2_pts)
        row["RealEstate_Aviation_Score"] = str(s3_pts)
        row["Philanthropy_Influence_Score"] = str(s4_pts)
        row["Business_Ownership_Score"] = str(s5_pts)
        row["LinkedIn_Profile_Strength"] = str(s6_pts)
        row["Propensity_Total"] = str(total)
        row["Member_Tier"] = tier
        row["Tier_Rank"] = ""  # Assigned after sorting

        scored_rows.append(row)

        # Accumulate stats
        section_totals["title_seniority"] += s1_pts
        section_totals["wealth"] += s2_pts
        section_totals["real_estate_aviation"] += s3_pts
        section_totals["philanthropy"] += s4_pts
        section_totals["business_ownership"] += s5_pts
        section_totals["linkedin_strength"] += s6_pts
        seniority_label_counts[s1_label] += 1

        if (i + 1) % 5000 == 0:
            print(f"  Scored {i + 1:,} / {len(rows):,} rows...")

    print(f"  Scored all {len(scored_rows):,} rows")
    print()

    # ── Step 3: Rank within tiers ──
    print("[3/5] Ranking within tiers...")
    tier_groups = defaultdict(list)
    for row in scored_rows:
        tier_groups[row["Member_Tier"]].append(row)

    tier_order = ["Platinum", "Gold", "Silver", "Bronze", "Prospect"]
    tier_counts = {}

    for tier in tier_order:
        members = tier_groups.get(tier, [])
        # Sort by Propensity_Total desc, then Net Worth Rating desc as tiebreaker
        members.sort(
            key=lambda r: (-int(r["Propensity_Total"]), -safe_int(r.get("Net Worth Rating", ""), 0))
        )
        for rank, member in enumerate(members, start=1):
            member["Tier_Rank"] = str(rank)
        tier_counts[tier] = len(members)
        print(f"  {tier}: {len(members):,} members")

    print()

    # ── Step 4: Write output CSV ──
    print("[4/5] Writing output files...")
    new_fields = [
        "Title_Seniority_Score", "Title_Seniority_Label",
        "Wealth_Score", "RealEstate_Aviation_Score",
        "Philanthropy_Influence_Score", "Business_Ownership_Score",
        "LinkedIn_Profile_Strength", "Propensity_Total",
        "Member_Tier", "Tier_Rank",
    ]
    output_fields = original_fields + new_fields

    # Write rows in tier-rank order (Platinum first, then Gold, etc.)
    ordered_rows = []
    for tier in tier_order:
        members = tier_groups.get(tier, [])
        ordered_rows.extend(members)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=output_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ordered_rows)

    print(f"  Written: {OUTPUT_CSV} ({len(ordered_rows):,} rows, {len(output_fields)} columns)")

    # ── Step 5: Write tier summary JSON ──
    total_rows = len(scored_rows)
    propensity_values = [int(r["Propensity_Total"]) for r in scored_rows]

    summary = {
        "total_rows": total_rows,
        "total_columns": len(output_fields),
        "tier_distribution": {},
        "section_averages": {},
        "seniority_label_distribution": dict(seniority_label_counts),
        "propensity_stats": {
            "min": min(propensity_values),
            "max": max(propensity_values),
            "mean": round(sum(propensity_values) / total_rows, 1),
            "median": statistics.median(propensity_values),
        },
    }

    for tier in tier_order:
        count = tier_counts.get(tier, 0)
        summary["tier_distribution"][tier] = {
            "count": count,
            "pct": round(count / total_rows * 100, 1),
        }

    for section, total_pts in section_totals.items():
        summary["section_averages"][section] = round(total_pts / total_rows, 2)

    with open(TIER_SUMMARY_JSON, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"  Written: {TIER_SUMMARY_JSON}")
    print()

    # ── Final Summary ──
    print("=" * 70)
    print("PROPENSITY SCORING SUMMARY")
    print("=" * 70)
    print()
    print(f"  Total records scored:  {total_rows:,}")
    print(f"  Output columns:        {len(output_fields)}")
    print()
    print("  Tier Distribution:")
    for tier in tier_order:
        info = summary["tier_distribution"][tier]
        bar = "#" * (info["count"] // 100)
        print(f"    {tier:10s}  {info['count']:>6,}  ({info['pct']:>5.1f}%)  {bar}")
    print()
    print("  Section Averages (per record):")
    section_labels = {
        "title_seniority": ("Title Seniority", 25),
        "wealth": ("Wealth Composite", 30),
        "real_estate_aviation": ("RE + Aviation", 15),
        "philanthropy": ("Philanthropy", 15),
        "business_ownership": ("Business Ownership", 10),
        "linkedin_strength": ("LinkedIn Strength", 5),
    }
    for key, (label, mx) in section_labels.items():
        avg = summary["section_averages"][key]
        print(f"    {label:22s}  {avg:>5.1f} / {mx}")
    print()
    print(f"  Propensity Score Range: {summary['propensity_stats']['min']} — {summary['propensity_stats']['max']}")
    print(f"  Mean:   {summary['propensity_stats']['mean']}")
    print(f"  Median: {summary['propensity_stats']['median']}")
    print()
    print("  Seniority Labels (from LinkedIn titles):")
    for label, count in sorted(seniority_label_counts.items(), key=lambda x: -x[1]):
        print(f"    {label:25s}  {count:>6,}  ({count/total_rows*100:>5.1f}%)")
    print()
    print("DONE!")


if __name__ == "__main__":
    main()
