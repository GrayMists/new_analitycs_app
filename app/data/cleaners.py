# app/data/cleaners.py
from __future__ import annotations

import pandas as pd
from app.core.config import DROP_COLS, RENAME_MAP, PIN_COLS, NUMERIC_WIDE_COLS

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Базова очистка:
    - скидає індекс
    - дропає зайві колонки (якщо вони є)
    """
    df = df.reset_index(drop=True).copy()
    for col in DROP_COLS:
        if col in df.columns:
            df = df.drop(columns=[col])
    return df

def apply_rename(df: pd.DataFrame) -> pd.DataFrame:
    """
    Перейменовує колонки за RENAME_MAP.
    Перейменовує тільки ті, які реально існують у df.
    """
    intersect = {k: v for k, v in RENAME_MAP.items() if k in df.columns}
    return df.rename(columns=intersect)

def reorder_others(df: pd.DataFrame, pin_cols: list[str] | None = None) -> pd.DataFrame:
    """
    Ставить «важливі» колонки (pin_cols або PIN_COLS) наперед,
    решта йде після них.
    """
    pin_cols = pin_cols or [c for c in PIN_COLS if c in df.columns]
    others = [c for c in df.columns if c not in pin_cols]
    return df[pin_cols + others]

def to_numeric_wide(df: pd.DataFrame) -> pd.DataFrame:
    """
    Приводить числові колонки у «широкій» таблиці до float.
    """
    df = df.copy()
    for col in NUMERIC_WIDE_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df