#!/usr/bin/env python3
import csv
import json

# Read the CSV and filter for Ultra-HNW prospects (Total Asset Rating = 12 OR Net Worth Rating = 12)
input_file = '/Users/nathaniel/Desktop/Cl3/agentic_enrichment_input.csv'
output_prospects = '/Users/nathaniel/Desktop/Cl3/ultra_hnw_prospects_to_search.json'

prospects = []

with open(input_file, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for idx, row in enumerate(reader):
        total_asset_rating = row.get('Total Asset Rating', '').strip()
        net_worth_rating = row.get('Net Worth Rating', '').strip()

        # Filter for Ultra-HNW: rating 12 in either category
        if total_asset_rating == '12' or net_worth_rating == '12':
            prospects.append({
                'row_index': idx,
                'first_name': row.get('First Name', '').strip(),
                'last_name': row.get('Last Name', '').strip(),
                'business_name': row.get('Business name', '').strip(),
                'city': row.get('City', '').strip(),
                'state': row.get('State', '').strip(),
                'total_asset_rating': total_asset_rating,
                'net_worth_rating': net_worth_rating
            })

# Write prospects to JSON for processing
with open(output_prospects, 'w', encoding='utf-8') as f:
    json.dump(prospects, f, indent=2)

print(f"Found {len(prospects)} Ultra-HNW prospects (Total Asset Rating = 12 OR Net Worth Rating = 12)")
print(f"Prospects written to: {output_prospects}")
