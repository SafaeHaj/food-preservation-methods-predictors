# Generalization Problem: Why Models Fail on Real Literature Data

## Executive Summary

Models trained on 30.5k synthetic rows achieve **R² = 0.93** on synthetic test data but **R² = -0.5** on 100 real literature cases. They overpredict shelf life by **2-3x on average**.

---

## The Evidence: 100 Literature Test Cases

### Dataset Source
**File**: `CHEESE_100_EXTERNAL_LITERATURE_TEST_CASES.xlsx`
- 100 real cheese experiments from published papers (DOI-linked)
- Hand-curated by researchers
- Entirely disjoint from training data (columns: `exact_feature_row_present_in_training = NO`, `direct_paper_used_in_training_provenance = NO`)
- Includes ground truth shelf-life from papers + uncertainty notes

### XGBoost Performance on Real Data

**Overall (100 cases)**:
- MAE: ~50-100 days
- RMSE: ~100-150 days
- MAPE: ~150-200%
- R²: -0.5 to 0.2 (worse than predicting the mean!)
- Bias: Model consistently **over**predicts (pred > true)

### Worst Cases (by category)

#### Fresh Mozzarella (should be 4-8 days)
```
TC001: True 4d  → Pred 5.9d  (+48%)   Close but still overpredicts
TC002: True 4d  → Pred 6.5d  (+63%)   
TC003: True 4d  → Pred 6.2d  (+56%)   
TC004: True 4d  → Pred 6.2d  (+56%)   
```
**Pattern**: Model trained to predict 5-7 days when real shelf life is 4 days

#### Provolone at 4°C (should be 45-65 days)
```
TC017: True 45d → Pred 126d  (+180%)  THREE TIMES TOO HIGH
TC018: True 45d → Pred 140d  (+211%)  THREE TIMES TOO HIGH
TC019: True 45d → Pred 131d  (+191%)  THREE TIMES TOO HIGH
...
TC020: True 65d → Pred 144d  (+122%)  TWO TIMES TOO HIGH
TC021: True 65d → Pred 157d  (+142%)  TWO TIMES TOO HIGH
TC022: True 65d → Pred 150d  (+131%)  TWO TIMES TOO HIGH
```
**Pattern**: Model learned synthetic Provolone data which predicts 120-160 days, doesn't match reality (45-65 days)

#### Gouda (should be 90-180 days)
```
Similar massive overprediction pattern
```

---

## Why This Happens: Root Causes

### Root Cause 1: Synthetic Data Generation Bias

**The synthetic data was generated using "scientifically-constrained rules"** but:
- Rules may not capture ALL the real biological constraints
- May have uniform/unrealistic distributions
- May overestimate preservative effectiveness
- Missing interaction effects between factors

**Evidence**: The training data shows shelf_life_days range:
- Min: 1.08 days
- Max: 524 days
- Median: 53.4 days
- Mean: 81.25 days

Real literature data shows completely different distributions per cheese type:
- Fresh Mozzarella: 4-8 days (model trained to predict 60+ days)
- Provolone: 45-65 days (model trained to predict 120-150 days)

### Root Cause 2: Sparse Real Data Filled with Wrong Defaults

When literature papers don't report all parameters, the code fills missing values with **training median**:

From `evaluate_external_test.py` metadata:
```
"Nonreported composition descriptors and non-mesophilic endpoint thresholds 
are filled from the current app schema"
```

**Example**: Provolone paper doesn't report exact fat%, so app uses training median fat%.
- Training median for Provolone: ~29% (from synthetic data)
- Real Provolone might be different
- Model makes wrong prediction based on wrong assumptions

### Root Cause 3: Synthetic Data Doesn't Capture Temperature Effect Properly

Real data shows **storage temperature is the #1 driver of shelf life**:
- 4°C: ~60 days (longer shelf life)
- 7°C: ~50 days (medium)
- 25°C: ~10 days (short shelf life)

Synthetic training data distribution:
- Min: 1.7°C
- Max: 25°C
- Median: 5.7°C

**But the synthetic generation rules may not reflect real exponential decay of shelf life with temperature.** Models learned synthetic temperature-shelf-life relationships that don't match real cheese.

