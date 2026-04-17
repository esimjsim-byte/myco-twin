"""SQLAlchemy ORM models for the mycelium cultivation database.

Tables (planned):
- Paper:     source publication metadata (pmid, doi, title, year, journal).
- Strain:    mushroom species / strain (genus, species, strain_code).
- Medium:    carbon source, nitrogen source, concentrations, C/N ratio.
- Experiment: links Strain + Medium + conditions (temp, pH, days).
- Result:    measured outputs (biomass_g_per_l, beta_glucan_pct, etc.).
"""

# TODO: create SQLAlchemy 2.0 DeclarativeBase and engine factory (SQLite under data/).
# TODO: define Paper, Strain, Medium, Experiment, Result models with FKs.
# TODO: add indexes on (strain_id, carbon_source, nitrogen_source).
# TODO: provide init_db() to create tables and get_session() context manager.
