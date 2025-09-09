# app/data/transform.py
#перетворення DataFrame — unpivot, приведення типів, підготовка агрегатів для діаграм
from __future__ import annotations

import pandas as pd

def to_int_safe(series: pd.Series) -> pd.Series:
    """
    Акуратно приводить кількісну колонку до int:
    - некоректні значення -> NaN -> 0
    - округлення до найближчого цілого
    """
    s = pd.to_numeric(series, errors="coerce").fillna(0)
    return s.round().astype(int)

def unpivot_long(df_wide: pd.DataFrame, id_cols: list[str]) -> pd.DataFrame:
    """
    Перетворює «широку» таблицю у довгу:
    - ідентифікаторні колонки = id_cols
    - всі інші колонки стають «Препарат», значення -> «К-сть»
    - фільтрує нульові/від’ємні значення
    """
    value_cols = [c for c in df_wide.columns if c not in id_cols]
    if not value_cols:
        raise ValueError("Немає колонок для 'unpivot' після зафіксованих id_cols.")

    df_long = df_wide.melt(
        id_vars=id_cols,
        value_vars=value_cols,
        var_name="Препарат",
        value_name="К-сть",
    )
    df_long["К-сть"] = to_int_safe(df_long["К-сть"])
    df_long = df_long[df_long["К-сть"] > 0].reset_index(drop=True)
    return df_long

def group_by_drug_and_specialty(df_long: pd.DataFrame) -> pd.DataFrame:
    """
    Агрегація для першої діаграми:
    групування за ['Препарат','Спеціалізація лікаря'] з сумою «К-сть».
    """
    req = ["Препарат", "Спеціалізація лікаря", "К-сть"]
    _check_columns(df_long, req)
    grouped = (
        df_long.groupby(["Препарат", "Спеціалізація лікаря"], as_index=False)["К-сть"]
        .sum()
        .sort_values(by=["Препарат", "Спеціалізація лікаря"])
        .reset_index(drop=True)
    )
    return grouped

def build_combo_category(df: pd.DataFrame, left: str, right: str, sep: str = " • ") -> pd.DataFrame:
    """
    Додає колонку «Категорія» як конкатенацію двох текстових колонок (left + sep + right).
    Використовується для другої діаграми.
    """
    _check_columns(df, [left, right])
    out = df.copy()
    out["Категорія"] = out[left].astype(str) + sep + out[right].astype(str)
    return out

def group_for_combo_chart(df_long: pd.DataFrame, order_by: list[str] | None = None) -> pd.DataFrame:
    """
    Агрегація для комбінованої осі X (наприклад, «Препарат • Спеціалізація лікаря»).
    За замовчуванням сортує за ['Спеціалізація лікаря','Препарат'].
    """
    req = ["Препарат", "Спеціалізація лікаря", "К-сть"]
    _check_columns(df_long, req)

    order_by = order_by or ["Спеціалізація лікаря", "Препарат"]
    grouped = (
        df_long.groupby(["Препарат", "Спеціалізація лікаря"], as_index=False)["К-сть"]
        .sum()
        .sort_values(by=order_by)
        .reset_index(drop=True)
    )
    grouped = build_combo_category(grouped, left="Препарат", right="Спеціалізація лікаря")
    return grouped

# ----------------- helpers -----------------

def _check_columns(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"Відсутні необхідні колонки: {missing}")