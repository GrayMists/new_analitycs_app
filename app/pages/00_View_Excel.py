# app/pages/00_Перегляд_Excel.py
import streamlit as st
import pandas as pd
import os, sys
PAGES_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(PAGES_DIR)
PROJECT_ROOT = os.path.dirname(APP_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from app.io.excel_reader import list_sheets, read_excel_bytes
from app.data.cleaners import clean_dataframe, apply_rename, reorder_others, to_numeric_wide
from app.data.transform import unpivot_long, group_by_drug_and_specialty, group_for_combo_chart
from app.charts.bars import bar_drug_vs_qty, bar_combo_category
from app.charts.filters import specialization_and_drug_filters
from app.io.supabase_client import init_supabase_client
from app.io.uploader import upload_doctor_points
from app.core.config import PIN_COLS, DROP_COLS, DEFAULT_HEADER_ROW

st.set_page_config(page_title="Перегляд Excel", layout="wide")
st.title("Перегляд Excel")

# --- Завантаження файлу ---
uploaded = st.file_uploader("Завантаж Excel-файл", type=["xlsx"])

if not uploaded:
    st.info("Оберіть файл .xlsx для перегляду.")
    st.stop()

# --- Вибір аркуша і заголовків ---
sheets = list_sheets(uploaded.getvalue())
sheet = st.selectbox("Аркуш", options=sheets, index=0 if sheets else 0)
header_row = st.number_input("Рядок заголовків (0-based)", min_value=0, value=DEFAULT_HEADER_ROW, step=1)

with st.spinner("Читаю файл..."):
    df = read_excel_bytes(uploaded.getvalue(), sheet_name=sheet, header_row=header_row)
    df = clean_dataframe(df)
    df = apply_rename(df)

    # Обрізаємо по якірній колонці, якщо є
    anchor_col = "Кіл-сть упаковок загальна"
    if anchor_col in df.columns:
        df = df.loc[:, :anchor_col]

    # Видаляємо непотрібні
    df = df.drop(columns=[col for col in DROP_COLS if col in df.columns], errors="ignore")

    # Формуємо зафіксовані колонки
    present_pins = [c for c in PIN_COLS if c in df.columns]
    df = reorder_others(df, present_pins)

    # Числові колонки
    df = to_numeric_wide(df)

    # Перетворюємо у довгий формат
    df_long = unpivot_long(df, id_cols=present_pins).reset_index(drop=True)
    df_long["Файл"] = uploaded.name

st.success(f"Зчитано: {len(df):,} рядків × {df.shape[1]} колонок")

# --- Кнопка завантаження у Supabase ---
client = init_supabase_client()
if client and not df_long.empty:
    if st.button("Завантажити в Supabase (doctor_points)"):
        inserted = upload_doctor_points(client, df_long, table_name="doctor_points")
        st.success(f"✅ Успішно завантажено {inserted} рядків у doctor_points")
elif not client:
    st.info("Додайте SUPABASE_URL та SUPABASE_KEY у st.secrets для завантаження у базу.")

# --- Відображення даних ---
st.subheader("Таблиця (довгий формат)")
st.dataframe(df_long, use_container_width=True)

