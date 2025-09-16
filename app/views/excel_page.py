# app/views/excel_page.py
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
# Видаляємо імпорт навігації, оскільки вона вже є в основному файлі
from app.core.config import PIN_COLS, DROP_COLS, DEFAULT_HEADER_ROW
import re

# --- Auth guard: require login before viewing this page ---
def _require_login():
    user = st.session_state.get('auth_user')
    if not user:
        st.warning("Будь ласка, увійдіть на головній сторінці, щоб переглядати цю сторінку.")
        st.stop()
    
    # Перевіряємо чи користувач є адміністратором
    user_type = user.get('type', '').lower()
    if user_type != 'admin':
        st.error("❌ Доступ заборонено. Ця сторінка доступна тільки адміністраторам.")
        st.info("Зверніться до адміністратора для отримання доступу.")
        st.stop()

def show():
    """
    Основна функція сторінки Excel та завантаження
    """
    # Перевіряємо авторизацію
    _require_login()

    st.title("📊 Excel та завантаження")
    
    # Показуємо інформацію про користувача
    user = st.session_state.get('auth_user')
    if user:
        st.info(f"👤 Користувач: {user.get('email', 'Невідомий')} | Тип: {user.get('type', 'Невідомий').upper()}")
    
    # Створюємо перемикач між контентом
    content_type = st.radio(
        "Оберіть тип контенту:",
        ["📊 Бали", "⬆️ Продажі"],
        horizontal=True,
        key="excel_content_selector"
    )
    
    st.divider()
    
    if content_type == "📊 Бали":
        show_excel_content()
    else:
        show_upload_content()

def show_excel_content():
    """
    Контент табу "Бали" (Excel)
    """
    st.subheader("📊 Перегляд Excel файлів з балами")

    # --- Завантаження файлу ---
    uploaded = st.file_uploader("Завантаж Excel-файл", type=["xlsx"])

    if not uploaded:
        st.info("Оберіть файл .xlsx для перегляду.")
        st.stop()

    with st.spinner("Читаю файл..."):
        # Always use first sheet and skip first 2 rows (header at row 2, i.e., third row)
        df = read_excel_bytes(uploaded.getvalue(), sheet_name=0, header_row=2)
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

        # Extract year and month from filename (allowing underscore or space between)
        match = re.search(r'(\d{4})[_ ](\d{2})', uploaded.name)
        if match:
            df_long["year"] = int(match.group(1))
            df_long["month"] = int(match.group(2))
        else:
            df_long["year"] = None
            df_long["month"] = None

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

def show_upload_content():
    """
    Контент табу "Продажі" (завантаження)
    """
    # Імпортуємо функціонал завантаження
    from app.views.upload_page import show as show_upload
    
    # Викликаємо функцію завантаження без заголовка
    show_upload(show_title=False)

def show_excel_page():
    """
    Сторінка: 📊 Excel
    Обгортка для інтеграції з навігацією
    """
    show()