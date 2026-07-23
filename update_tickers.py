import json
import urllib.request
import re

SEC_URL = "https://www.sec.gov/files/company_tickers.json"
LOCAL_FILE = "backend/data/company_tickers.json"

def clean_title(title):
    # Remove common suffixes
    title = re.sub(r'(?i)\b(inc|corp|corporation|llc|plc|ltd|co|company)\.?\b', '', title)
    # Remove special chars and extra spaces
    title = re.sub(r'[^a-zA-Z0-9\s]', '', title)
    return title.strip().title()

def update_tickers():
    print("Downloading SEC tickers...")
    req = urllib.request.Request(SEC_URL, headers={'User-Agent': 'SyndraDataEngine/1.0 admin@syndradata.com'})
    with urllib.request.urlopen(req) as response:
        sec_data = json.loads(response.read().decode())
    
    print("Loading existing tickers...")
    try:
        with open(LOCAL_FILE, 'r', encoding='utf-8') as f:
            existing = json.load(f)
    except FileNotFoundError:
        existing = {}

    added = 0
    for key, data in sec_data.items():
        ticker = data['ticker'].upper()
        title = data['title']
        
        if ticker not in existing:
            aliases = [title.title()]
            cleaned = clean_title(title)
            if cleaned and cleaned not in aliases:
                aliases.append(cleaned)
            existing[ticker] = aliases
            added += 1

    print(f"Added {added} new tickers.")
    
    print("Saving back to file...")
    with open(LOCAL_FILE, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=2)

if __name__ == "__main__":
    update_tickers()
