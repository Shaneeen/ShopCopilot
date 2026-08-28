# Personalisation weight sweep

Ranks beyond top 10 are unavailable and are represented as 11 only for capped movement diagnostics.

| Weight | MRR | Delta | Hit@10 | MTTC | Improved | Worsened | Unchanged | Top-3 preserve |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0.181796 | +0.000000 | 0.262500 | 8.731250 | 0 | 0 | 160 | 1.0 |
| 0.025 | 0.183038 | +0.001242 | 0.268750 | 8.668750 | 2 | 2 | 156 | 1.0 |
| 0.05 | 0.183150 | +0.001354 | 0.268750 | 8.668750 | 3 | 2 | 155 | 1.0 |
| 0.1 | 0.182778 | +0.000982 | 0.275000 | 8.631250 | 6 | 5 | 149 | 0.96875 |
| 0.15 | 0.186119 | +0.004323 | 0.268750 | 8.693750 | 9 | 8 | 143 | 0.9375 |
| 0.2 | 0.193492 | +0.011696 | 0.281250 | 8.587500 | 12 | 8 | 140 | 0.9375 |
| 0.3 | 0.181143 | -0.000653 | 0.287500 | 8.525000 | 14 | 13 | 133 | 0.90625 |
| 0.4 | 0.153668 | -0.028128 | 0.281250 | 8.556250 | 10 | 20 | 130 | 0.78125 |

Recommended candidate weight: **0.2**. This is a dev-set candidate, not an automatic production change.
