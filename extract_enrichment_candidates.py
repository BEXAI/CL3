#!/usr/bin/env python3
"""
Extract LinkedIn enrichment candidates from linkedin_master_25003.csv

Identifies prospects that need agentic LinkedIn enrichment based on:
- Low confidence LinkedIn matches (Confidence_Score < 80 OR LinkedIn_URL is empty)
- High wealth/business signals that make them valuable targets

Author: Claude
Date: 2026-06-17
"""

import pandas as pd
import json
from datetime import datetime

def main():
    print("=" * 80)
    print("LinkedIn Enrichment Candidate Extraction")
    print("=" * 80)
    print()

    # Read the CSV file
    print("Loading linkedin_master_25003.csv...")
    df = pd.read_csv('/Users/nathaniel/Desktop/Cl3/linkedin_master_25003.csv')
    print(f"✓ Loaded {len(df):,} total records with {len(df.columns)} columns")
    print()

    # Filter for low-confidence matches
    print("Filtering for enrichment candidates...")
    print("  Criteria: Confidence_Score < 80 OR LinkedIn_URL is empty")

    # Handle both missing values and low scores
    low_confidence = df[
        (df['Confidence_Score'].isna()) |
        (df['Confidence_Score'] < 80) |
        (df['LinkedIn_URL'].isna()) |
        (df['LinkedIn_URL'].str.strip() == '')
    ].copy()

    print(f"  → Found {len(low_confidence):,} low-confidence/missing LinkedIn records")
    print()

    # Define wealth signals
    wealth_signals = {
        'Net Worth Rating >= 8': (low_confidence['Net Worth Rating'] >= 8),
        'Total Asset Rating >= 8': (low_confidence['Total Asset Rating'] >= 8),
        'Aircraft Owner == Y': (low_confidence['Aircraft Owner'] == 'Y'),
        'Board Member == Y': (low_confidence['Board Member'] == 'Y')
    }

    # Combine wealth signals (at least one must be True)
    has_wealth_signal = pd.Series([False] * len(low_confidence), index=low_confidence.index)
    for signal_name, signal_mask in wealth_signals.items():
        has_wealth_signal = has_wealth_signal | signal_mask

    # Filter to high-value candidates
    enrichment_candidates = low_confidence[has_wealth_signal].copy()

    print("High-value wealth signals applied:")
    for signal_name, signal_mask in wealth_signals.items():
        count = signal_mask.sum()
        print(f"  • {signal_name}: {count:,} prospects")
    print()
    print(f"✓ Identified {len(enrichment_candidates):,} high-value enrichment candidates")
    print()

    # Create wealth tier breakdown for statistics
    def categorize_wealth_tier(row):
        """Categorize prospect by wealth tier based on multiple signals"""
        net_worth = row.get('Net Worth Rating', 0)
        asset_rating = row.get('Total Asset Rating', 0)
        aircraft = row.get('Aircraft Owner', 'N')
        board = row.get('Board Member', 'Y')

        if net_worth >= 11 or asset_rating >= 11:
            return 'Ultra High Net Worth ($100M+)'
        elif net_worth >= 9 or asset_rating >= 9:
            return 'Very High Net Worth ($25M-$100M)'
        elif net_worth >= 8 or asset_rating >= 8:
            return 'High Net Worth ($10M-$25M)'
        elif aircraft == 'Y' or board == 'Y':
            return 'Aircraft Owner/Board Member'
        else:
            return 'Other High-Value Signal'

    enrichment_candidates['Wealth_Tier'] = enrichment_candidates.apply(categorize_wealth_tier, axis=1)

    # Generate statistics
    tier_breakdown = enrichment_candidates['Wealth_Tier'].value_counts().to_dict()

    # Calculate confidence score distribution for candidates
    conf_score_dist = {}
    if 'Confidence_Score' in enrichment_candidates.columns:
        conf_score_dist = {
            'missing': int(enrichment_candidates['Confidence_Score'].isna().sum()),
            'score_0_20': int(((enrichment_candidates['Confidence_Score'] >= 0) &
                              (enrichment_candidates['Confidence_Score'] < 20)).sum()),
            'score_20_40': int(((enrichment_candidates['Confidence_Score'] >= 20) &
                               (enrichment_candidates['Confidence_Score'] < 40)).sum()),
            'score_40_60': int(((enrichment_candidates['Confidence_Score'] >= 40) &
                               (enrichment_candidates['Confidence_Score'] < 60)).sum()),
            'score_60_80': int(((enrichment_candidates['Confidence_Score'] >= 60) &
                               (enrichment_candidates['Confidence_Score'] < 80)).sum())
        }

    # Create summary statistics
    summary = {
        'generated_at': datetime.now().isoformat(),
        'total_records_processed': int(len(df)),
        'low_confidence_records': int(len(low_confidence)),
        'high_value_enrichment_candidates': int(len(enrichment_candidates)),
        'enrichment_rate': f"{(len(enrichment_candidates) / len(df) * 100):.2f}%",
        'wealth_tier_breakdown': {k: int(v) for k, v in tier_breakdown.items()},
        'confidence_score_distribution': conf_score_dist,
        'wealth_signal_counts': {k: int(v.sum()) for k, v in wealth_signals.items()}
    }

    # Save outputs
    print("Saving output files...")

    # Drop the temporary Wealth_Tier column before saving
    enrichment_candidates_output = enrichment_candidates.drop(columns=['Wealth_Tier'])

    # Save CSV with all columns preserved
    output_csv = '/Users/nathaniel/Desktop/Cl3/agentic_enrichment_input.csv'
    enrichment_candidates_output.to_csv(output_csv, index=False)
    print(f"  ✓ Saved {output_csv}")
    print(f"    → {len(enrichment_candidates_output):,} rows × {len(enrichment_candidates_output.columns)} columns")

    # Save JSON summary
    output_json = '/Users/nathaniel/Desktop/Cl3/enrichment_candidates_summary.json'
    with open(output_json, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"  ✓ Saved {output_json}")
    print()

    # Print summary to stdout
    print("=" * 80)
    print("ENRICHMENT CANDIDATES SUMMARY")
    print("=" * 80)
    print()
    print(f"Total Records Processed:          {summary['total_records_processed']:,}")
    print(f"Low-Confidence LinkedIn Records:  {summary['low_confidence_records']:,}")
    print(f"High-Value Enrichment Candidates: {summary['high_value_enrichment_candidates']:,}")
    print(f"Enrichment Rate:                  {summary['enrichment_rate']}")
    print()
    print("WEALTH TIER BREAKDOWN:")
    print("-" * 80)
    for tier, count in sorted(summary['wealth_tier_breakdown'].items(),
                              key=lambda x: x[1], reverse=True):
        pct = (count / summary['high_value_enrichment_candidates'] * 100)
        print(f"  {tier:<40} {count:>6,} ({pct:>5.1f}%)")
    print()
    print("CONFIDENCE SCORE DISTRIBUTION:")
    print("-" * 80)
    for score_range, count in summary['confidence_score_distribution'].items():
        pct = (count / summary['high_value_enrichment_candidates'] * 100)
        print(f"  {score_range:<20} {count:>6,} ({pct:>5.1f}%)")
    print()
    print("WEALTH SIGNAL COUNTS (may overlap):")
    print("-" * 80)
    for signal, count in summary['wealth_signal_counts'].items():
        pct = (count / summary['high_value_enrichment_candidates'] * 100)
        print(f"  {signal:<40} {count:>6,} ({pct:>5.1f}%)")
    print()
    print("=" * 80)
    print("Extraction complete!")
    print("=" * 80)

if __name__ == '__main__':
    main()
