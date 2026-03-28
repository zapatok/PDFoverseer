# Plan: OCR Preprocessing Sweep v2

**Spec:** `docs/superpowers/specs/2026-03-27-ocr-preprocess-v2-design.md`
**Branch:** cuda-gpu
**Scope:** eval/ only

---

## Step 1 — Correct OCR_PRODUCTION_PARAMS baseline

**File:** `eval/ocr_params.py`

**Instructions:**
1. Read `eval/ocr_params.py`
2. Change `OCR_PRODUCTION_PARAMS`:
   - `"skip_binarization": False` → `True`
   - `"unsharp_sigma": 0.0` → `1.0`
   - `"unsharp_strength": 0.0` → `0.3`
3. Add a new dict `OCR_PREPROCESS_V2_SPACE` after `OCR_TIER1_PARAMS`:
   ```python
   OCR_PREPROCESS_V2_SPACE: dict[str, list] = {
       "color_separation": ["hsv_inpaint", "red_channel"],
       "clahe_clip":       [0.0, 2.0, 3.0],
       "morph_dilate":     [0, 2, 3],
   }
   ```
4. Do NOT modify `OCR_PARAM_SPACE` or `OCR_TESS_PARAM_SPACE` — the new params are separate

**Verification:** `ruff check eval/ocr_params.py` → 0 violations

---

## Step 2 — Add 3 preprocessing steps to eval/ocr_preprocess.py

**File:** `eval/ocr_preprocess.py`

**Instructions:**

Read the file first. The current pipeline in `preprocess()` is:
```
1. deskew → 2. blue_inpaint → 3. grayscale → 4. unsharp → 5. border → 6. binarization → 7. tess_config
```

Make these changes:

### 2a. Replace step 2 (blue ink removal) with color_separation logic

The current step 2 block checks `params.get("blue_inpaint", True)`. Replace it with:

```python
# 2. Color separation (blue ink removal)
color_sep = params.get("color_separation", "hsv_inpaint")
if color_sep == "red_channel":
    # Red channel extraction: blue ink (R~30-80) fades, black text (R~0-40) preserved
    if img.ndim == 3 and img.shape[2] >= 3:
        img = img[:, :, 2]  # BGR → R channel (already grayscale)
elif params.get("blue_inpaint", True):
    # Existing: HSV mask + Navier-Stokes inpainting
    if img.ndim == 3 and img.shape[2] >= 3:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask_blue = cv2.inRange(hsv, _LOWER_BLUE, _UPPER_BLUE)
        img = cv2.inpaint(img, mask_blue, 3, cv2.INPAINT_NS)
```

**Important:** The existing grayscale step (step 3) already handles `img.ndim == 2` — if red_channel was used, it will detect the 2D array and skip conversion. No changes needed in step 3.

### 2b. Add CLAHE step between grayscale (step 3) and unsharp (step 4)

Insert after the grayscale block, before the unsharp block:

```python
# 3b. CLAHE (adaptive contrast equalization)
clahe_clip = params.get("clahe_clip", 0.0)
if clahe_clip > 0:
    clahe_obj = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(4, 4))
    gray = clahe_obj.apply(gray)
```

### 2c. Add morphological dilation after binarization (step 6), before tess_config (step 7)

Insert after the binarization block, before the tess_config block:

```python
# 6b. Morphological dilation (thicken thin character strokes)
morph_k = params.get("morph_dilate", 0)
if morph_k > 0:
    kernel = np.ones((morph_k, morph_k), np.uint8)
    gray = cv2.bitwise_not(gray)
    gray = cv2.dilate(gray, kernel, iterations=1)
    gray = cv2.bitwise_not(gray)
```

**Verification:** `ruff check eval/ocr_preprocess.py` → 0 violations

---

## Step 3 — Add --preprocess mode to eval/ocr_sweep.py

**File:** `eval/ocr_sweep.py`

**Instructions:**

Read the file first. You need to add:

### 3a. Import the new param space

