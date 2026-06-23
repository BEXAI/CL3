#!/usr/bin/env python3
"""
Compile LinkedIn search results from manual searches.
This script will be updated with search results as they come in.
"""
import csv
import json

# Manual search results collected so far
# Format: (row_index, first_name, last_name, business_name, linkedin_url, linkedin_title, confidence_score, match_strategy)

results = []

# Batch 1 results
results.append({
    'row_index': 1,
    'first_name': 'Pegula',
    'last_name': 'Kim',
    'business_name': 'Pegula Limited Partnership',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found in search'
})

results.append({
    'row_index': 78,
    'first_name': 'Allison',
    'last_name': 'Kanders',
    'business_name': '',
    'linkedin_url': 'https://www.linkedin.com/in/allison-kanders-b6827aa3',
    'linkedin_title': 'United States | Professional Profile',
    'confidence_score': 65,  # URL contains both names (40), title contains name (25)
    'match_strategy': 'Name in URL slug + Name in title'
})

results.append({
    'row_index': 83,
    'first_name': 'Christopher',
    'last_name': 'Pechock',
    'business_name': 'Matlinpatterson Globl Advsers',
    'linkedin_url': 'https://www.linkedin.com/in/chris-pechock-043314178/',
    'linkedin_title': 'Analyst at MatlinPatterson',
    'confidence_score': 80,  # URL contains parts of name (40), title has name (25), company match (15)
    'match_strategy': 'Name in URL + Title + Company match (MatlinPatterson)'
})

results.append({
    'row_index': 96,
    'first_name': 'Susan',
    'last_name': 'Sulentic',
    'business_name': 'Sulentic Family Foundation',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found'
})

results.append({
    'row_index': 140,
    'first_name': 'Laura',
    'last_name': 'Ubben',
    'business_name': '',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No exact match found (Laura Ubbenhorst found, different last name)'
})

results.append({
    'row_index': 194,
    'first_name': 'Kim',
    'last_name': 'Pegula',
    'business_name': 'Pegula Limited Partnership',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found'
})

results.append({
    'row_index': 195,
    'first_name': 'Kenneth',
    'last_name': 'Decubellis',
    'business_name': 'Allied Esports Entrmt Inc',
    'linkedin_url': 'https://www.linkedin.com/in/ken-decubellis-ba12b3/',
    'linkedin_title': 'Greater Minneapolis-St. Paul Area | Professional Profile',
    'confidence_score': 65,  # URL contains name parts (40), title has name (25)
    'match_strategy': 'Name in URL + Name in title'
})

results.append({
    'row_index': 208,
    'first_name': 'Deborah',
    'last_name': 'Wachtell',
    'business_name': "Women's And Children's Alliance",
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found'
})

results.append({
    'row_index': 251,
    'first_name': 'Christopher',
    'last_name': 'Shackelton',
    'business_name': 'Providence Service Corporation',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'Multiple Chris Shackleton profiles found, unable to determine correct match'
})

results.append({
    'row_index': 295,
    'first_name': 'Cathy',
    'last_name': 'Lasry',
    'business_name': 'The Lasry Family Foundation',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No specific LinkedIn profile found'
})

results.append({
    'row_index': 315,
    'first_name': 'Cosmas',
    'last_name': 'Lykos',
    'business_name': 'K2c Inc',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found (found in other business databases)'
})

results.append({
    'row_index': 340,
    'first_name': 'Nicole',
    'last_name': 'Salmasi',
    'business_name': 'Honor Wild Foundation',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found'
})

results.append({
    'row_index': 385,
    'first_name': 'Melinda',
    'last_name': 'Dabbiere',
    'business_name': 'Shepherd Center Foundation Inc',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found'
})

results.append({
    'row_index': 417,
    'first_name': 'Dathan',
    'last_name': 'Tate',
    'business_name': 'Dathan Tate Construction',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found'
})

results.append({
    'row_index': 454,
    'first_name': 'Reena',
    'last_name': 'Blumenfeld',
    'business_name': '',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found'
})

results.append({
    'row_index': 464,
    'first_name': 'Zita',
    'last_name': 'Ezpeleta',
    'business_name': 'School Of American Ballet Inc',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found'
})

results.append({
    'row_index': 487,
    'first_name': 'Ran',
    'last_name': 'Kohen',
    'business_name': 'Best Light Llc',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found'
})

results.append({
    'row_index': 544,
    'first_name': 'Rodger',
    'last_name': 'Krouse',
    'business_name': 'Sun Indalex Llc',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found (business info found elsewhere)'
})

results.append({
    'row_index': 556,
    'first_name': 'Bruce',
    'last_name': 'Karsh',
    'business_name': 'Ocm Investments Llc',
    'linkedin_url': 'https://www.linkedin.com/in/bruce-karsh-0a9010257/',
    'linkedin_title': 'Los Angeles, California, United States | Professional Profile',
    'confidence_score': 65,  # URL contains name (40), title contains location match (10), name in title (25)
    'match_strategy': 'Name in URL + Name in title + Location match'
})

results.append({
    'row_index': 785,
    'first_name': 'Elon',
    'last_name': 'Musk',
    'business_name': 'Tesla, Inc.',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'Multiple impersonator profiles found, no verified profile'
})

results.append({
    'row_index': 875,
    'first_name': 'Mitchell',
    'last_name': 'Rales',
    'business_name': 'Fortive Insurance Company',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found'
})

results.append({
    'row_index': 1001,
    'first_name': 'Eric',
    'last_name': 'Slifka',
    'business_name': 'Glp Finance Corp',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found (business info available)'
})

results.append({
    'row_index': 2132,
    'first_name': 'Mackenzie',
    'last_name': 'Bezos',
    'business_name': '',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found (now known as MacKenzie Scott)'
})

results.append({
    'row_index': 2137,
    'first_name': 'Ike',
    'last_name': 'Perlmutter',
    'business_name': 'Tot Funding Corp',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found'
})

results.append({
    'row_index': 2528,
    'first_name': 'Jeffrey',
    'last_name': 'Immelt',
    'business_name': 'General Electric Company',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found'
})

results.append({
    'row_index': 2575,
    'first_name': 'Len',
    'last_name': 'Blavatnik',
    'business_name': 'Access Industries  Inc',
    'linkedin_url': '',
    'linkedin_title': '',
    'confidence_score': 0,
    'match_strategy': 'No LinkedIn profile found'
})

print(f"Compiled {len(results)} search results so far")
print(f"Profiles found: {sum(1 for r in results if r['linkedin_url'])}")
print(f"No profiles: {sum(1 for r in results if not r['linkedin_url'])}")

# Save intermediate results
with open('/Users/nathaniel/Desktop/Cl3/linkedin_results_partial.json', 'w') as f:
    json.dump(results, f, indent=2)
