import requests
import json
from pathlib import Path

PATENTS_DIR = Path("data/raw/patents")
PATENTS_DIR.mkdir(parents=True, exist_ok=True)

queries = [
    "cryptographic hashing ledger",
    "distributed hash chain encryption",
    "secure transaction ledger blockchain",
    "password hashing authentication module",
    "AES encryption data protection",
]

for query in queries:
    print(f"Fetching: {query}")
    try:
        resp = requests.get(
            "https://api.patentsview.org/patents/query",
            params={
                "q": json.dumps({"_text_any": {"patent_abstract": query}}),
                "f": json.dumps([
                    "patent_number", "patent_title",
                    "patent_abstract", "patent_date",
                    "assignees.assignee_organization"
                ]),
                "o": json.dumps({"per_page": 5}),
            },
            timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            patents = data.get("patents") or []
            for p in patents:
                if not p or not p.get("patent_number"):
                    continue
                assignee = "Unknown"
                if p.get("assignees"):
                    assignee = p["assignees"][0].get("assignee_organization", "Unknown")
                filename = PATENTS_DIR / f"patent_{p['patent_number']}.txt"
                content  = f"Patent Number: {p['patent_number']}\n"
                content += f"Title: {p.get('patent_title', '')}\n"
                content += f"Assignee: {assignee}\n"
                content += f"Grant Date: {p.get('patent_date', '')}\n\n"
                content += f"Abstract: {p.get('patent_abstract', '')}\n"
                filename.write_text(content, encoding="utf-8")
                print(f"  Saved: {filename.name}")
        else:
            print(f"  API error {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"  Failed: {e}")

print(f"\nDone. Patents saved to {PATENTS_DIR}")
print(f"Total files: {len(list(PATENTS_DIR.glob('*.txt')))}")