# app/io/loader_stock.py
from __future__ import annotations

import streamlit as st
import pandas as pd
from typing import Optional

from app.io.supabase_client import init_supabase_client

supabase = init_supabase_client()


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_medical_representatives() -> pd.DataFrame:
    if supabase is None:
        st.error("Supabase клієнт не ініціалізований.")
        return pd.DataFrame()
    try:
        response = (
            supabase.table("medical_representatives")
            .select("id, full_name, mp_line, region")
            .order("full_name")
            .execute()
        )
        rows = response.data or []
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)
    except Exception as e:
        st.error(f"Помилка при завантаженні списку МП: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_stock_reports(
    mp_ids: Optional[tuple],
    date_from: str,
    date_to: str,
) -> pd.DataFrame:
    if supabase is None:
        st.error("Supabase клієнт не ініціалізований.")
        return pd.DataFrame()

    all_data = []
    offset = 0
    page_size = 1000

    select_query = (
        "id, drug_name, quantity, visit_date, mp_id, pharmacy_id, visit_session_id,"
        "medical_representatives(id, full_name),"
        "pharmacies(id, name, city)"
    )

    while True:
        try:
            query = (
                supabase.table("pharmacy_stock_reports")
                .select(select_query)
                .gte("visit_date", date_from)
                .lte("visit_date", date_to)
                .order("visit_date", desc=False)
                .range(offset, offset + page_size - 1)
            )
            if mp_ids:
                query = query.in_("mp_id", list(mp_ids))

            response = query.execute()

            if response.data:
                batch = response.data
                all_data.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size
            else:
                break
        except Exception as e:
            st.error(f"Помилка при завантаженні залишків з Supabase: {e}")
            return pd.DataFrame()

    if not all_data:
        return pd.DataFrame()

    records = []
    for r in all_data:
        mr = r.get("medical_representatives") or {}
        ph = r.get("pharmacies") or {}
        records.append({
            "id": r.get("id"),
            "pharmacy_id": r.get("pharmacy_id"),
            "pharmacy_name": ph.get("name", ""),
            "pharmacy_city": ph.get("city", ""),
            "drug_name": r.get("drug_name", ""),
            "mp_id": r.get("mp_id"),
            "mp_full_name": mr.get("full_name", ""),
            "quantity": r.get("quantity", 0),
            "visit_date": r.get("visit_date"),
            "visit_session_id": r.get("visit_session_id"),
        })

    df = pd.DataFrame(records)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)
    df["visit_date"] = pd.to_datetime(df["visit_date"], errors="coerce")
    return df
