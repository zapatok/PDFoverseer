# eval/params.py
"""
Parameter search space for the inference engine sweep.
Each key maps to a list of discrete candidate values.
PRODUCTION_PARAMS mirrors the hardcoded constants in core/utils.py.

Sweep2: refined grid around soft-alignment-v3-sweep1 winners.
"""

PARAM_SPACE: dict[str, list] = {
    # Phase 1 — Forward propagation
    "fwd_conf":         [0.97, 0.99, 1.00],
    "new_doc_base":     [0.60, 0.65, 0.68, 0.70],
    "new_doc_hom_mul":  [0.25, 0.28, 0.30, 0.33],
    # Phase 2 — Backward propagation
    "back_conf":        [0.85, 0.88, 0.90],
    # Phase 3 — Cross-validation
    "xval_cap":         [0.40, 0.43, 0.45, 0.48, 0.50],
    # Phase 5 — D-S post-validation
    "ds_period_weight":   [0.10, 0.12, 0.14],
    "ds_neighbor_weight": [0.08, 0.10, 0.12],
    "ds_prior_weight":    [0.05, 0.07, 0.09],
    "ds_boost_max":       [0.18, 0.20, 0.22],
    # Phase 5b — Period-contradiction correction
    "ph5b_conf_min":      [0.50, 0.55, 0.60, 0.65],
    "ph5b_ratio_min":     [0.90, 0.93, 0.95],
    # Phase 6 — Orphan suppression
    "min_conf_for_new_doc": [0.55, 0.60, 0.65, 0.70],
    "anomaly_dropout":      [0.0, 0.10, 0.20, 0.30],
    # Gap solver
    "clash_w_local":    [0.75, 1.0, 1.5, 2.0],
    "clash_w_period":   [1.5, 2.0, 2.5, 3.0],
    "phase4_conf":       [0.0, 0.10, 0.15],
    "clash_boundary_pen":      [1.0, 1.5, 2.0, 3.0],
    "failure_zone_cbpen_scale": [1.0, 1.5, 2.0, 3.0],
    "failure_zone_min_len":    [5, 10, 20, 50],
    # Global
    "window":           [5, 7, 9],
    "hom_threshold":    [0.80, 0.83, 0.85],
    # Pre-inference dedup
    "min_boundary_gap": [1, 2],
}

# Current production values — sweep4 (2026-03-27, 42 fixtures incl. syn_failure_zone, syn_misread_singleton)
PRODUCTION_PARAMS: dict[str, float | int] = {
    "fwd_conf":         1.0,
    "new_doc_base":     0.60,
    "new_doc_hom_mul":  0.28,
    "back_conf":        0.85,
    "xval_cap":         0.40,
    "ds_period_weight":   0.10,
    "ds_neighbor_weight": 0.08,
    "ds_prior_weight":    0.05,
    "ds_boost_max":       0.18,
    "ph5b_conf_min":      0.65,
    "ph5b_ratio_min":     0.90,
    "min_conf_for_new_doc": 0.55,
    "anomaly_dropout":    0.10,
    "clash_w_local":      1.5,
    "clash_w_period":     3.0,
    "phase4_conf":        0.10,
    "clash_boundary_pen":      1.0,
    "failure_zone_cbpen_scale": 3.0,
    "failure_zone_min_len":    10,
    "window":           9,
    "hom_threshold":    0.80,
    "min_boundary_gap": 2,
}
