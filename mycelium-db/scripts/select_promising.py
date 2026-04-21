"""Select promising papers for 2nd pilot extraction.

Criteria (any combination that scores high):
  - source_queries contains 'rsm' or 'betaglucan' (strong relevance signal)
  - journal is in cultivation/polysaccharide focused list
  - has PMC full-text
  - year >= 2018 (modern optimization research era)

Output: data/raw/promising_pilot.json (8 papers, same schema as merged_unique)
"""
import json
from pathlib import Path


INPUT = Path("data/raw/merged_unique.json")
OUTPUT = Path("data/raw/promising_pilot.json")
N_SELECT = 8

# Journals strongly aligned with our target (biomass/β-glucan cultivation)
CULTIVATION_JOURNALS = {
    "Bioresour Technol",
    "Bioresource Technology",
    "Int J Biol Macromol",
    "International Journal of Biological Macromolecules",
    "Int J Med Mushrooms",
    "International Journal of Medicinal Mushrooms",
    "Appl Microbiol Biotechnol",
    "Applied Microbiology and Biotechnology",
    "J Biosci Bioeng",
    "Journal of Bioscience and Bioengineering",
    "Food Sci Biotechnol",
    "Enzyme Microb Technol",
    "Process Biochem",
}

# Strong relevance signal from query tags
PRIORITY_QUERIES = {"rsm", "betaglucan"}


def score_paper(paper: dict) -> int:
    """Higher score = more promising target for our use case."""
    score = 0

    # Must have PMC full-text (hard filter, score=-999 if missing)
    if not paper.get("fulltext"):
        return -999

    # +10 per priority query tag matched
    source_qs = set(paper.get("source_queries", []))
    score += 10 * len(source_qs & PRIORITY_QUERIES)

    # +5 for cultivation-focused journal
    journal = (paper.get("journal") or "").strip()
    if any(j.lower() in journal.lower() for j in CULTIVATION_JOURNALS):
        score += 5

    # +3 for recent year (2020+)
    year = paper.get("year")
    if year and str(year).isdigit():
        y = int(year)
        if y >= 2020:
            score += 3
        elif y >= 2018:
            score += 1

    # +2 for multi-query hits (covered by multiple themes)
    if len(source_qs) >= 2:
        score += 2

    # +1 bonus if abstract mentions key biological terms
    abstract = (paper.get("abstract") or "").lower()
    strong_signals = ["c/n ratio", "biomass", "submerged", "optimi", "response surface"]
    for signal in strong_signals:
        if signal in abstract:
            score += 1

    return score


def main():
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    records = data["records"]
    print(f"Loaded {len(records)} papers from {INPUT}")

    # Score all papers, sort descending
    scored = [(score_paper(p), p) for p in records]
    scored.sort(key=lambda x: -x[0])

    # Take top N with PMC full-text
    selected = [p for s, p in scored[:N_SELECT] if s >= 0]
    print(f"\n=== Top {len(selected)} promising papers ===")
    print(f"{'Score':>5s}  {'PMID':>10s}  {'Year':>4s}  {'Queries':<25s}  Journal")
    print("-" * 100)
    for s, p in scored[:N_SELECT]:
        if s < 0:
            continue
        queries = "+".join(p.get("source_queries", []))
        journal = (p.get("journal") or "")[:35]
        print(f"{s:>5d}  {p.get('pmid', ''):>10s}  {str(p.get('year', '')):>4s}  {queries:<25s}  {journal}")

    # Write selected subset in same format as merged_unique
    output = {
        "description": "Promising papers selected for 2nd pilot (by score)",
        "source_queries_count": 4,
        "unique_pmid_count": len(selected),
        "with_pmcid_count": sum(1 for p in selected if p.get("pmcid")),
        "with_fulltext_count": sum(1 for p in selected if p.get("fulltext")),
        "records": selected,
    }

    OUTPUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nWrote {len(selected)} papers to {OUTPUT}")


if __name__ == "__main__":
    main()