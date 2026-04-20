# Extractor Output Schema

This document specifies the JSON schema for `extractor.py` output.
Each PubMed paper (identified by PMID) produces exactly one JSON object.

## Design Principles

1. **Paper → study metadata → experiments (list) → outcomes (list)**: Preserves
   multi-condition experimental structure for cross-paper comparison.

2. **Value + unit + normalized_value**: Raw values are never discarded.
   Normalization produces a canonical unit for direct comparison.

3. **β-glucan as a dedicated structured field**: This project's central target.
   Separate from generic `outcomes` to support:
   - total vs (1→3) vs (1→6) reporting
   - Unit diversity normalization (mg/g, %, g/L)
   - Lentinan vs generic β-glucan distinction

4. **`null` is a first-class value**: Missing information is preserved as
   `null`, never fabricated. The extractor must not invent data not in source.

5. **`extraction_status` and `relevance_score`**: Every record includes an
   explicit verdict on whether extraction succeeded and whether the paper
   is relevant to the project's focus (cultivation condition optimization).

---

## Top-Level Schema
{
"pmid": str,                          // Copied from fetcher
"extraction_status": enum,            // success | partial | failed | not_relevant
"relevance_score": float,             // 0.0 to 1.0
"relevance_reason": str,              // One-sentence justification
"study_metadata": { ... },            // Study-level info
"experiments": [ { ... } ],           // List of experimental conditions
"analysis_notes": { ... },            // Methods and notes
"source": { ... }                     // Traceability metadata
}

### `extraction_status` values
- `success`: Full extraction with ≥1 experiment having conditions + outcomes.
- `partial`: Some fields extracted but key data missing (e.g., conditions but
  no outcomes, or vice versa).
- `failed`: Extraction failed entirely (parsing error, refused, etc.).
  `experiments` will be empty.
- `not_relevant`: Paper is off-topic (relevance_score < 0.3). Minimal metadata
  extracted; no experiments processed.

### `relevance_score` thresholds
- `>= 0.8`: Core study — cultivation conditions + biomass/β-glucan measurement.
- `0.5–0.8`: Related — mentions conditions but primary focus elsewhere.
- `0.3–0.5`: Marginal — passing mentions only.
- `< 0.3`: Off-topic (set status to `not_relevant`, skip experiment extraction).

---

## `study_metadata`
{
"strain": str | null,
"strain_notes": str | null,
"culture_mode": enum | null,
"optimization_method": enum | null,
"reactor_scale": enum | null,
"reactor_volume_ml": float | null
}

### Controlled vocabularies

**`culture_mode`**:
- `submerged_liquid`
- `solid_state`
- `plate_agar`
- `log_synthetic`
- `other`

**`optimization_method`**:
- `RSM_Box-Behnken`
- `RSM_central_composite`
- `Plackett-Burman`
- `Taguchi`
- `OFAT`
- `none`
- `other`

**`reactor_scale`**:
- `test_tube`
- `shake_flask`
- `stirred_tank`
- `airlift_bioreactor`
- `petri_dish`
- `other`

---

## `experiments` (list)

Each experiment represents ONE distinct condition set. A paper comparing
glucose / sucrose / starch as carbon sources produces 3 experiments.
{
"experiment_id": str,
"description": str,
"conditions": { ... },
"outcomes": [ { ... } ],
"beta_glucan": { ... }
}

### `conditions`

All fields `null` if not reported.
{
"carbon_source": str | null,
"carbon_concentration_g_L": float | null,
"nitrogen_source": str | null,
"nitrogen_concentration_g_L": float | null,
"cn_ratio": float | null,
"initial_pH": float | null,
"temperature_C": float | null,
"agitation_rpm": float | null,
"duration_days": float | null,
"inoculum_percent": float | null
}

**Normalization rules**:
- Concentrations: convert to g/L. `mg/mL` = g/L. `% (w/v)` × 10 = g/L.
- Temperature: Celsius only.
- Duration: days.

### `outcomes` (list)

General measurements other than β-glucan.
{
"metric": str,
"value": float,
"unit": str,
"value_g_L": float | null,
"metric_type": enum
}

**`metric_type`**:
- `mycelial_dry_weight`
- `mycelial_wet_weight`
- `exopolysaccharide`
- `intracellular_polysaccharide`
- `total_polysaccharide`
- `protein_content`
- `reducing_sugar_residual`
- `ergothioneine`
- `other`

