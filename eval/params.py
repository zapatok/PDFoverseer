# eval/params.py
"""
Parameter search space for the inference engine sweep.
Each key maps to a list of discrete candidate values.
PRODUCTION_PARAMS mirrors the hardcoded constants in core/analyzer.py.
"""

PARAM_SPACE: dict[str, list] = {
    # Phase 1 — Forward propagation
    "fwd_conf":         [0.95, 0.97, 0.99],
    "new_doc_base":     [0.55, 0.60, 0.65],
    "new_doc_hom_mul":  [0.25, 0.30, 0.35],
    # Phase 2 — Backward propagation
    "back_conf":        [0.88, 0.90, 0.93],
    # Phase 3 — Cross-validation
    "xval_cap":         [0.35, 0.40, 0.45],
    # Phase 4 — Fallback
    "fallback_base":     [0.35, 0.40, 0.45],
    "fallback_hom_base": [0.25, 0.30, 0.35],
    "fallback_hom_mul":  [0.12, 0.15, 0.18],
    # Phase 5 — D-S post-validation (with period evidence)
    "ds_period_weight":   [0.08, 0.10, 0.12],
    "ds_neighbor_weight": [0.08, 0.10, 0.12],
    "ds_prior_weight":    [0.03, 0.05, 0.07],
    "ds_boost_max":       [0.18, 0.20, 0.23],
    # Phase 5b — Period-contradiction correction
    # 0.0 = disabled (baseline). >0 = min period confidence to activate.
    # Sweet spot: 0.69 catches INS_31 (conf=0.698) but not ART (conf=0.685).
    "ph5b_conf_min":      [0.0, 0.50, 0.60, 0.69, 0.70],
    "ph5b_ratio_min":     [0.90, 0.93, 0.95],
    # Phase 6 — Orphan suppression
    # Inferred new-doc triggers (curr==1) below this confidence are excluded.
    # 0.0 = no suppression (baseline behavior).
    # xval_cap (Ph3) caps inconsistent orphans to ≤0.60, so values in
    # [0.45, 0.65] are the discriminating range.
    "min_conf_for_new_doc": [0.0, 0.45, 0.55, 0.65],
    # Global
    "window":           [3, 5, 7],
    "hom_threshold":    [0.83, 0.85, 0.88],
}

# Current production values (hardcoded constants in analyzer.py)
PRODUCTION_PARAMS: dict[str, float | int] = {
    "fwd_conf":         0.95,
    "new_doc_base":     0.60,
    "new_doc_hom_mul":  0.30,
    "back_conf":        0.90,
    "xval_cap":         0.50,
    "fallback_base":    0.40,
    "fallback_hom_base":0.30,
    "fallback_hom_mul": 0.20,
    "ds_period_weight":   0.15,
    "ds_neighbor_weight": 0.08,
    "ds_prior_weight":    0.05,
    "ds_boost_max":       0.25,
    "ph5b_conf_min":      0.0,   # disabled — matches core (no Phase 5b)
    "ph5b_ratio_min":     0.85,
    "min_conf_for_new_doc": 0.0,
    "window":           5,
    "hom_threshold":    0.85,
}
