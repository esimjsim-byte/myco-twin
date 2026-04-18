"""Merge multiple query results into a single deduplicated dataset."""
import json
from pathlib import Path


QUERY_FILES = [
    ("query1_submerged", "submerged"),
    ("query2_betaglucan", "betaglucan"),
    ("query3_solidstate", "solidstate"),
    ("query4_rsm", "rsm"),
]

OUTPUT_PATH = Path("data/raw/merged_unique.json")


def main():
    merged = {}

    for filename, tag in QUERY_FILES:
        path = Path("data/raw") / f"{filename}.json"
        if not path.exists():
            print(f"[skip] {filename}: file not found")
            continue

        data = json.loads(path.read_text(encoding="utf-8"))
        records = data.get("records", [])

        added = 0
        duplicated = 0
        for rec in records:
            pmid = rec.get("pmid")
            if not pmid:
                continue

            if pmid in merged:
                if tag not in merged[pmid]["source_queries"]:
                    merged[pmid]["source_queries"].append(tag)
                duplicated += 1
            else:
                new_rec = dict(rec)
                new_rec["source_queries"] = [tag]
                merged[pmid] = new_rec
                added += 1

        print(f"{filename:25s}: +{added:3d} new, {duplicated:3d} duplicate (tagged)")

    records_out = sorted(merged.values(), key=lambda r: r.get("pmid", ""))

    with_pmcid = sum(1 for r in records_out if r.get("pmcid"))
    with_fulltext = sum(1 for r in records_out if r.get("fulltext"))

    source_dist = {}
    for r in records_out:
        key = tuple(sorted(r["source_queries"]))
        source_dist[key] = source_dist.get(key, 0) + 1

    output = {
        "description": "Merged and deduplicated Lentinula edodes dataset",
        "source_queries_count": len(QUERY_FILES),
        "unique_pmid_count": len(records_out),
        "with_pmcid_count": with_pmcid,
        "with_fulltext_count": with_fulltext,
        "records": records_out,
    }

    OUTPUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print()
    print(f"=== Merged dataset written to {OUTPUT_PATH} ===")
    print(f"Unique PMIDs:        {len(records_out)}")
    print(f"With PMC ID:         {with_pmcid}")
    print(f"With PMC full-text:  {with_fulltext}")
    print()
    print("Source query combinations:")
    for combo, count in sorted(source_dist.items(), key=lambda x: -x[1]):
        combo_str = "+".join(combo)
        print(f"  {combo_str:40s} {count:>4d}")


if __name__ == "__main__":
    main()