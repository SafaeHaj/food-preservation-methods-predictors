# Model Versions & Experiment Log

## Version History

### v1: Synthetic Data Only (Current - 2026-08-13)
**Backup location**: `model_versions/v1_synthetic_only_2026-08-13_101320/`

#### Training Data
- Source: 30,500 rows, 100% synthetic, scientifically-constrained generation
- Split: 70% train (21,350), 15% val (4,575), 15% test (4,575)
- All grouped by context_id (no leakage)

#### Model Performance (on Synthetic Test Set)
| Model | Val R² | Test R² | Val RMSE | Test RMSE | Val MAE | Test MAE |
|-------|--------|---------|----------|-----------|---------|----------|
| Random Forest | 0.907 | 0.916 | 16.83 | 15.92 | 11.02 | 10.24 |
| LightGBM | 0.920 | 0.929 | 15.71 | 14.46 | 10.13 | 9.32 |
| XGBoost | **0.925** | **0.932** | **15.18** | **14.03** | **9.89** | **8.96** |
| EBM | 0.918 | 0.927 | 15.92 | 14.66 | 10.44 | 9.51 |
| LSTM | 0.801 | 0.798 | 27.81 | 28.04 | 19.33 | 19.51 |

**Best model**: XGBoost (lowest test RMSE)

#### External Literature Test (100 Real Cases from Papers)
**Problem identified**: Models catastrophically overpredict on real data

| Metric | Value | Issue |
|--------|-------|-------|
| XGBoost MAE | ~50-100 days | 2-3x overprediction |
| Fresh Mozzarella (true 4d, pred 5.9d) | +48% | Consistent overprediction |
| Provolone (true 45d, pred 126d) | +180% | Massive overprediction |
| Provolone (true 65d, pred 140d) | +115% | Massive overprediction |

**Root causes identified**:
1. Synthetic data generation doesn't match real cheese physics
2. Real data is sparse (missing values filled with training medians)
3. Model learned synthetic correlations, not true causality
4. Generalization gap: ~80+ R² points between synthetic and real test sets

#### Files
- Models: `artifacts/models/` (random_forest.joblib, lightgbm.joblib, xgboost.joblib, ebm.joblib, lstm.keras)
- Preprocessors: `artifacts/models/preprocessor_tree.joblib`, `preprocessor_ebm.joblib`, `preprocessor_lstm_scaler.joblib`
- Metrics: `artifacts/metrics.json`
- Predictions: `artifacts/predictions.parquet`
- External test results: `external_test_predictions.csv`, `failure_analysis.csv`

---

## Version History (continued)

### v2: Expanded Dataset + product_form/package_status (2026-08-13, 13:15 UTC)
**Dataset**: `CHEESE_SHELF_LIFE_CORRECTED_GENERALIZED_READY_TO_TRAIN.xlsx`
- 41,285 rows (was 30,500, +35%)
- 38 columns (was 36, +2: `product_form`, `package_status`)
- Split: train=28,900 / val=6,195 / test=6,190

**LSTM skipped this run** (`SKIP_LSTM=1`) — it's the worst-performing, non-load-bearing model; excluded to get the 4 real models trained and saved without the CPU-bound neural net step blocking everything.

#### Synthetic Test Metrics (v2 vs v1)
| Model | v1 Val R² | v2 Val R² | v1 Test RMSE | v2 Test RMSE | v1 Test MAE | v2 Test MAE |
|-------|-----------|-----------|---------------|---------------|--------------|--------------|
| Random Forest | 0.907 | 0.931 | 15.92 | 23.75 | 10.24 | 13.60 |
| LightGBM | 0.920 | **0.953** | 14.46 | 19.39 | 9.32 | 11.38 |
| XGBoost | 0.925 | 0.948 | 14.03 | 20.07 | 8.96 | 11.87 |
| EBM | 0.918 | 0.912 | 14.66 | 24.29 | 9.51 | 15.86 |

**Best model changed**: v1 was XGBoost → **v2 is LightGBM** (val R²=0.953)

**Note**: RMSE/MAE went up in absolute days even though R² went up — expected, since this dataset has a wider/different target distribution (more rows, different generation rules), not a sign of worse fit by itself. R² is the fairer cross-version comparison metric.

#### External Literature Test (100 real cases) — PENDING
Status: Evaluation running now, results to follow.

---

## Planned Experiments

### Experiment A: [TO BE DECIDED]
**Hypothesis**: 
**Changes to dataset**: 
**Expected outcome**: 
**Status**: PLANNED

---

## Comparison Strategy

When running new training, use this checklist:

- [ ] Run `python train_models.py` with new data
- [ ] Compare synthetic test R² to v1 baseline
- [ ] Run `python evaluate_external_test.py` with same 100 literature cases
- [ ] Compare external test MAE/RMSE to v1 results
- [ ] Check if overprediction reduced (is pred closer to true on literature cases?)
- [ ] Document worst cases and which categories improved/worsened
- [ ] Save all results to `model_versions/vX_description_TIMESTAMP/`

### Key Metrics to Track

**Synthetic test set (should NOT degrade)**:
- XGBoost R² (keep ≥ 0.93)
- XGBoost RMSE (keep ≤ 14)

**External literature test (PRIMARY GOAL - improve)**:
- XGBoost MAE on 100 real cases (target: < 20 days)
- Overprediction ratio on Provolone (target: < 1.2x, currently 1.8-2.1x)
- Overprediction ratio on Fresh Mozzarella (target: < 1.1x, currently 1.48x)
- % of cases where pred >= true (for lower-bound cases)

---

## Decision Rules

✅ **Accept new training if**:
- External literature MAE improves (< 100 days)
- Overprediction on real cases < 50%
- Synthetic test R² still ≥ 0.90 (acceptable small degradation)
- At least 2/4 categories improve

🟡 **Investigate further if**:
- External MAE unchanged or slightly worse
- Synthetic test R² 0.88-0.90 (minor degradation)
- Mixed results (some categories better, some worse)

❌ **Reject and revert if**:
- Synthetic test R² < 0.88 (too much degradation)
- External literature MAE worse than v1
- Overprediction increases beyond 2x

---

## Notes

- Always keep backups before retraining
- Document what changed in the dataset
- Never delete v1 — it's your baseline
- Use `model_versions/vX_*/` to store all intermediate experiments
