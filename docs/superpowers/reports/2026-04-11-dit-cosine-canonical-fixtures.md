# DiT + Cosine benchmark - canonical project fixtures

Generated: 2026-04-11T19:21:40

_rio_bueno baseline: rescue_c -> 4/13 exact, MAE 9.5. Canonical fixtures use F1 instead of count-MAE so the bucket criteria below are reinterpreted._

## Fixtures included

21 fixtures with both JSON ground truth and a PDF in `data/samples/`:

- **ALUM_1** (ALUM) - 2 labeled pages, 1 expected covers, PDF: `ALUM_1.pdf`
- **ALUM_19** (ALUM) - 36 labeled pages, 19 expected covers, PDF: `ALUM_19.pdf`
- **ART_674** (ART) - 2686 labeled pages, 674 expected covers, PDF: `ART_674.pdf`
- **CASTRO_15** (CASTRO) - 15 labeled pages, 15 expected covers, PDF: `CASTRO_15.pdf`
- **CASTRO_5** (CASTRO) - 5 labeled pages, 5 expected covers, PDF: `CASTRO_5.pdf`
- **CH_39** (CH) - 77 labeled pages, 39 expected covers, PDF: `CH_39.pdf`
- **CH_51** (CH) - 101 labeled pages, 51 expected covers, PDF: `CH_51docs.pdf`
- **CH_74** (CH) - 148 labeled pages, 74 expected covers, PDF: `CH_74docs.pdf`
- **CH_9** (CH) - 17 labeled pages, 9 expected covers, PDF: `CH_9.pdf`
- **CH_BSM_18** (CH_BSM) - 36 labeled pages, 18 expected covers, PDF: `CH_BSM_18.pdf`
- **CHAR_17** (CH) - 17 labeled pages, 17 expected covers, PDF: `CHAR_17.pdf`
- **CHAR_25** (CH) - 52 labeled pages, 25 expected covers, PDF: `CHAR_25.pdf`
- **CRS_9** (CRS) - 19 labeled pages, 9 expected covers, PDF: `CRS_9.pdf`
- **INS_31** (INS_31) - 31 labeled pages, 31 expected covers, PDF: `INS_31.pdf.pdf`
- **INSAP_20** (INSAP) - 31 labeled pages, 20 expected covers, PDF: `INSAP_20.pdf`
- **JOGA_19** (JOGA) - 38 labeled pages, 19 expected covers, PDF: `JOGA_19.pdf`
- **QUEVEDO_1** (QUEVEDO) - 2 labeled pages, 1 expected covers, PDF: `QUEVEDO_1.pdf`
- **QUEVEDO_13** (QUEVEDO) - 26 labeled pages, 13 expected covers, PDF: `QUEVEDO_13.pdf`
- **QUEVEDO_2** (QUEVEDO) - 4 labeled pages, 2 expected covers, PDF: `QUEVEDO_2.pdf`
- **RACO_25** (RACO) - 43 labeled pages, 25 expected covers, PDF: `RACO_25.pdf`
- **SAEZ_14** (SAEZ) - 24 labeled pages, 14 expected covers, PDF: `SAEZ_14.pdf`

Skipped 1 fixtures (no matching PDF found):

- ART_674_tess - no PDF in data\samples

## Sweep results (aggregated micro-averages)

| Scorer | Params | Micro P | Micro R | Micro F1 | Macro F1 | Exact / N | MAE count |
|--------|--------|--------:|--------:|---------:|---------:|----------:|----------:|
| find_peaks | prominence=0.05, distance=1 | 1.000 | 0.019 | 0.038 | 0.221 | 2/21 | 50.48 |
| find_peaks | prominence=0.1, distance=1 | 1.000 | 0.019 | 0.038 | 0.221 | 2/21 | 50.48 |
| find_peaks | prominence=0.1, distance=2 | 1.000 | 0.019 | 0.038 | 0.221 | 2/21 | 50.48 |
| find_peaks | prominence=0.2, distance=2 | 1.000 | 0.019 | 0.038 | 0.221 | 2/21 | 50.48 |
| find_peaks | prominence=0.3, distance=2 | 1.000 | 0.019 | 0.038 | 0.221 | 2/21 | 50.48 |
| percentile | percentile=60.0 | 0.470 | 0.610 | 0.531 | 0.522 | 1/21 | 24.48 |
| percentile | percentile=65.0 | 0.494 | 0.562 | 0.526 | 0.492 | 0/21 | 19.90 |
| percentile | percentile=70.0 | 0.516 | 0.504 | 0.510 | 0.446 | 1/21 | 15.00 |
| percentile | percentile=75.0 | 0.533 | 0.438 | 0.480 | 0.416 | 1/21 | 10.05 |
| percentile | percentile=80.0 | 0.556 | 0.370 | 0.444 | 0.376 | 1/21 | 17.43 |
| percentile | percentile=85.0 | 0.576 | 0.291 | 0.387 | 0.346 | 1/21 | 25.62 |

