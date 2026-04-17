"""Streamlit front-end for the mycelium cultivation database.

Lets users browse extracted experiments and compare biomass / β-glucan
outcomes across carbon sources, nitrogen sources, and C/N ratios.
"""

# TODO: page 1 — Search & Ingest: enter PubMed query, trigger fetcher + extractor,
#       preview extracted rows before committing to the DB.
# TODO: page 2 — Browse: filter by species, carbon source, nitrogen source, year.
# TODO: page 3 — Compare: Plotly box/scatter plots of biomass and β-glucan
#       grouped by carbon/nitrogen source and binned C/N ratio.
# TODO: page 4 — Export: download filtered subset as CSV via pandas.
# TODO: wire everything to schema.get_session() for reads and writes.
