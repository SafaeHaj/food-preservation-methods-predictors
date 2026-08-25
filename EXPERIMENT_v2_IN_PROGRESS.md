# Experiment v2: Enhanced Dataset + UI Updates (IN PROGRESS)

**Start time**: 2026-08-13 10:30 UTC
**Status**: Training running...

## Changes Made

### 1. Dataset Upgrade
**Old**: `CHEESE_SHELF_LIFE_REVISED_READY_TO_TRAIN.xlsx` (30,500 rows × 36 columns)
**New**: `CHEESE_SHELF_LIFE_CORRECTED_GENERALIZED_READY_TO_TRAIN.xlsx` (41,285 rows × 38 columns)

**Improvements**:
- +10,785 rows (+35% more data)
- +2 new features: `product_form` (12 categories), `package_status`
- Better generalization for real-world cases

### 2. Frontend Enhancement
**Added**: `primary_ingredient_family` as main prediction form field
- **Before**: Hidden in advanced "Ingredient descriptors" section
- **After**: Visible dropdown field right next to ingredient selection
- User can now easily select ingredient family (essential_oil, bacteriocin, enzyme, etc.)
- Non-editable input field converted to dropdown for consistency

### 3. Training Configuration
- Updated `train_models.py` to use new dataset
- Retraining all 5 models from scratch on expanded data
- Same preprocessing, train/val/test split strategy
- Random seed: 42 (deterministic)

## Expected Outcomes

### Best Case (hope to achieve)
- External literature test MAE: < 30 days (vs 50-100 currently)
- Overprediction on real cases: < 50% (vs 80-180% currently)
- Synthetic test R²: ≥ 0.90 (vs 0.93 baseline, acceptable -3% degradation)
- Product form helps differentiate between packaged/bulk forms

### Worst Case (would reject)
- Synthetic test R²: < 0.88 (too much degradation from baseline 0.93)
- External literature MAE: > 100 days (worse than v1)
- Product form adds noise instead of signal

## Key Metrics to Compare

| Metric | v1 Baseline | v2 Target | Status |
|--------|-------------|-----------|--------|
| Synthetic test R² (XGBoost) | 0.925 | ≥0.90 | PENDING |
| Synthetic test RMSE (XGBoost) | 14.03 | ≤15.0 | PENDING |
| External literature MAE | 50-100 | <30 | PENDING |
| Fresh Mozzarella overpred | +48% | <20% | PENDING |
| Provolone overpred | +180% | <50% | PENDING |

## Files Modified

1. **train_models.py** (line 64):
   - Changed XLSX_PATH to new dataset file

2. **frontend/src/components/prediction-form.tsx**:
   - Added `primary_ingredient_family` dropdown (main form)
   - Removed hidden ingredient descriptors section
   - Now shows as required field for candidates

## Next Steps (After Training Completes)

1. Run `python evaluate_external_test.py` on same 100 literature cases
2. Compare results to v1 baseline
3. If good → save to `model_versions/v2_expanded_data_Aug13/`
4. If bad → keep v1, adjust dataset and try again
5. Test frontend with new models
6. Verify ingredient_family selector works correctly

## Training Progress Log

```
[10:30] Started training with new dataset (41,285 rows)
[10:35] Expected completion: ~11:00-11:30
```

---

**Backup**: v1 models saved to `model_versions/v1_synthetic_only_2026-08-13_101320/`
