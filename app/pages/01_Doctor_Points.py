# app/pages/01_Doctor_Points.py
import os, sys
import streamlit as st

import pandas as pd

# --- Auth guard: require login before viewing this page ---
def _require_login():
    user = st.session_state.get('auth_user')
    if not user:
        st.warning("Будь ласка, увійдіть на головній сторінці, щоб переглядати цю сторінку.")
        st.stop()

# --- забезпечуємо імпорти виду "from app...." ---
PAGES_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(PAGES_DIR)
PROJECT_ROOT = os.path.dirname(APP_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from app.io.supabase_client import init_supabase_client

# --- helpers for data fetching ---
@st.cache_data(show_spinner=False)
def fetch_mp_options(_client) -> list[str]:
    """Return sorted list of full_name from profiles table (used for М.П. filter)."""
    try:
        res = _client.table("profiles").select("full_name").execute()
        data = res.data or []
        names = sorted({(row.get("full_name") or "").strip() for row in data if row.get("full_name")})
        return list(names)
    except Exception as e:
        st.error(f"Помилка читання профілів: {e}")
        return []

@st.cache_data(show_spinner=False)
def fetch_doctor_points_by_mp(_client, mp_values: list[str], limit: int | None = None) -> pd.DataFrame:
    """Fetch doctor_points filtered by column 'М.П.' ∈ mp_values."""
    if not mp_values:
        return pd.DataFrame()
    try:
        quoted_col = '"М.П."'
        q = _client.table("doctor_points").select("*").in_(quoted_col, mp_values)
        if limit:
            q = q.limit(limit)
        res = q.execute()
        data = res.data or []
        return pd.DataFrame(data) if data else pd.DataFrame()
    except Exception as e:
        st.error(f"Помилка читання з Supabase (doctor_points): {e}")
        return pd.DataFrame()

st.set_page_config(page_title="Doctor Points (Supabase)", layout="wide")
st.title("Doctor Points із Supabase")
_require_login()

# ------------- з’єднання з Supabase -------------
client = init_supabase_client()
if client is None:
    st.error("Не ініціалізовано Supabase. Додайте SUPABASE_URL та SUPABASE_KEY у st.secrets.")
    st.stop()

# ------------- М.П. фільтр з таблиці profiles -------------
mp_options = fetch_mp_options(client)
if not mp_options:
    st.warning("Не знайдено жодного М.П. у таблиці profiles.")
    st.stop()

# Ініціалізація стану
if "dp_df" not in st.session_state:
    st.session_state.dp_df = None
if "dp_selection" not in st.session_state:
    st.session_state.dp_selection = []

with st.form("mp_filter_form"):
    selected_mps = st.multiselect(
        "М.П. (з profiles.full_name)",
        options=mp_options,
        default=(st.session_state.dp_selection or mp_options),
    )
    submitted = st.form_submit_button("Отримати дані")

# Обчислюємо ефективний вибір (порожній => всі)
effective_mps = selected_mps or mp_options

# Якщо натиснули кнопку — оновлюємо дані в сесії
if submitted:
    with st.spinner("Завантажую дані doctor_points..."):
        df_new = fetch_doctor_points_by_mp(client, effective_mps)
    if df_new.empty:
        st.info("Дані відсутні для обраного(их) М.П.")
        st.session_state.dp_df = None
        st.session_state.dp_selection = effective_mps
        st.stop()
    st.session_state.dp_df = df_new
    st.session_state.dp_selection = effective_mps

# Після сабміту або при наступних ререндерах використовуємо кеш із session_state
if st.session_state.dp_df is None:
    st.info("Оберіть М.П. і натисніть \"Отримати дані\".")
    st.stop()

df = st.session_state.dp_df.copy()
st.success(
    f"Поточний відбір: {len(st.session_state.dp_selection)} М.П.; рядків: {len(df):,} × {df.shape[1]}"
)

# Спрощений перегляд без візуалізацій — лише сирі дані
st.subheader("Сирі дані (перші 200 рядків)")
st.dataframe(df.head(200), use_container_width=True)