"""Summarize collected PubMed data using fetcher's actual JSON structure."""
import json
from pathlib import Path


files = [
    "query1_submerged",
    "query2_betaglucan",
    "query3_solidstate",
    "query4_rsm",
]

total_papers = 0
total_pmc = 0
total_fulltext = 0
all_pmids = set()

print(f"{'Query':25s} {'total':>7s} {'pmc':>5s} {'fulltext':>9s} {'new_unique':>11s}")
print("-" * 62)

for name in files:
    path = Path("data/raw") / f"{name}.json"
    if not path.exists():
        print(f"{name:25s}  [missing]")
        continue
    
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("records", [])
    
    record_count = data.get("record_count", len(records))
    pmc_count = data.get("pmcid_count", 0)
    fulltext_count = data.get("fulltext_count", 0)
    
    pmids = {r.get("pmid") for r in records if isinstance(r, dict) and r.get("pmid")}
    new_pmids = pmids - all_pmids
    all_pmids |= pmids
    
    print(f"{name:25s} {record_count:>7d} {pmc_count:>5d} {fulltext_count:>9d} {len(new_pmids):>11d}")
    total_papers += record_count
    total_pmc += pmc_count
    total_fulltext += fulltext_count

print("-" * 62)
print(f"Sum (with duplicates):  {total_papers}")
print(f"Unique PMIDs:           {len(all_pmids)}")
print(f"Total PMC metadata:     {total_pmc}")
print(f"Total PMC full-text:    {total_fulltext}")
print(f"Duplicates removed:     {total_papers - len(all_pmids)}")
print()
print(f"Deduplication rate:     {(total_papers - len(all_pmids)) / total_papers * 100:.1f}%")