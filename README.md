# Shelf-Life Studio

Predicts `shelf_life_days` from cheese formulation, processing, packaging,
and storage-condition features using five independently-trained regression
models: Random Forest, LightGBM, XGBoost, an Explainable Boosting Machine
(EBM), and an experimental tabular LSTM benchmark.

## Setup

```bash
pip install -r requirements.txt
python train_models.py
python app.py
```

Dashboard: **http://127.0.0.1:8050**

## Dataset

The sole dataset is `data/raw/CHEESE_SHELF_LIFE_REVISED_READY_TO_TRAIN.xlsx`
(sheet `training_data`, 30,500 rows). This dataset version is **entirely
synthetic** (scientifically-constrained generation) — there is no
real-paper-derived subset. It ships with no pre-built split, so
`train_models.py` builds one itself: rows are grouped by `context_id`
(never split across train/val/test), 70% / 15% / 15% train / validation /
test.

Identifier columns (`row_id`, `context_id`, `formulation_id`, `source_link`,
`source_row_id`) and data-provenance columns (`data_origin`,
`augmentation_method`, `training_weight`, `training_include`,
`quality_flag`) are excluded from model features — they describe the row's
lineage, not the product, and would leak trivially if used as inputs. The
remaining 34 columns are auto-detected as numeric / categorical / binary by
dtype and cardinality. The LSTM is an experimental tabular benchmark
included for comparison — this dataset is not temporal or sequential, and
the LSTM has no natural advantage here (its validation R² is honestly far
below the other four models).

## Artifacts

`python train_models.py` writes everything the dashboard reads, with no
MLflow and no server:

```text
artifacts/
  models/            fitted models + preprocessing objects (joblib / .keras)
  metrics.json        train/val/test R², RMSE, MAE, median AE, MAPE, duration
  feature_importance.json   permutation (all models) + native importance
  curves.json          loss curves (LightGBM/XGBoost/LSTM), learning curves (RF/EBM)
  predictions.parquet   row-level predictions for every model/split
  schema.json          feature roles, dropdown options, numeric ranges, control template
  uncertainty.json      per-model split-conformal 90% interval half-width
  category_errors.json  test MAE by cheese category / food matrix / indicator / control
  training_manifest.json  seed, row counts, real/synthetic counts, best model, run metadata
```

Re-run `python train_models.py` any time to retrain all five models from
scratch; `python app.py` never retrains — it only reads these files.

## Dashboard pages

Home, Datasets, Modeling, Prediction, Results, Explainability, How it works,
References — all sidebar-navigated, all reading the same saved artifacts.
Prediction writes its result to an in-memory store that Results and
Explainability's "local explanation of your last prediction" section both
read from; nothing is retrained or fetched live.
