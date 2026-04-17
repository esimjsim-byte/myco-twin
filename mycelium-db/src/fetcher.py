"""NCBI Entrez API wrapper.

Fetches PubMed / PMC records related to mushroom mycelium cultivation
(carbon sources, nitrogen sources, biomass yields, β-glucan content, etc.)
using Biopython's Entrez module.
"""

# TODO: load NCBI_EMAIL and NCBI_API_KEY from environment (python-dotenv).
# TODO: implement search_pubmed(query, retmax) -> list[pmid] using Entrez.esearch.
# TODO: implement fetch_abstracts(pmids) -> list[dict] using Entrez.efetch (XML via lxml).
# TODO: implement fetch_pmc_fulltext(pmcid) -> str for open-access full-text retrieval.
# TODO: add rate limiting (<=3 req/s without API key, <=10 req/s with key).
# TODO: add simple on-disk cache under data/cache/ keyed by (endpoint, params hash).