## Best run - per-family breakdown

Best by micro-F1: **percentile** with {'percentile': 60.0} - micro F1 0.531

| Family | N | Micro P | Micro R | Micro F1 | Exact count |
|--------|--:|--------:|--------:|---------:|------------:|
| ALUM | 2 | 0.526 | 0.500 | 0.513 | 0/2 |
| ART | 1 | 0.454 | 0.733 | 0.561 | 0/1 |
| CASTRO | 2 | 1.000 | 0.500 | 0.667 | 0/2 |
| CH | 6 | 0.477 | 0.381 | 0.424 | 0/6 |
| CH_BSM | 1 | 0.438 | 0.389 | 0.412 | 0/1 |
| CRS | 1 | 0.556 | 0.556 | 0.556 | 1/1 |
| INSAP | 1 | 0.500 | 0.350 | 0.412 | 0/1 |
| INS_31 | 1 | 1.000 | 0.452 | 0.622 | 0/1 |
| JOGA | 1 | 0.467 | 0.368 | 0.412 | 0/1 |
| QUEVEDO | 3 | 0.529 | 0.562 | 0.545 | 0/3 |
| RACO | 1 | 0.471 | 0.320 | 0.381 | 0/1 |
| SAEZ | 1 | 0.600 | 0.429 | 0.500 | 0/1 |

## Best run - per-fixture detail

| Fixture | Family | Expected | Predicted | TP | FP | FN | P | R | F1 | Diff |
|---------|--------|---------:|----------:|---:|---:|---:|--:|--:|---:|-----:|
| ALUM_1 | ALUM | 1 | 2 | 1 | 1 | 0 | 0.50 | 1.00 | 0.67 | +1 |
| ALUM_19 | ALUM | 19 | 17 | 9 | 8 | 10 | 0.53 | 0.47 | 0.50 | -2 |
| ART_674 | ART | 674 | 1088 | 494 | 594 | 180 | 0.45 | 0.73 | 0.56 | +414 |
| CASTRO_15 | CASTRO | 15 | 7 | 7 | 0 | 8 | 1.00 | 0.47 | 0.64 | -8 |
| CASTRO_5 | CASTRO | 5 | 3 | 3 | 0 | 2 | 1.00 | 0.60 | 0.75 | -2 |
| CH_39 | CH | 39 | 31 | 13 | 18 | 26 | 0.42 | 0.33 | 0.37 | -8 |
| CH_51 | CH | 51 | 42 | 19 | 23 | 32 | 0.45 | 0.37 | 0.41 | -9 |
| CH_74 | CH | 74 | 61 | 29 | 32 | 45 | 0.48 | 0.39 | 0.43 | -13 |
| CH_9 | CH | 9 | 8 | 3 | 5 | 6 | 0.38 | 0.33 | 0.35 | -1 |
| CH_BSM_18 | CH_BSM | 18 | 16 | 7 | 9 | 11 | 0.44 | 0.39 | 0.41 | -2 |
| CHAR_17 | CH | 17 | 7 | 7 | 0 | 10 | 1.00 | 0.41 | 0.58 | -10 |
| CHAR_25 | CH | 25 | 23 | 11 | 12 | 14 | 0.48 | 0.44 | 0.46 | -2 |
| CRS_9 | CRS | 9 | 9 | 5 | 4 | 4 | 0.56 | 0.56 | 0.56 | +0 |
| INS_31 | INS_31 | 31 | 14 | 14 | 0 | 17 | 1.00 | 0.45 | 0.62 | -17 |
| INSAP_20 | INSAP | 20 | 14 | 7 | 7 | 13 | 0.50 | 0.35 | 0.41 | -6 |
| JOGA_19 | JOGA | 19 | 15 | 7 | 8 | 12 | 0.47 | 0.37 | 0.41 | -4 |
| QUEVEDO_1 | QUEVEDO | 1 | 2 | 1 | 1 | 0 | 0.50 | 1.00 | 0.67 | +1 |
| QUEVEDO_13 | QUEVEDO | 13 | 12 | 6 | 6 | 7 | 0.50 | 0.46 | 0.48 | -1 |
| QUEVEDO_2 | QUEVEDO | 2 | 3 | 2 | 1 | 0 | 0.67 | 1.00 | 0.80 | +1 |
| RACO_25 | RACO | 25 | 17 | 8 | 9 | 17 | 0.47 | 0.32 | 0.38 | -8 |
| SAEZ_14 | SAEZ | 14 | 10 | 6 | 4 | 8 | 0.60 | 0.43 | 0.50 | -4 |