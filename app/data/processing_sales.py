# app/data/processing_sales.py
from __future__ import annotations

import pandas as pd
import numpy as np
from datetime import date, timedelta

# --- робочі дні України (guarded import) ---
try:
    from workalendar.europe import Ukraine  # type: ignore
    _CAL_UA = Ukraine()
    _HAVE_WORKALENDAR = True
except Exception:
    Ukraine = None  # type: ignore
    _CAL_UA = None
    _HAVE_WORKALENDAR = False


def is_working_day(dt: date) -> bool:
    """
    True, якщо робочий день в Україні.
    Якщо workalendar недоступний — просте правило пн–пт.
    """
    if _HAVE_WORKALENDAR and _CAL_UA is not None:
        return _CAL_UA.is_working_day(dt)
    return dt.weekday() < 5


def create_full_address(df: pd.DataFrame) -> pd.DataFrame:
    """
    Створює єдину колонку 'full_address' з city, street, house_number (якщо її ще немає).
    """
    if 'full_address' not in df.columns:
        df = df.copy()
        df['full_address'] = (
            df.get('city', '').astype(str).fillna('') + ", " +
            df.get('street', '').astype(str).fillna('') + ", " +
            df.get('house_number', '').astype(str).fillna('')
        ).str.strip(' ,')
    return df


def compute_actual_sales(df: pd.DataFrame) -> pd.DataFrame:
    """
    Розраховує «фактичні» (чисті) продажі між декадами.

    Припущення: у вхідному df колонка 'quantity' — КУМУЛЯТИВНЕ значення на кінець декади.
    Алгоритм:
      1) очищення ключових текстових полів;
      2) створення 'full_address';
      3) агрегація продажів у межах декади;
      4) віднімання значення попередньої декади (shift) => actual_quantity;
      5) фільтр actual_quantity != 0.
    """
    req = [
        'decade', 'distributor', 'product_name', 'quantity',
        'year', 'month', 'city', 'street', 'house_number', 'new_client'
    ]
    for col in req:
        if col not in df.columns:
            # Повертаємо порожній df зі стандартними колонками — зручніше для UI
            return pd.DataFrame(
                columns=['distributor', 'product_name', 'full_address',
                         'year', 'month', 'decade', 'actual_quantity', 'new_client']
            )

    if df.empty:
        return pd.DataFrame(
            columns=['distributor', 'product_name', 'full_address',
                     'year', 'month', 'decade', 'actual_quantity', 'new_client']
        )

    # --- очищення текстових полів ---
    text_cols = ['distributor', 'product_name', 'city', 'street', 'house_number', 'new_client']
    df = df.copy()
    for c in text_cols:
        if c in df.columns:
            df[c] = df[c].fillna('').astype(str).str.strip()

    # повна адреса
    df = create_full_address(df)
    df = df[df['full_address'] != '']

    # decade у число
    df['decade'] = pd.to_numeric(df['decade'], errors='coerce').fillna(0).astype(int)

    if (df['distributor'] == '').all():
        return pd.DataFrame(
            columns=['distributor', 'product_name', 'full_address',
                     'year', 'month', 'decade', 'actual_quantity', 'new_client']
        )

    # 1) агрегація всередині декади
    df = df.groupby(
        ['distributor', 'product_name', 'full_address', 'year', 'month', 'decade', 'new_client'],
        as_index=False
    )['quantity'].sum()

    # 2) сортування для коректного shift
    df = df.sort_values(
        by=['distributor', 'product_name', 'full_address', 'year', 'month', 'new_client', 'decade']
    )

    # 3) попередня декада
    df['prev_decade_quantity'] = df.groupby(
        ['distributor', 'product_name', 'full_address', 'year', 'month', 'new_client']
    )['quantity'].shift(1).fillna(0)

    # 4) чисті продажі
    df['actual_quantity'] = df['quantity'] - df['prev_decade_quantity']

    # 5) вихід
    result = df[[
        'distributor', 'product_name', 'full_address',
        'year', 'month', 'decade', 'actual_quantity', 'new_client'
    ]].copy()

    # decade назад у рядок — якщо так очікує UI
    result['decade'] = result['decade'].astype(str)

    return result[result['actual_quantity'] != 0]