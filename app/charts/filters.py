# app/charts/filters.py
from __future__ import annotations

import pandas as pd
import streamlit as st

def specialization_and_drug_filters(df: pd.DataFrame):
    """
    Додає два мультиселект-фільтри:
    - по спеціалізаціях лікарів
    - по препаратах
    Повертає: (відфільтрований df, вибрані_спеціалізації, вибрані_препарати)
    Якщо користувач нічого не вибрав → показуємо всі.
    """
    specs = sorted(df["Спеціалізація лікаря"].dropna().unique()) if "Спеціалізація лікаря" in df.columns else []
    drugs = sorted(df["Препарат"].dropna().unique()) if "Препарат" in df.columns else []

    sel_specs = st.multiselect("Оберіть спеціалізації лікаря", options=specs, default=specs)
    sel_drugs = st.multiselect("Оберіть препарати", options=drugs, default=drugs)

    effective_specs = sel_specs or specs
    effective_drugs = sel_drugs or drugs

    df_filtered = df[
        df["Спеціалізація лікаря"].isin(effective_specs) &
        df["Препарат"].isin(effective_drugs)
    ].reset_index(drop=True)

    return df_filtered, effective_specs, effective_drugs