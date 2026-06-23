#!/usr/bin/env python3
"""
Generate comprehensive analytics report for the SYH LinkedIn enrichment pipeline.

Reads:
  - linkedin_master_25003_enriched.csv (or linkedin_master_25003.csv if enriched not available)
  - prospect_scores_25003.csv
  - tier_summary.json
  - enrichment_merge_summary.json (if available)

Outputs:
  - final_pipeline_report.json (comprehensive stats)
"""

import csv
import json
import os
import sys
from collections import Counter, defaultdict

BASE_DIR = "/Users/nathaniel/Desktop/Cl3"


def safe_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def safe_int(val):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def main():
    print("=" * 70)
    print("FINAL PIPELINE ANALYTICS REPORT")
    print("=" * 70)

    # Determine master file
    enriched = os.path.join(BASE_DIR, "linkedin_master_25003_enriched.csv")
    original = os.path.join(BASE_DIR, "linkedin_master_25003.csv")
    master_file = enriched if os.path.exists(enriched) else original

    print(f"\n[1/5] Loading master: {os.path.basename(master_file)}...")
    with open(master_file, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        master_rows = list(reader)
    total = len(master_rows)
    print(f"  {total} rows loaded")

    # LinkedIn match analysis
    print("\n[2/5] Analyzing LinkedIn match quality...")
    with_url = 0
    high_conf = 0
    medium_conf = 0
    low_conf = 0
    no_match = 0
    pass_distribution = Counter()
    confidence_buckets = Counter()

    for row in master_rows:
        url = row.get("LinkedIn_URL", "").strip()
        score = safe_float(row.get("Confidence_Score", 0))
        pass_name = row.get("Match_Pass", "").strip()

        if url:
            with_url += 1
        if score >= 80:
            high_conf += 1
        elif score >= 40:
            medium_conf += 1
        elif score > 0:
            low_conf += 1
        else:
            no_match += 1

        if pass_name:
            pass_distribution[pass_name] += 1

        # 10-point buckets
        bucket = int(score // 10) * 10
        confidence_buckets[bucket] += 1

    print(f"  With LinkedIn URL:     {with_url} ({with_url/total*100:.1f}%)")
    print(f"  High confidence >=80:  {high_conf} ({high_conf/total*100:.1f}%)")
    print(f"  Medium conf 40-79:     {medium_conf} ({medium_conf/total*100:.1f}%)")
    print(f"  Low confidence <40:    {low_conf} ({low_conf/total*100:.1f}%)")
    print(f"  No match:              {no_match} ({no_match/total*100:.1f}%)")

    # Load propensity scores
    print("\n[3/5] Analyzing propensity scores...")
    scores_file = os.path.join(BASE_DIR, "prospect_scores_25003.csv")
    propensity_data = {}
    tier_counts = Counter()

    if os.path.exists(scores_file):
        with open(scores_file, encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                record_id = row.get("WE Record ID", "").strip()
                tier = row.get("Member_Tier", "").strip()
                score = safe_float(row.get("Propensity_Total", 0))
                if record_id:
                    propensity_data[record_id] = {"tier": tier, "score": score}
                if tier:
                    tier_counts[tier] += 1

        print(f"  Loaded {len(propensity_data)} propensity scores")
        for tier in ["Platinum", "Gold", "Silver", "Bronze", "Prospect"]:
            count = tier_counts.get(tier, 0)
            print(f"    {tier}: {count} ({count/max(len(propensity_data),1)*100:.1f}%)")
    else:
        print("  WARNING: prospect_scores_25003.csv not found")

    # Cross-reference: LinkedIn match quality by propensity tier
    print("\n[4/5] Cross-referencing LinkedIn + propensity...")
    tier_match_quality = defaultdict(lambda: {"total": 0, "high_conf": 0, "with_url": 0})

    for row in master_rows:
        record_id = row.get("WE Record ID", "").strip()
        prop = propensity_data.get(record_id, {})
        tier = prop.get("tier", "Unknown")

        url = row.get("LinkedIn_URL", "").strip()
        score = safe_float(row.get("Confidence_Score", 0))

        tier_match_quality[tier]["total"] += 1
        if url:
            tier_match_quality[tier]["with_url"] += 1
        if score >= 80:
            tier_match_quality[tier]["high_conf"] += 1

    print(f"  {'Tier':<12} {'Total':>6} {'URL%':>6} {'High%':>6}")
    print(f"  {'-'*12} {'-'*6} {'-'*6} {'-'*6}")
    for tier in ["Platinum", "Gold", "Silver", "Bronze", "Prospect", "Unknown"]:
        data = tier_match_quality.get(tier, {"total": 0, "with_url": 0, "high_conf": 0})
        t = data["total"]
        if t == 0:
            continue
        url_pct = data["with_url"] / t * 100
        hi_pct = data["high_conf"] / t * 100
        print(f"  {tier:<12} {t:>6} {url_pct:>5.1f}% {hi_pct:>5.1f}%")

    # Wealth tier analysis
    print("\n[5/5] Wealth tier coverage...")
    wealth_tiers = {
        "12": "$500MM+",
        "11": "$100MM-$500MM",
        "10": "$50MM-$100MM",
        "9": "$25MM-$50MM",
    }
    wealth_match = defaultdict(lambda: {"total": 0, "high_conf": 0, "with_url": 0})

    for row in master_rows:
        rating = row.get("Total Asset Rating", "").strip()
        if rating not in wealth_tiers:
            continue

        tier_label = wealth_tiers[rating]
        url = row.get("LinkedIn_URL", "").strip()
        score = safe_float(row.get("Confidence_Score", 0))

        wealth_match[tier_label]["total"] += 1
        if url:
            wealth_match[tier_label]["with_url"] += 1
        if score >= 80:
            wealth_match[tier_label]["high_conf"] += 1

    print(f"  {'Wealth Tier':<20} {'Total':>6} {'URL%':>6} {'High%':>6}")
    print(f"  {'-'*20} {'-'*6} {'-'*6} {'-'*6}")
    for tier_label in ["$500MM+", "$100MM-$500MM", "$50MM-$100MM", "$25MM-$50MM"]:
        data = wealth_match.get(tier_label, {"total": 0, "with_url": 0, "high_conf": 0})
        t = data["total"]
        if t == 0:
            continue
        url_pct = data["with_url"] / t * 100
        hi_pct = data["high_conf"] / t * 100
        print(f"  {tier_label:<20} {t:>6} {url_pct:>5.1f}% {hi_pct:>5.1f}%")

    # Build report JSON
    report = {
        "pipeline_summary": {
            "total_prospects": total,
            "linkedin_url_coverage": with_url,
            "linkedin_url_coverage_pct": round(with_url / max(total, 1) * 100, 1),
            "high_confidence_matches": high_conf,
            "high_confidence_pct": round(high_conf / max(total, 1) * 100, 1),
            "medium_confidence_matches": medium_conf,
            "low_confidence_matches": low_conf,
            "no_match": no_match,
        },
        "confidence_distribution": {
            f"{k}-{k+9}": v for k, v in sorted(confidence_buckets.items())
        },
        "match_pass_distribution": dict(pass_distribution.most_common()),
        "propensity_tier_distribution": dict(tier_counts.most_common()),
        "linkedin_by_propensity_tier": {
            tier: {
                "total": data["total"],
                "with_url": data["with_url"],
                "high_confidence": data["high_conf"],
                "url_pct": round(data["with_url"] / max(data["total"], 1) * 100, 1),
                "high_conf_pct": round(data["high_conf"] / max(data["total"], 1) * 100, 1),
            }
            for tier, data in tier_match_quality.items()
            if data["total"] > 0
        },
        "linkedin_by_wealth_tier": {
            tier_label: {
                "total": data["total"],
                "with_url": data["with_url"],
                "high_confidence": data["high_conf"],
                "url_pct": round(data["with_url"] / max(data["total"], 1) * 100, 1),
                "high_conf_pct": round(data["high_conf"] / max(data["total"], 1) * 100, 1),
            }
            for tier_label, data in wealth_match.items()
            if data["total"] > 0
        },
    }

    # Load enrichment summary if available
    merge_summary_file = os.path.join(BASE_DIR, "enrichment_merge_summary.json")
    if os.path.exists(merge_summary_file):
        with open(merge_summary_file) as f:
            report["enrichment_merge"] = json.load(f)

    report_file = os.path.join(BASE_DIR, "final_pipeline_report.json")
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n  Written: {report_file}")

    # Final summary
    print("\n" + "=" * 70)
    print("PIPELINE METRICS SUMMARY")
    print("=" * 70)
    print(f"  Total prospects:            {total:,}")
    print(f"  LinkedIn URL coverage:      {with_url:,} ({with_url/total*100:.1f}%)")
    print(f"  High-confidence matches:    {high_conf:,} ({high_conf/total*100:.1f}%)")
    print(f"  Propensity tiers scored:    {len(propensity_data):,}")
    print(f"  Platinum prospects:         {tier_counts.get('Platinum', 0):,}")
    print(f"  Gold prospects:             {tier_counts.get('Gold', 0):,}")
    print()
    print("DONE!")


if __name__ == "__main__":
    main()
