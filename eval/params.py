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
    "ph5b_conf_min":      [0.0, 0.40, 0.50, 0.60, 0.69, 0.70],
    "ph5b_ratio_min":     [0.90, 0.93, 0.95],
    "ph5_guard_conf":     [0.0, 0.70, 0.80, 0.90],
    "recon_weight":       [0.0, 0.15, 0.20, 0.25, 0.30],   # Approach A
    "ph5_guard_slope":    [0.0, 0.5, 1.0, 1.5, 2.0],        # Approach B
    # Period-Consistency Filter (PCF) — corrects inferred reads with wrong totals
    # 0.0 = disabled. Higher = more aggressive (corrects higher-confidence reads).
    "pcf_conf_max":        [0.0, 0.40, 0.50, 0.60],
    "pcf_period_conf_min": [0.40, 0.50, 0.60],  # min period confidence to activate
    # Period-Aware Doc Merge (PDM) — merges consecutive small docs summing to period
    "pdm_enable":          [0.0, 1.0],        # 0.0 = disabled, 1.0 = enabled
    "pdm_period_conf_min": [0.40, 0.50, 0.60],  # min period confidence to activate
    # Phase MP — Multi-period local correction
    # Uses sliding-window local period to correct direct OCR reads that
    # contradict their neighborhood.  0 = disabled (global Phase 5b only).
    "mp_window":    [0, 60, 80, 100],     # full window size (pages on each side = half)
    "mp_ratio_min": [0.55, 0.65, 0.69, 0.75],  # local agreement ratio to trigger correction
    "mp_min_run":   [3, 5, 8],            # min consecutive total=1 direct reads to correct
    # Phase D — Viterbi anchor-constrained segment fill
    "viterbi_anchor_conf_min": [0.80, 0.85, 0.90, 0.95],   # min conf for hard anchor
    "viterbi_period_weight":   [0.2, 0.3, 0.5, 0.7, 0.8],  # weight of period alignment bonus
    "viterbi_prior_weight":    [0.2, 0.4, 0.6],             # weight of prior(total) (reserved)
    # Phase 6 — Orphan suppression
    # Inferred new-doc triggers (curr==1) below this confidence are excluded.
    # 0.0 = no suppression (baseline behavior).
    # xval_cap (Ph3) caps inconsistent orphans to ≤0.60, so values in
    # [0.45, 0.65] are the discriminating range.
    "min_conf_for_new_doc": [0.0],
    # Global
    "window":           [3, 5, 7],
    "hom_threshold":    [0.83, 0.85, 0.88],
}

# Current production values (hardcoded constants in analyzer.py)
PRODUCTION_PARAMS: dict[str, float | int] = {
    "fwd_conf":         0.99,
    "new_doc_base":     0.60,
    "new_doc_hom_mul":  0.35,
    "back_conf":        0.93,
    "xval_cap":         0.35,
    "fallback_base":    0.45,  # Phase D sweep: increased from 0.40
    "fallback_hom_base":0.30,
    "fallback_hom_mul": 0.12,
    "ds_period_weight":   0.10,
    "ds_neighbor_weight": 0.10,
    "ds_prior_weight":    0.05,
    "ds_boost_max":       0.23,
    "ph5b_conf_min":      0.69,
    "ph5b_ratio_min":     0.93,
    "ph5_guard_conf":     0.90,
    "recon_weight":       0.0,   # Approach A: no improvement over baseline
    "ph5_guard_slope":    1.0,   # Approach B: sweep winner, improves undercount recovery
    "pcf_conf_max":        0.0,   # PCF: disabled by default (0.0 = off)
    "pcf_period_conf_min": 0.50,  # PCF: min period confidence to activate
    "pdm_enable":          1.0,   # PDM: enabled (aggressive sweep winner), was 0.0
    "pdm_period_conf_min": 0.40,  # PDM: min period confidence to activate (sweep winner)
    "mp_window":    80,    # Phase MP: sweep winner (aggressive), was 0
    "mp_ratio_min": 0.69,  # Phase MP: local agreement ratio threshold
    "mp_min_run":   5,     # Phase MP: min run length of total=1 direct reads
    "viterbi_anchor_conf_min": 0.90,  # Phase D: confidence threshold for hard anchors
    "viterbi_period_weight":   0.5,   # Phase D: weight of period-alignment confidence boost
    "viterbi_prior_weight":    0.4,   # Phase D: weight of prior(total) (reserved)
    "min_conf_for_new_doc": 0.0,
    "window":           7,
    "hom_threshold":    0.83,  # Phase D sweep: decreased from 0.88
}
