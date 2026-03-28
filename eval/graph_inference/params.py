# eval/graph_params.py
"""
Parameter search space for the graph inference engine (HMM + Viterbi).
Each key maps to a list of discrete candidate values.
GRAPH_DEFAULT_PARAMS are reasonable starting defaults (not yet sweep-tuned).
"""

GRAPH_PARAM_SPACE: dict[str, list] = {
    # Transition model
    "trans_continue":   [0.70, 0.80, 0.85, 0.90, 0.95],
    "trans_new_doc":    [0.05, 0.10, 0.15, 0.20, 0.30],
    "trans_skip":       [0.01, 0.03, 0.05, 0.10],
    # Emission model
    "emit_match":       [0.60, 0.70, 0.80, 0.90, 0.95],
    "emit_conf_scale":  [0.5, 1.0, 1.5, 2.0],
    "emit_partial":     [0.05, 0.10, 0.15, 0.20],
    "emit_null":        [0.1, 0.2, 0.3, 0.5],
    # State space
    "max_total":        [15, 20, 25, 30],
    # Boundary
    "boundary_bonus":   [1.0, 2.0, 3.0, 5.0],
    # Period prior
    "period_prior":     [0.0, 0.1, 0.2, 0.3, 0.5],
}

# Reasonable defaults (not yet tuned)
GRAPH_DEFAULT_PARAMS: dict[str, float | int] = {
    "trans_continue":   0.85,
    "trans_new_doc":    0.10,
    "trans_skip":       0.03,
    "emit_match":       0.90,
    "emit_conf_scale":  1.0,
    "emit_partial":     0.10,
    "emit_null":        0.3,
    "max_total":        20,
    "boundary_bonus":   2.0,
    "period_prior":     0.0,
}
