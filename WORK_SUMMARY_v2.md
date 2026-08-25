# Work Summary: Experiment v2 - Fixing Generalization Problem

## Problem Identified (Session 1)
Models trained on 30.5k synthetic rows achieved excellent performance on synthetic test data (R²=0.925) but **completely failed on 100 real literature test cases**.

**Evidence of failure**:
- Fresh Mozzarella: Model predicts 5.9 days when truth is 4 days (+48%)
- Provolone: Model predicts 126 days when truth is 45 days (+180%!)
- Overall: MAE 50-100 days on literature cases (vs 8-9 days on synthetic test set)

**Root causes identified**:
1. Synthetic data generation doesn't match real cheese physics
2. Real data sparse (missing values filled with training medians)
3. Model learned synthetic correlations, not true causality
4. Temperature effects not properly calibrated
5. Global model instead of cheese-type-specific models

---

## Experiment v2: Solution Attempt (Session 2 - Today)

### Changes Implemented

#### 1. Dataset Expansion ✓
**File**: `CHEESE_SHELF_LIFE_CORRECTED_GENERALIZED_READY_TO_TRAIN.xlsx`

**Improvements**:
- **Old**: 30,500 rows × 36 columns
- **New**: 41,285 rows × 38 columns
- **Growth**: +10,785 rows (+35%), +2 new features

**New features**:
- `product_form`: 12 categories (intact_unspecified, wheel_or_wedge, spread_or_fresh_mass, etc.)
- `package_status`: Describes packaging condition

**Hypothesis**: 
More data + product form details should help model learn real-world shelf-life patterns better

#### 2. Frontend Enhancement ✓
**File**: `frontend/src/components/prediction-form.tsx`

**Changes**:
- Moved `primary_ingredient_family` from hidden advanced section to main prediction form
- Changed from text input to dropdown selector (consistency with other fields)
- Now visible and easily editable for every candidate ingredient

**User benefit**:
- Clearer UI: ingredient category selection no longer requires expanding advanced section
- Explicit control: users can independently choose ingredient family

#### 3. Training Infrastructure ✓
**Updated**: `train_models.py` (line 64)
```python
# OLD: CHEESE_SHELF_LIFE_REVISED_READY_TO_TRAIN.xlsx
# NEW: CHEESE_SHELF_LIFE_CORRECTED_GENERALIZED_READY_TO_TRAIN.xlsx
```

**Status**: All 5 models retraining with new dataset
- Random Forest
- LightGBM
- XGBoost (currently best)
- EBM (most explainable)
- LSTM (experimental)

---

## Comparison Strategy (After Training)

### Metrics to Evaluate

**1. Synthetic test set (should NOT degrade much)**
- v1 baseline: R² = 0.925, RMSE = 14.03 days
- v2 target: R² ≥ 0.90, RMSE ≤ 15 days
- Acceptable degradation: -3% (tolerance for increased data complexity)

**2. External literature test set (PRIMARY GOAL)**
- v1 baseline: MAE = 50-100 days (terrible)
- v2 target: MAE < 30 days (major improvement)
- Overprediction ratio:
  - Fresh Mozzarella: currently +48%, target < 20%
  - Provolone: currently +180%, target < 50%

### Decision Rules

✅ **ACCEPT v2** if:
- External literature MAE < 40 days (significant improvement)
- Overprediction on real cases < 50% (currently 80-180%)
- Synthetic test R² ≥ 0.90 (acceptable minor degradation)
- At least 2 of 3 metrics improved

❌ **REJECT v2** if:
- Synthetic test R² < 0.88 (too much degradation)
- External MAE > 100 days (worse than v1)
- Overprediction increases

---

## Backup & Safety

**v1 Models Saved**: `model_versions/v1_synthetic_only_2026-08-13_101320/`
- All trained models (RF, LGB, XGB, EBM, LSTM)
- Preprocessors, metrics, feature importance
- External test predictions & failure analysis
- Can revert anytime if v2 worse

---

## Timeline

- **10:30**: Training started with new dataset
- **Estimated completion**: 11:00 - 11:30 UTC (30-60 minute run)
- **Next step**: Run `evaluate_external_test.py` against same 100 literature cases
- **Analysis**: Compare v2 results to v1 baseline (expected 2026-08-13 11:30+)

---

## Files Modified Today

1. **train_models.py** - Updated dataset path
2. **frontend/src/components/prediction-form.tsx** - Added ingredient_family field to main form
3. **MODEL_VERSIONS.md** - Documented baseline and comparison rules
4. **GENERALIZATION_ANALYSIS.md** - Analyzed root causes
5. **EXPERIMENT_v2_IN_PROGRESS.md** - Tracked this experiment

---

## Success Criteria

This experiment succeeds if:
1. We reduce external literature test MAE significantly (< 40 days)
2. We maintain synthetic test performance (R² ≥ 0.90)
3. We can confidently recommend v2 for deployment

Otherwise, we use insights from v2 to design v3 (e.g., separate models per cheese type, add temperature calibration, etc.)
