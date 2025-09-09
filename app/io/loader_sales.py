# app/io/loader_sales.py
from __future__ import annotations

import streamlit as st
import pandas as pd
from typing import List, Optional

from app.io.supabase_client import init_supabase_client

# Ініціалізуємо клієнт один раз (кеш ресурсу бажано у самій init_supabase_client)
supabase = init_supabase_client()


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_all_sales_data(
    region_name: Optional[str],
    territory: str,
    line: str,
    months: List[str] | List[int] | None,
) -> pd.DataFrame:
    """
    Завантажує дані з таблиці sales_data, використовуючи пагінацію та фільтри.
    Повертає DataFrame з колонкою quantity як int (NaN -> 0).
    """
    if supabase is None:
        st.error("Supabase клієнт не ініціалізований. Перевірте st.secrets.")
        return pd.DataFrame()

    all_data = []
    offset = 0
    page_size = 1000

    select_query = (
        "distributor,client,new_client,product_name,quantity,city,street,house_number,"
        "territory,adding,product_line,delivery_address,year,month,decade,region"
    )

    # Не кастимо у int: у БД "month" може бути рядком типу "01".."12".
    # Легко нормалізуємо до str і зберігаємо формат з UI.
    if months:
        months_norm = [str(m).strip() for m in months]
    else:
        months_norm = None

    while True:
        try:
            query = supabase.table("sales_data").select(select_query).range(offset, offset + page_size - 1)

            # Фільтр за регіоном (людська назва)
            if region_name and region_name != "Оберіть регіон...":
                query = query.eq("region", str(region_name).strip())

            # Фільтри територія/лінія
            if territory and territory != "Всі":
                query = query.eq("territory", str(territory).strip())
            if line and line != "Всі":
                query = query.eq("product_line", str(line).strip())

            # Фільтр за місяцями (якщо є)
            if months_norm:
                query = query.in_("month", months_norm)

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
            st.error(f"Помилка при завантаженні sales_data з Supabase: {e}")
            return pd.DataFrame()

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    # Приводимо quantity до int
    df["quantity"] = pd.to_numeric(df.get("quantity"), errors="coerce").fillna(0).astype(int)
    # Нормалізуємо місяць у два представлення
    # month_str: "01".."12" (для фільтрів по sales_data)
    # month_int: Int64 1..12 (для джоїнів та розрахунків)
    df["month_str"] = df.get("month").astype(str).str.zfill(2)
    df["month_int"] = pd.to_numeric(df["month_str"], errors="coerce").astype("Int64")
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_price_data(region_id: int, months: List[str] | List[int]) -> pd.DataFrame:
    """
    Завантажує дані про ціни з таблиці 'price' для вказаного region_id та місяців.
    Повертає: product_name, price (float), month (Int64)
    """
    if supabase is None:
        st.error("Supabase клієнт не ініціалізований. Перевірте st.secrets.")
        return pd.DataFrame()

    if not months or not region_id:
        return pd.DataFrame()

    try:
        # Уніфікуємо місяці: працюємо в БД з int, оскільки price.month = int2
        numeric_months = [int(m) for m in months]
        query = (
            supabase.table("price")
            .select("product_name,price,month")
            .eq("region_id", region_id)
            .in_("month", numeric_months)
        )
        response = query.execute()
        rows = response.data or []

        if not rows:
            return pd.DataFrame()

        price_df = pd.DataFrame(rows).drop_duplicates(subset=["product_name", "month"], keep="last")
        price_df["price"] = pd.to_numeric(price_df["price"], errors="coerce")
        # додаємо уніфіковану колонку month_int для злиття
        price_df["month_int"] = pd.to_numeric(price_df["month"], errors="coerce").astype("Int64")
        return price_df

    except Exception as e:
        st.error(f"Помилка при завантаженні цін з Supabase: {e}")
        return pd.DataFrame()