"""Structured-data extractor powered by the Claude API.

Takes raw paper text (abstract or full-text) and extracts structured
cultivation experiment records: species, carbon source, nitrogen source,
C/N ratio, temperature, pH, biomass yield, β-glucan content, etc.
"""

# TODO: load ANTHROPIC_API_KEY from environment (python-dotenv).
# TODO: define an extraction JSON schema (strain, carbon_source, nitrogen_source,
#       concentrations, temperature_c, ph, incubation_days, biomass_g_per_l,
#       beta_glucan_pct, source_pmid).
# TODO: implement extract_from_text(text: str) -> list[dict] using the Anthropic
#       client with tool-use / structured output and prompt caching on the system prompt.
# TODO: validate extractions against the schema; drop or flag low-confidence rows.
# TODO: batch long full-texts into chunks, then deduplicate across chunks.
