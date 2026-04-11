# DiT + Cosine benchmark - rio_bueno ART folders

Generated: 2026-04-11T19:06:20
Corpus: `A:\informe mensual\MARZO\rio_bueno\7.- ART  Realizadas`

## Baseline (handcrafted 80-d + L2)

- `scorer_rescue_c` - exact: 4/13, MAE: 9.5

## DiT + Cosine runs

| Scorer | Params | Exact / 13 | MAE |
|--------|--------|-----------:|----:|
| find_peaks | prominence=0.05, distance=1 | 0 | 62.38 |
| find_peaks | prominence=0.1, distance=1 | 0 | 62.38 |
| find_peaks | prominence=0.1, distance=2 | 0 | 62.38 |
| find_peaks | prominence=0.2, distance=2 | 0 | 62.38 |
| find_peaks | prominence=0.3, distance=2 | 0 | 62.38 |
| percentile | percentile=65.0 | 0 | 18.85 |
| percentile | percentile=70.0 | 1 | 11.92 |
| percentile | percentile=75.0 | 2 | 11.62 |
| percentile | percentile=80.0 | 1 | 18.62 |
| percentile | percentile=85.0 | 0 | 28.00 |

## Per-folder breakdown (best run)

Best: **percentile** with {'percentile': 75.0} - exact 2/13, MAE 11.62

| Folder | Expected | Counted | Diff |
|--------|---------:|--------:|-----:|
| ART AL2000  7 | 7 | 9 | +2 |
| ART C.PINOCHET 23 | 23 | 18 | -5 |
| ART CRS 424 | 424 | 341 | -83 |
| ART JOGA 21 | 21 | 16 | -5 |
| ART P.SAEZ 42 | 42 | 43 | +1 |
| ART PINGON 23 | 23 | 19 | -4 |
| ART RACO 38 | 38 | 40 | +2 |
| BSM 10 | 10 | 10 | +0 |
| INSAP  23 | 23 | 22 | -1 |
| JJC 83 | 83 | 94 | +11 |
| JMIE 28 | 28 | 21 | -7 |
| RIBEIRO 75 | 75 | 105 | +30 |
| STI  67 | 67 | 67 | +0 |