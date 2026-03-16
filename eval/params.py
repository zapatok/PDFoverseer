# eval/params.py
"""
Parameter search space for the inference engine sweep.
Each key maps to a list of discrete candidate values.
PRODUCTION_PARAMS mirrors the hardcoded constants in core/analyzer.py.
"""

PARAM_SPACE: dict[str, list] = {
    # Phase 1 — Forward propagation
    "fwd_conf":         [0.90, 0.93, 0.95, 0.97],
    "new_doc_base":     [0.50, 0.60, 0.70],
    "new_doc_hom_mul":  [0.20, 0.30, 0.40],
    # Phase 2 — Backward propagation
    "back_conf":        [0.85, 0.90, 0.95],
    # Phase 3 — Cross-validation
    "xval_cap":         [0.40, 0.50, 0.60],
    # Phase 4 — Fallback
    "fallback_base":     [0.30, 0.40, 0.50],
    "fallback_hom_base": [0.20, 0.30, 0.40],
    "fallback_hom_mul":  [0.15, 0.20, 0.25],
    # Phase 5 — D-S post-validation (period evidence not ported; support=0 always)
    "ds_boost_max":     [0.20, 0.25, 0.30],
    # Phase 6 — Orphan suppression
    # Inferred new-doc triggers (curr==1) below this confidence are excluded.
    # 0.0 = no suppression (baseline behavior).
    # xval_cap (Ph3) caps inconsistent orphans to ≤0.60, so values in
    # [0.45, 0.65] are the discriminating range.
    "min_conf_for_new_doc": [0.0, 0.45, 0.55, 0.65, 0.75],
    # Global
    "window":           [3, 5, 7],
    "hom_threshold":    [0.80, 0.85, 0.90],
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
    "ds_boost_max":     0.25,
    "min_conf_for_new_doc": 0.0,
    "window":           5,
    "hom_threshold":    0.85,
}