Add to imports at top:
```python
from eval.ocr_params import (
    ...existing imports...,
    OCR_PREPROCESS_V2_SPACE,
)
```

### 3b. Add the `run_preprocess_sweep()` function

Add before `main()`. This function runs 4 phases sequentially. Here's the logic:

```python
def run_preprocess_sweep() -> dict:
    """4-phase incremental preprocessing sweep.
    Phase 1-3: one technique each (isolated).
    Phase 4: combo of winners."""
    failed, success = load_pages_tier1()
    rng = random.Random(42)
    success_sample_size = min(200, len(success))
    success_sample = rng.sample(success, success_sample_size)

    # Corrected production baseline
    baseline_params = dict(OCR_TIER1_PARAMS)

    print(f"[preprocess_v2] {len(failed)} failed + {len(success)} success pages")
    print(f"Baseline: {baseline_params}\n")

    phases = {}

    # --- Helper: run one phase ---
    def _run_phase(name: str, param_key: str, values: list) -> dict:
        """Score each value against failed+success pages, return phase result."""
        configs = []
        for val in values:
            label = str(val)
            cfg = {**baseline_params, param_key: val}
            print(f"  [{name}] scoring {label}...")
            sc_a = score_on_pages(cfg, failed)
            sc_b = score_on_pages(cfg, success_sample)
            net = sc_a["rescued"] - sc_b["regressed"] * 3
            entry = {
                "label": label,
                "params": cfg,
                "phase_a": {k: v for k, v in sc_a.items() if k != "rescued_pages"},
                "phase_b": {k: v for k, v in sc_b.items() if k != "rescued_pages"},
                "net_gain": net,
                "rescued_pages": sc_a["rescued_pages"],
            }
            configs.append(entry)
            print(f"    rescued={sc_a['rescued']}, regressed={sc_b['regressed']}, "
                  f"net_gain={net}")

        configs.sort(key=lambda x: -x["net_gain"])
        winner = configs[0] if configs else None
        return {"configs": configs, "winner": {
            "label": winner["label"],
            "value": values[configs.index(winner)] if winner else None,
            "net_gain": winner["net_gain"],
        } if winner else None}

    # Phase 1: Red channel
    print("Phase 1: Red Channel")
    phases["red_channel"] = _run_phase(
        "red_channel", "color_separation",
        OCR_PREPROCESS_V2_SPACE["color_separation"],
    )

    # Phase 2: CLAHE
    print("\nPhase 2: CLAHE")
    phases["clahe"] = _run_phase(
        "clahe", "clahe_clip",
        OCR_PREPROCESS_V2_SPACE["clahe_clip"],
    )

    # Phase 3: Dilation
    print("\nPhase 3: Dilation")
    phases["dilate"] = _run_phase(
        "dilate", "morph_dilate",
        OCR_PREPROCESS_V2_SPACE["morph_dilate"],
    )

    # Phase 4: Combo of winners (only techniques with net_gain > 0)
    print("\nPhase 4: Combo")
    combo_params = {}
    for phase_name, param_key in [
        ("red_channel", "color_separation"),
        ("clahe", "clahe_clip"),
        ("dilate", "morph_dilate"),
    ]:
        w = phases[phase_name]["winner"]
        if w and w["net_gain"] > 0:
            combo_params[param_key] = w["value"]

    if not combo_params:
        print("  No winning techniques — skipping combo phase")
        phases["combo"] = {"configs": [], "winner": None, "skipped": True}
    elif len(combo_params) == 1:
        print("  Only 1 winning technique — combo identical to single phase, skipping")
        phases["combo"] = {"configs": [], "winner": None, "skipped": True}
    else:
        # Cartesian product of all winning values
        from itertools import product as iterproduct
        combo_keys = list(combo_params.keys())
        # For combo, also test each winner's "off" value to check interactions
        combo_values = []
        off_values = {"color_separation": "hsv_inpaint", "clahe_clip": 0.0, "morph_dilate": 0}
        for k in combo_keys:
            combo_values.append([off_values[k], combo_params[k]])

        combo_configs = []
        for combo in iterproduct(*combo_values):
            overrides = dict(zip(combo_keys, combo))
            # Skip the all-off config (that's baseline)
            if all(overrides[k] == off_values[k] for k in combo_keys):
                continue
            cfg = {**baseline_params, **overrides}
            label = "+".join(f"{k}={v}" for k, v in overrides.items()
                            if v != off_values[k])
            if not label:
                label = "baseline"

            print(f"  [combo] scoring {label}...")
            sc_a = score_on_pages(cfg, failed)
            sc_b = score_on_pages(cfg, success_sample)
            net = sc_a["rescued"] - sc_b["regressed"] * 3
            entry = {
                "label": label,
                "params": cfg,
                "phase_a": {k: v for k, v in sc_a.items() if k != "rescued_pages"},
                "phase_b": {k: v for k, v in sc_b.items() if k != "rescued_pages"},
                "net_gain": net,
                "rescued_pages": sc_a["rescued_pages"],
            }
            combo_configs.append(entry)
            print(f"    rescued={sc_a['rescued']}, regressed={sc_b['regressed']}, "
                  f"net_gain={net}")

        combo_configs.sort(key=lambda x: -x["net_gain"])
        combo_winner = combo_configs[0] if combo_configs else None
        phases["combo"] = {
            "configs": combo_configs,
            "winner": {
                "label": combo_winner["label"],
                "net_gain": combo_winner["net_gain"],
            } if combo_winner else None,
        }

    return {
        "run_at": datetime.now().isoformat(),
        "mode": "preprocess_v2",
        "baseline_params": baseline_params,
        "total_failed_pages": len(failed),
        "total_success_pages": len(success),
        "success_sample_size": success_sample_size,
        "phases": phases,
    }
```

