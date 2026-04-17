# mycelium-db

A database app for **mushroom mycelium cultivation conditions**.

The goal is to collect, normalize, and compare published cultivation
experiments so you can answer questions like:

- Which **carbon source** (glucose, sucrose, molasses, …) produces the
  highest mycelial **biomass** for *Hericium erinaceus*?
- How does **β-glucan** content vary with **nitrogen source** (yeast
  extract, peptone, urea, NH₄NO₃, …) and **C/N ratio**?
- Which temperature / pH / incubation-time windows tend to co-occur
  with top-quartile yields?

## Pipeline

1. **fetcher.py** — query PubMed/PMC via NCBI Entrez and pull abstracts
   or open-access full-texts.
2. **extractor.py** — use the Claude API to pull structured rows
   (strain, medium, conditions, results) out of each paper.
3. **normalizer.py** — unify units (g/L, °C, …) and compute derived
   values such as C/N ratio.
4. **schema.py** — persist everything in a SQLAlchemy-backed SQLite DB.
5. **app.py** — explore and compare via a Streamlit UI with Plotly
   charts.

## Requirements

- Python **3.11+**
- [`uv`](https://docs.astral.sh/uv/) for dependency / venv management
- An **NCBI API key** (optional but recommended) and an **Anthropic API
  key**

## Installation

```bash
cd mycelium-db
uv sync
cp .env.example .env
# edit .env and fill in NCBI_EMAIL, NCBI_API_KEY, ANTHROPIC_API_KEY
```

## Running

Launch the Streamlit app:

```bash
uv run streamlit run src/app.py
```

Run tests:

```bash
uv run pytest
```

## Project layout

```
mycelium-db/
├── src/
│   ├── fetcher.py      # NCBI Entrez API wrapper
│   ├── extractor.py    # Claude API → structured extraction from papers
│   ├── schema.py       # SQLAlchemy models
│   ├── normalizer.py   # unit conversion, C/N ratio
│   └── app.py          # Streamlit UI
├── data/               # SQLite DB and fetch cache (gitignored)
├── tests/
├── .env.example
├── pyproject.toml
└── README.md
```

## Status

Scaffolding only — each module currently contains a docstring and
`TODO` markers describing what it will do. No business logic is
implemented yet.
