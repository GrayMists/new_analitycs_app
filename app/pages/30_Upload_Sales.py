# app/pages/20_Upload_Sales.py
from __future__ import annotations

import os, sys, re
import streamlit as st
import pandas as pd

# --- додаємо корінь проєкту у sys.path ---
PAGES_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(PAGES_DIR)
PROJECT_ROOT = os.path.dirname(APP_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from app.utils import PRODUCTS_DICT
from app.io.supabase_client import init_supabase_client

# ініціалізація supabase
supabase = init_supabase_client()


def normalize_address(address: str) -> str:
    """Надійна нормалізація рядка адреси."""
    if not isinstance(address, str):
        address = str(address)
    address = address.replace("\xa0", " ")
    address = re.sub(r"\s+", " ", address)
    return address.lower().strip()


def get_golden_address(address: str, golden_map: dict) -> dict:
    """Повертає golden-рядок адреси, якщо знайдений у golden_map."""
    lookup_key = normalize_address(address)
    default_result = {"city": None, "street": None, "number": None, "territory": None}
    return golden_map.get(lookup_key, default_result)


def show():
    st.title("🚀 Завантаження та стандартизація даних продажів")
    st.write("Завантажте ваш Excel-файл, оберіть регіон і натисніть кнопку — дані будуть оброблені й готові для завантаження у Supabase.")

    if supabase is None:
        st.error("❌ Supabase не ініціалізовано. Перевірте st.secrets.")
        st.stop()

    # --- довідники ---
    try:
        all_regions_data = supabase.table("region").select("*").execute().data or []
        all_clients_data = supabase.table("client").select("*").execute().data or []
    except Exception as e:
        st.error(f"Помилка при завантаженні довідників: {e}")
        all_regions_data, all_clients_data = [], []

    if all_clients_data:
        client_map = {str(row.get("client")).strip(): row.get("new_client") for row in all_clients_data if row.get("client")}
    else:
        client_map = {}

    col1, col2 = st.columns(2)
    with col1:
        uploaded_file = st.file_uploader("1. Виберіть Excel-файл з адресами", type=["xlsx", "xls"], key="file_uploader")

    with col2:
        if all_regions_data:
            region_names = [r["name"] for r in all_regions_data]
            selected_region_name = st.selectbox("2. Оберіть регіон:", region_names, key="region_selector")
        else:
            st.warning("Не вдалося завантажити список регіонів.")
            selected_region_name = None

    if st.button("🚀 Опрацювати файл", type="primary", key="process_button"):
        if uploaded_file is not None and selected_region_name is not None:
            try:
                df = pd.read_excel(uploaded_file)
                required_columns = ["Регіон", "Факт.адреса доставки", "Найменування", "Клієнт"]
                if not all(c in df.columns for c in required_columns):
                    st.error(f"Помилка: у файлі відсутні колонки: {', '.join(required_columns)}")
                    st.stop()

                df_filtered = df[df["Регіон"] == selected_region_name].copy()
                if df_filtered.empty:
                    st.warning(f"Немає рядків для регіону {selected_region_name}.")
                    st.stop()

                # шукаємо ID регіону
                region_id = next((r["id"] for r in all_regions_data if r["name"] == selected_region_name), None)
                if region_id is None:
                    st.error("Не знайдено ID регіону.")
                    st.stop()

                # golden addresses
                golden_map = {}
                try:
                    response = supabase.table("golden_addres").select("*").eq("region_id", region_id).execute()
                    for row in response.data or []:
                        if row.get("Факт.адреса доставки"):
                            golden_map[normalize_address(row["Факт.адреса доставки"])] = {
                                "city": row.get("Місто"),
                                "street": row.get("Вулиця"),
                                "number": str(row.get("Номер будинку")) if row.get("Номер будинку") is not None else None,
                                "territory": row.get("Територія"),
                            }
                except Exception as e:
                    st.warning(f"Не вдалося завантажити golden addresses: {e}")

                parsed_addresses = df_filtered["Факт.адреса доставки"].apply(get_golden_address, golden_map=golden_map)
                parsed_df = pd.json_normalize(parsed_addresses)
                parsed_df = parsed_df.rename(
                    columns={"city": "City", "street": "Street", "number": "House_Number", "territory": "Territory"}
                )

                df_filtered.reset_index(drop=True, inplace=True)
                parsed_df.reset_index(drop=True, inplace=True)
                result_df = pd.concat([df_filtered, parsed_df], axis=1)

                # додаємо дату з назви файлу (yyyy_mm_dd або yyyy_mm)
                date_match = re.search(r"(\\d{4}_\\d{2}(_\\d{2})?)", uploaded_file.name)
                if date_match:
                    parts = date_match.group(0).split("_")
                    result_df["year"] = parts[0]
                    result_df["month"] = parts[1]
                    result_df["decade"] = parts[2] if len(parts) > 2 else None
                    result_df["adding"] = date_match.group(0)
                else:
                    result_df["year"] = result_df["month"] = result_df["decade"] = result_df["adding"] = None

                # визначаємо product_line за словником
                result_df["Product_Line"] = result_df["Найменування"].str[3:].map(PRODUCTS_DICT)

                # мапимо клієнтів
                if client_map:
                    result_df["new_client"] = result_df["Клієнт"].astype(str).str.strip().map(client_map)
                else:
                    result_df["new_client"] = None

                st.session_state["upload_result_df"] = result_df
                st.success("✅ Файл опрацьовано!")
            except Exception as e:
                st.error(f"Помилка при обробці файлу: {e}")

    # після опрацювання
    if "upload_result_df" in st.session_state:
        df = st.session_state["upload_result_df"]
        st.dataframe(df, use_container_width=True)

        unmatched_df = df[df["City"].isna()]
        if not unmatched_df.empty:
            st.subheader("⚠️ Адреси, не знайдені в golden")
            st.dataframe(unmatched_df[["Факт.адреса доставки"]])

        if st.button("💾 Завантажити у Supabase", key="upload_button"):
            with st.spinner("Вставка у Supabase..."):
                try:
                    upload_df = df.rename(
                        columns={
                            "Дистриб'ютор": "distributor",
                            "Регіон": "region",
                            "Місто": "city_xls",
                            "ЄДРПОУ": "edrpou",
                            "Клієнт": "client",
                            "Юр. адреса клієнта": "client_legal_address",
                            "Факт.адреса доставки": "delivery_address",
                            "Найменування": "product_name",
                            "Кількість": "quantity",
                            "adding": "adding",
                            "City": "city",
                            "Street": "street",
                            "House_Number": "house_number",
                            "Territory": "territory",
                            "Product_Line": "product_line",
                            "year": "year",
                            "month": "month",
                            "decade": "decade",
                            "new_client": "new_client",
                        }
                    )
                    cols = [
                        "distributor",
                        "region",
                        "city_xls",
                        "edrpou",
                        "client",
                        "client_legal_address",
                        "delivery_address",
                        "product_name",
                        "quantity",
                        "adding",
                        "city",
                        "street",
                        "house_number",
                        "territory",
                        "product_line",
                        "year",
                        "month",
                        "decade",
                        "new_client",
                    ]
                    final_upload_df = upload_df[[c for c in cols if c in upload_df.columns]]
                    final_upload_df = final_upload_df.where(pd.notna(final_upload_df), None)
                    data_to_insert = final_upload_df.to_dict(orient="records")

                    resp = supabase.table("sales_data").insert(data_to_insert).execute()
                    if resp.data:
                        st.success(f"✅ Завантажено {len(resp.data)} рядків.")
                    else:
                        st.error(f"Не вдалося завантажити: {resp.error if hasattr(resp, 'error') else 'невідома помилка'}")
                except Exception as e:
                    st.error(f"Помилка при завантаженні у Supabase: {e}")


# виклик для Streamlit
if __name__ == "__main__":
    show()
else:
    show()