### 3c. Wire up in main()

Add `--preprocess` flag parsing and dispatch in `main()`:

```python
preprocess_mode = "--preprocess" in sys.argv
```

Add before the existing mode checks:
```python
if preprocess_mode:
    result = run_preprocess_sweep()
    tag = "ocr_preprocess_v2"
```

### 3d. Add `itertools.product` alias note

The combo phase uses `from itertools import product as iterproduct` locally to avoid shadowing the existing module-level `from itertools import product`. Alternatively, rename the module-level import. Use whichever avoids lint issues — the local import inside the function is fine since it's a stdlib import.

**Verification:** `ruff check eval/ocr_sweep.py` → 0 violations

---

## Step 4 — Verify with ruff

**Instructions:**
1. Run `ruff check eval/ocr_params.py eval/ocr_preprocess.py eval/ocr_sweep.py`
2. Fix any violations
3. Do NOT run the sweep yet — just verify lint passes

---

## Step 5 — Dry run sanity check

**Instructions:**
1. Run a quick Python import check:
   ```bash
   python -c "from eval.ocr_params import OCR_PRODUCTION_PARAMS, OCR_PREPROCESS_V2_SPACE; print('params ok')"
   python -c "from eval.ocr_preprocess import preprocess; print('preprocess ok')"
   python -c "from eval.ocr_sweep import run_preprocess_sweep; print('sweep ok')"
   ```
2. Verify no import errors
3. Do NOT run the actual sweep — that's the user's decision

---

## Checklist before done

- [ ] `OCR_PRODUCTION_PARAMS` reflects actual production (skip_bin=True, unsharp=1.0/0.3)
- [ ] `OCR_PREPROCESS_V2_SPACE` added as separate dict
- [ ] `preprocess()` handles `color_separation`, `clahe_clip`, `morph_dilate`
- [ ] Red channel path produces ndim==2 (grayscale step skips correctly)
- [ ] CLAHE between grayscale and unsharp
- [ ] Dilate after binarization, uses invert-dilate-invert pattern
- [ ] `--preprocess` mode wired in main()
- [ ] `ruff check` passes on all 3 files
- [ ] Import sanity check passes
- [ ] No changes to core/, api/, or any production code
