# app/ui/components.py
from __future__ import annotations
import streamlit as st
import pandas as pd


def display_kpi_card(title: str, value: str, help_text: str = ""):
    """
    Відображає стильну картку KPI.
    Використовує стандартний st.metric з додатковою підказкою.
    """
    st.metric(label=title, value=value, help=help_text)


def render_local_filters(df: pd.DataFrame, key_prefix: str = "") -> tuple[list[str], list[str]]:
    """
    Створює локальні фільтри для міста та вулиці.
    Повертає кортеж (selected_cities, selected_streets).
    """
    col1, col2 = st.columns(2)

    with col1:
        unique_cities = sorted(df.get("city", pd.Series(dtype=str)).dropna().unique().tolist())
        selected_cities = st.multiselect(
            "Місто:",
            options=unique_cities,
            default=[],
            key=f"{key_prefix}_city_filter"
        )

    with col2:
        if selected_cities:
            streets = df[df["city"].isin(selected_cities)]["street"].dropna().unique().tolist()
            unique_streets = sorted(streets)
        else:
            unique_streets = sorted(df.get("street", pd.Series(dtype=str)).dropna().unique().tolist())

        selected_streets = st.multiselect(
            "Вулиця:",
            options=unique_streets,
            default=[],
            key=f"{key_prefix}_street_filter"
        )

    return selected_cities, selected_streets


def apply_filters(df: pd.DataFrame, cities: list[str], streets: list[str]) -> pd.DataFrame:
    """
    Фільтрує DataFrame за містами та вулицями.
    Якщо список порожній — умова не застосовується.
    """
    out = df.copy()
    if cities:
        out = out[out["city"].isin(cities)]
    if streets:
        out = out[out["street"].isin(streets)]
    return out