### `beta_glucan` (dedicated field)
{
"reported": bool,
"total_value": float | null,
"total_unit": str | null,
"total_value_pct_dw": float | null,
"beta_1_3_value": float | null,
"beta_1_3_unit": str | null,
"beta_1_6_value": float | null,
"beta_1_6_unit": str | null,
"ratio_1_3_to_1_6": float | null,
"molecular_weight_kDa": float | null,
"is_lentinan_specific": bool,
"notes": str | null
}

**Normalization rules for `total_value_pct_dw`**:
- `mg/g DW` × 0.1 = `% DW`
- `% DW` unchanged
- `g/100g` = `% DW`
- `mg/L` CANNOT be converted without biomass. Leave `null`, note in `notes`.

**`is_lentinan_specific`**:
- `true` if paper explicitly names "lentinan" AND provides structural evidence
  (β-(1→3) main chain, β-(1→6) branches).
- `false` for generic "β-glucan" or "polysaccharide".

---

## `analysis_notes`
{
"beta_glucan_analysis_method": enum | null,
"statistical_design": str | null
}

**`beta_glucan_analysis_method`**:
- `Megazyme_kit`
- `phenol_sulfuric_acid`
- `Congo_red`
- `NMR`
- `HPLC`
- `enzymatic_other`
- `other`
- `not_specified`

---

## `source`
{
"section_used": list[str],
"extractor_model": str,
"extracted_at": str,
"warnings": list[str]
}

---

## Complete Example

```json
{
  "pmid": "25868404",
  "extraction_status": "success",
  "relevance_score": 0.92,
  "relevance_reason": "RSM study optimizing submerged culture for biomass and polysaccharide production",

  "study_metadata": {
    "strain": "LeS (NCBI JX915793)",
    "strain_notes": "Strain deposited at NCBI accession JX915793",
    "culture_mode": "submerged_liquid",
    "optimization_method": "RSM_Box-Behnken",
    "reactor_scale": "shake_flask",
    "reactor_volume_ml": 250
  },

  "experiments": [
    {
      "experiment_id": "exp_1",
      "description": "RSM-optimized condition",
      "conditions": {
        "carbon_source": "glucose",
        "carbon_concentration_g_L": 20,
        "nitrogen_source": "yeast extract",
        "nitrogen_concentration_g_L": 5,
        "cn_ratio": 15.4,
        "initial_pH": 5.0,
        "temperature_C": 26,
        "agitation_rpm": 52,
        "duration_days": 25,
        "inoculum_percent": 5
      },
      "outcomes": [
        {
          "metric": "biomass",
          "value": 5.88,
          "unit": "mg/mL",
          "value_g_L": 5.88,
          "metric_type": "mycelial_dry_weight"
        },
        {
          "metric": "EPS",
          "value": 0.40,
          "unit": "mg/mL",
          "value_g_L": 0.40,
          "metric_type": "exopolysaccharide"
        },
        {
          "metric": "IPS",
          "value": 12.45,
          "unit": "mg/g",
          "value_g_L": null,
          "metric_type": "intracellular_polysaccharide"
        }
      ],
      "beta_glucan": {
        "reported": false,
        "total_value": null,
        "total_unit": null,
        "total_value_pct_dw": null,
        "beta_1_3_value": null,
        "beta_1_3_unit": null,
        "beta_1_6_value": null,
        "beta_1_6_unit": null,
        "ratio_1_3_to_1_6": null,
        "molecular_weight_kDa": null,
        "is_lentinan_specific": false,
        "notes": "Paper measured total polysaccharide (IPS), not β-glucan specifically"
      }
    }
  ],

  "analysis_notes": {
    "beta_glucan_analysis_method": "phenol_sulfuric_acid",
    "statistical_design": "Box-Behnken design, 3 factors"
  },

  "source": {
    "section_used": ["abstract", "results", "table_2"],
    "extractor_model": "claude-opus-4-7",
    "extracted_at": "2026-04-18T10:00:00Z",
    "warnings": []
  }
}
```

---

## Validation Rules (post-extraction)

1. `extraction_status` is valid enum.
2. `relevance_score` in [0.0, 1.0].
3. If `status == "success"`, require ≥1 experiment with conditions AND outcomes.
4. If `status == "not_relevant"`, `experiments` must be empty.
5. `conditions.carbon_concentration_g_L` positive if non-null.
6. `beta_glucan.total_value_pct_dw` in [0, 100] if non-null.
7. `source.extracted_at` ISO 8601 parseable.

Validation failures do NOT block saving — recorded in `source.warnings`.