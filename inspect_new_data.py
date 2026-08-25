#!/usr/bin/env python
"""Inspect the new dataset"""
import pandas as pd

df = pd.read_excel('CHEESE_SHELF_LIFE_CORRECTED_GENERALIZED_READY_TO_TRAIN.xlsx', sheet_name='training_data')

print('=== NEW DATASET ANALYSIS ===')
print(f'Shape: {df.shape}')
print(f'Rows: {len(df)}, Columns: {len(df.columns)}')

print(f'\n--- NEW FEATURE CHECK ---')
if 'product_form' in df.columns:
    print(f'✓ product_form FOUND: {df["product_form"].nunique()} unique values')
    print(f'  Value counts:')
    print(df['product_form'].value_counts())
else:
    print('✗ product_form NOT FOUND')

print(f'\n--- ALL COLUMNS ({len(df.columns)}) ---')
for col in sorted(df.columns):
    print(f'  {col}')

print(f'\n--- MISSING VALUES ---')
missing = df.isnull().sum()
if missing.sum() > 0:
    print(missing[missing > 0])
else:
    print('No missing values ✓')

print(f'\n--- TARGET VARIABLE (shelf_life_days) ---')
print(f'Min: {df["shelf_life_days"].min():.2f} days')
print(f'Max: {df["shelf_life_days"].max():.2f} days')
print(f'Mean: {df["shelf_life_days"].mean():.2f} days')
print(f'Median: {df["shelf_life_days"].median():.2f} days')
print(f'Std: {df["shelf_life_days"].std():.2f} days')

print(f'\n--- CHANGES FROM V1 ---')
print('Old dataset: 30,500 rows × 36 columns')
print(f'New dataset: {len(df)} rows × {len(df.columns)} columns')
print(f'Difference: {len(df) - 30500:+d} rows, {len(df.columns) - 36:+d} columns')
