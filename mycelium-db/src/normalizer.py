"""Unit normalization and derived-value computation.

Converts heterogeneous units reported across papers into a canonical form
(e.g. biomass -> g/L, temperature -> °C, concentrations -> g/L) and computes
derived quantities such as the C/N ratio of the medium.
"""

# TODO: implement to_g_per_l(value, unit) supporting mg/mL, g/L, %, w/v.
# TODO: implement to_celsius(value, unit) supporting °C, °F, K.
# TODO: implement cn_ratio(carbon_source, c_conc_g_l, nitrogen_source, n_conc_g_l)
#       using a small lookup table of %C and %N for common substrates
#       (glucose, sucrose, yeast extract, peptone, urea, NH4NO3, ...).
# TODO: expose normalize_record(dict) -> dict that applies all conversions in one pass.
