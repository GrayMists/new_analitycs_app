# app/charts/bars.py
from __future__ import annotations

import altair as alt
import pandas as pd

def bar_drug_vs_qty(df: pd.DataFrame, height: int = 400, rotate_labels: int = -45) -> alt.Chart:
    """
    Стовпчаста діаграма: x = Препарат, y = К-сть.
    Повертає alt.Chart (без виклику st.altair_chart).
    """
    _check_cols(df, ["Препарат", "К-сть"])
    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("Препарат:N",
                    sort=None,
                    axis=alt.Axis(labelAngle=rotate_labels, labelLimit=0)),
            y=alt.Y("К-сть:Q"),
            tooltip=[
                alt.Tooltip("Препарат:N", title="Препарат"),
                alt.Tooltip("К-сть:Q", title="Кількість", format=",.0f"),
            ],
        )
        .properties(width="container", height=height)
    )
    return chart

def bar_combo_category(df_with_cat: pd.DataFrame, height: int = 600, rotate_labels: int = -45) -> alt.Chart:
    """
    Стовпчаста діаграма з комбінованою категорією у колонці «Категорія».
    Очікує df, який вже містить:
      - «Категорія» (наприклад, 'Спеціалізація • Препарат')
      - «К-сть»
    """
    _check_cols(df_with_cat, ["Категорія", "К-сть"])
    chart = (
        alt.Chart(df_with_cat)
        .mark_bar()
        .encode(
            x=alt.X("Категорія:N",
                    sort=None,
                    axis=alt.Axis(labelAngle=rotate_labels, labelLimit=0)),
            y=alt.Y("К-сть:Q"),
            tooltip=[
                alt.Tooltip("Категорія:N", title="Категорія"),
                alt.Tooltip("К-сть:Q", title="Кількість", format=",.0f"),
            ],
        )
        .properties(width="container", height=height)
    )
    return chart

def bar_stacked_by_specialty(df: pd.DataFrame, height: int = 450, rotate_labels: int = -45) -> alt.Chart:
    """
    Варіант: x = Препарат, y = К-сть, колір = Спеціалізація лікаря (stacked).
    Корисно, коли хочеш бачити внесок спеціалізацій у кожен препарат.
    """
    _check_cols(df, ["Препарат", "Спеціалізація лікаря", "К-сть"])
    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("Препарат:N",
                    sort=None,
                    axis=alt.Axis(labelAngle=rotate_labels, labelLimit=0)),
            y=alt.Y("К-сть:Q", stack="zero"),
            color=alt.Color("Спеціалізація лікаря:N", legend=alt.Legend(title="Спеціалізація")),
            tooltip=[
                alt.Tooltip("Препарат:N", title="Препарат"),
                alt.Tooltip("Спеціалізація лікаря:N", title="Спеціалізація"),
                alt.Tooltip("К-сть:Q", title="Кількість", format=",.0f"),
            ],
        )
        .properties(width="container", height=height)
    )
    return chart

# -------------- helpers --------------

def _check_cols(df: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"Відсутні необхідні колонки: {missing}")