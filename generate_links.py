import os
import sys
import pandas as pd
import urllib.parse

# 1. Exact file path on your Mac
file_path = "All WE contacts_vAIM1.0.xlsx"

print(f"Reading {file_path}... Please wait (large file).")

# 2. Load the Excel spreadsheet safely
if not os.path.exists(file_path):
    print(f"Error: Could not find the file '{file_path}' in the current directory.")
    sys.exit(1)

df = pd.read_excel(file_path)
print(f"Successfully loaded {len(df)} rows from the dataset.")

# 3. Create search queries: "FirstName" "LastName" "Company" LinkedIn
def build_query(row):
    fn = str(row['First Name']).strip() if pd.notna(row['First Name']) else ''
    ln = str(row['Last Name']).strip() if pd.notna(row['Last Name']) else ''
    co = str(row['Business name']).strip() if pd.notna(row['Business name']) else ''

    parts = []
    if fn:
        parts.append(f'"{fn}"')
    if ln:
        parts.append(f'"{ln}"')
    if co:
        parts.append(f'"{co}"')
    parts.append('"LinkedIn"')
    return ' '.join(parts)

print("Building search queries...")
raw_queries = df.apply(build_query, axis=1)

# 5. Convert text queries into clickable Google Search URLs
def convert_to_google_link(query):
    clean_query = " ".join(query.split())
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(clean_query)

df['Google Search Link'] = raw_queries.apply(convert_to_google_link)
df['Search Query'] = raw_queries

# 6. Export back into an updated Excel spreadsheet
output_excel = "All_WE_contacts_with_Search_Links.xlsx"
df.to_excel(output_excel, index=False)

# 7. Export raw queries as text (for Apify batch processing)
output_queries = "linkedin_search_queries.txt"
with open(output_queries, 'w') as f:
    for q in raw_queries:
        f.write(q + '\n')

# 8. Export a raw text list of URLs
output_txt = "all_25000_linkedin_search_links.txt"
df['Google Search Link'].to_csv(output_txt, index=False, header=False)

print("\nProcess successfully complete!")
print(f"1. New Excel sheet created: {output_excel}")
print(f"2. Search queries file: {output_queries}")
print(f"3. Raw URL file created: {output_txt}")
print(f"   Query format: \"FirstName\" \"LastName\" \"Company\" \"LinkedIn\"")