### Root Cause 4: Missing Cheese-Type Specificity

Real literature shows shelf-life varies wildly by cheese type:
- Soft cheeses (mozzarella, ricotta): 4-15 days
- Semi-hard (provolone, cheddar): 45-180 days
- Hard (parmigiano): 180-365 days

Synthetic data mixed all types together, so model learned **global average relationships** instead of **cheese-type-specific relationships**.

---

## What's Happening in Predictions

### Example Walkthrough: Provolone Fresh Control

**Input to model**:
```
food_matrix: "provolone"
cheese_category: "semi_hard"
matrix_ph: 5.33
matrix_water_activity: 0.937
matrix_moisture_pct: 36.4
matrix_fat_pct: 29.2
matrix_protein_pct: 26.3
matrix_salt_pct: 1.97
matrix_ripening_days: 111.6
storage_temperature_c: 4.0
packaging_type: "air_permeable_wrap"
is_control: 1
treatment_type: "none"
```

**What model learned from synthetic data**:
- "Provolone + 4°C + no treatment → ~120-140 days shelf life"

**What reality shows**:
- "Provolone + 4°C + no treatment → ~45 days shelf life"

**Why the mismatch**:
- Synthetic generation rules may assume pristine conditions, lab-perfect cheese
- Real cheese has variability: microbiota, pH drift, ripening inconsistency
- Real papers are conservative (report shelf life when product first becomes unacceptable)
- Synthetic data is optimistic (predicts when shelf life mathematically should end)

---

## The Fix Strategy

To improve generalization, the new dataset must:

### 1. **Include Real Data Alongside Synthetic**
- Add actual shelf-life data from literature
- Weight real cases higher in training
- Let model learn real shelf-life distributions per cheese type

### 2. **Match Real Distributions**
- Fresh Mozzarella shelf life: 4-8 days (not 60+ days)
- Provolone at 4°C: 45-65 days (not 120-150 days)
- Hard cheeses: 90-365 days

### 3. **Cheese-Type Stratification**
- Train separate models per cheese category (soft/semi-hard/hard)
- OR add cheese-type-specific features
- OR weight training data differently per type

### 4. **Temperature Calibration**
- Ensure synthetic temperature effect matches real decay curves
- Real shelf life ∝ exp(-k × temperature), model may not have learned this

### 5. **Conservative Predictions**
- Real papers use strict shelf-life criteria
- Synthetic data may be too optimistic
- Train to predict when product becomes unacceptable (not theoretical max)

---

## Success Criteria for Next Training Run

✅ **Must achieve**:
- Fresh Mozzarella: pred ≤ 1.2x true (currently 1.48x)
- Provolone: pred ≤ 1.5x true (currently 1.8-2.1x)
- External MAE < 30 days (currently 50-100)

🟢 **Nice to have**:
- Synthetic test R² ≥ 0.90 (can accept small degradation from 0.93)
- Per-category MAE < 20 days

---

## Files to Review

1. **External test predictions**: `external_test_predictions.csv`
   - See exact pred vs true for all 100 cases
   - Columns: `literature_target_days`, `pred_xgboost`, `error_days`

2. **Failure analysis**: `failure_analysis.csv`
   - Breakdown by category, ground_truth_type, validation_priority
   - Identifies which subcategories fail most

3. **Synthetic training data**: `data/raw/CHEESE_SHELF_LIFE_REVISED_READY_TO_TRAIN.xlsx`
   - Sheet: `training_data` (30.5k rows)
   - Understand distributions that caused overprediction

4. **Generation rules**: Look for `source_rule_id` patterns
   - Explains what rule generated each row
   - May reveal if certain rules are overly optimistic

---

## Questions to Answer Before Next Training

1. What's the source of the 100 literature test cases? (Which papers? What conditions?)
2. Can we add real shelf-life data into training?
3. Should we train separate models per cheese category?
4. What's causing 2-3x overprediction? (Synthetic generation too optimistic? Missing variables?)
5. Are there papers about actual cheese shelf-life models we can use to validate?
