"""Exploratory analysis of merged_unique.json to inform extractor design."""
import json
import re
from collections import Counter
from pathlib import Path


DATA_PATH = Path("data/raw/merged_unique.json")


def count_keyword_mentions(records, category_name, keywords):
    print(f"\n[{category_name}]")
    kw_counter = Counter()
    for r in records:
        abstract = (r.get("abstract") or "").lower()
        for kw in keywords:
            if kw.lower() in abstract:
                kw_counter[kw] += 1
    for kw, count in kw_counter.most_common():
        pct = count / len(records) * 100
        bar = "#" * int(pct / 2)
        print(f"  {count:>3d} ({pct:>4.1f}%)  {kw:<30s} {bar}")


def main():
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    records = data["records"]
    total = len(records)
    print(f"Total records: {total}")
    print(f"With PMC ID: {sum(1 for r in records if r.get('pmcid'))}")
    print(f"With full-text: {sum(1 for r in records if r.get('fulltext'))}")
    print()

    years = [int(r["year"]) for r in records if r.get("year") and str(r["year"]).isdigit()]
    year_counter = Counter()
    for y in years:
        decade = (y // 5) * 5
        year_counter[decade] += 1
    print("=== Year distribution (5-year bins) ===")
    for decade in sorted(year_counter):
        bar = "#" * year_counter[decade]
        print(f"  {decade}-{decade+4}: {year_counter[decade]:>3d} {bar}")
    print()

    journal_counter = Counter(r.get("journal", "Unknown") for r in records)
    print("=== Top 10 journals ===")
    for journal, count in journal_counter.most_common(10):
        print(f"  {count:>3d}  {journal}")
    print()

    print("=== Keyword frequency in abstracts ===")
    carbon_sources = [
        "glucose", "sucrose", "fructose", "maltose", "lactose",
        "starch", "xylose", "cellobiose", "mannose", "arabinose",
        "molasses", "glycerol"
    ]
    nitrogen_sources = [
        "yeast extract", "peptone", "tryptone", "soybean",
        "urea", "ammonium sulfate", "ammonium nitrate",
        "sodium nitrate", "potassium nitrate",
        "glutamate", "glutamine", "asparagine", "corn steep"
    ]
    metrics = [
        "biomass", "dry weight", "mycelial growth", "mycelium",
        "beta-glucan", "lentinan", "polysaccharide",
        "exopolysaccharide", "EPS", "intracellular polysaccharide", "IPS"
    ]
    culture_types = [
        "submerged", "liquid culture", "solid-state", "shake flask",
        "bioreactor", "fermenter"
    ]
    analysis_methods = [
        "response surface", "RSM", "Box-Behnken", "Plackett-Burman",
        "C/N ratio", "central composite", "Taguchi"
    ]

    count_keyword_mentions(records, "Carbon sources", carbon_sources)
    count_keyword_mentions(records, "Nitrogen sources", nitrogen_sources)
    count_keyword_mentions(records, "Metrics/Products", metrics)
    count_keyword_mentions(records, "Culture types", culture_types)
    count_keyword_mentions(records, "Analysis methods", analysis_methods)
    print()

    print("=== Numerical data presence in abstracts ===")
    has_gl = 0
    has_mgg = 0
    has_pct = 0
    has_temp = 0
    for r in records:
        abstract = r.get("abstract") or ""
        if re.search(r"\d+\.?\d*\s*g\s*/\s*L", abstract, re.IGNORECASE):
            has_gl += 1
        if re.search(r"\d+\.?\d*\s*mg\s*/\s*g", abstract, re.IGNORECASE):
            has_mgg += 1
        if re.search(r"\d+\.?\d*\s*%", abstract):
            has_pct += 1
        if re.search(r"\d+\s*°?C", abstract):
            has_temp += 1
    print(f"  Abstracts with g/L concentrations: {has_gl} ({has_gl/total*100:.0f}%)")
    print(f"  Abstracts with mg/g concentrations: {has_mgg} ({has_mgg/total*100:.0f}%)")
    print(f"  Abstracts with percentages: {has_pct} ({has_pct/total*100:.0f}%)")
    print(f"  Abstracts with temperatures: {has_temp} ({has_temp/total*100:.0f}%)")
    print()

    print("=== Quick relevance signals ===")
    optimization_keywords = ["optimi", "optimum", "maximum yield", "enhanced"]
    has_optimization = sum(
        1 for r in records
        if any(k in (r.get("abstract") or "").lower() for k in optimization_keywords)
    )
    has_medium = sum(
        1 for r in records
        if "medium" in (r.get("abstract") or "").lower()
        or "media" in (r.get("abstract") or "").lower()
    )
    has_both_cn = sum(
        1 for r in records
        if "carbon" in (r.get("abstract") or "").lower()
        and "nitrogen" in (r.get("abstract") or "").lower()
    )
    print(f"  Mentions optimization: {has_optimization} ({has_optimization/total*100:.0f}%)")
    print(f"  Mentions 'medium'/'media': {has_medium} ({has_medium/total*100:.0f}%)")
    print(f"  Mentions both carbon AND nitrogen: {has_both_cn} ({has_both_cn/total*100:.0f}%)")


if __name__ == "__main__":
    main()