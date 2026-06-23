#!/usr/bin/env python3
"""
This script will output search queries for LinkedIn profiles.
The actual WebSearch calls will be made by Claude using the queries generated here.
"""
import json

# Load prospects
with open('/Users/nathaniel/Desktop/Cl3/ultra_hnw_prospects_to_search.json', 'r') as f:
    prospects = json.load(f)

# Generate search queries
queries = []
for prospect in prospects:
    first_name = prospect['first_name']
    last_name = prospect['last_name']

    # Create LinkedIn-specific search query
    query = f'site:linkedin.com/in/ "{first_name} {last_name}"'

    queries.append({
        'row_index': prospect['row_index'],
        'first_name': first_name,
        'last_name': last_name,
        'business_name': prospect['business_name'],
        'city': prospect['city'],
        'state': prospect['state'],
        'query': query
    })

# Save queries
with open('/Users/nathaniel/Desktop/Cl3/linkedin_search_queries.json', 'w') as f:
    json.dump(queries, f, indent=2)

print(f"Generated {len(queries)} search queries")
print("First 5 queries:")
for i, q in enumerate(queries[:5]):
    print(f"{i+1}. {q['query']}")
