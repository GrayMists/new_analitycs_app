# app/views/doctor_points_page.py
import os, sys
import streamlit as st
import plotly.express as px
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
from app.auth.authentication import get_current_user

# --- helpers for data fetching ---
MONTH_NAMES = {
    1: "Січень",
    2: "Лютий",
    3: "Березень",
    4: "Квітень",
    5: "Травень",
    6: "Червень",
    7: "Липень",
    8: "Серпень",
    9: "Вересень",
    10: "Жовтень",
    11: "Листопад",
    12: "Грудень"
}

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
def fetch_year_options(_client) -> list[int]:
    """Return sorted distinct years from doctor_points.year (as ints)."""
    try:
        res = _client.table("doctor_points").select("year").execute()
        data = res.data or []
        years = sorted({int(row["year"]) for row in data if row.get("year") is not None})
        return years
    except Exception as e:
        st.warning(f"Не вдалося отримати список років: {e}")
        return []

@st.cache_data(show_spinner=False)
def fetch_month_options() -> list[str]:
    """Return list of month names."""
    return list(MONTH_NAMES.values())

@st.cache_data(show_spinner=False)
def fetch_doctor_points_by_mp(_client, mp_values: list[str], year: int | list[int] | None = None, month: int | list[int] | None = None, limit: int | None = None) -> pd.DataFrame:
    """Fetch doctor_points filtered by column 'М.П.' ∈ mp_values."""
    if not mp_values:
        return pd.DataFrame()
    try:
        q = _client.table("doctor_points").select("*")
        if year is not None:
            if isinstance(year, list):
                q = q.in_("year", [int(y) for y in year])
            else:
                q = q.eq("year", int(year))
        if month is not None:
            if isinstance(month, list):
                if len(month) == 1:
                    q = q.eq("month", str(int(month[0])))
                else:
                    q = q.in_("month", [str(int(m)) for m in month])
            else:
                q = q.eq("month", str(int(month)))
        if mp_values:
            quoted_col = '"М.П."'
            q = q.in_(quoted_col, mp_values)
        if limit:
            q = q.limit(limit)

        res = q.execute()
        data = res.data or []
        return pd.DataFrame(data) if data else pd.DataFrame()
    except Exception as e:
        st.error(f"Помилка читання з Supabase (doctor_points): {e}")
        return pd.DataFrame()

st.set_page_config(page_title="Doctor Points (Supabase)", layout="wide")

def show():
    """Main function to display the doctor points page"""
    st.title("Doctor Points із Supabase")
    _require_login()

    # ------------- з'єднання з Supabase -------------
    client = init_supabase_client()
    if client is None:
        st.error("Не ініціалізовано Supabase. Перевірте секцію [supabase] у st.secrets з SUPABASE_URL та SUPABASE_KEY.")
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
        col_y, col_m = st.columns(2)
        with col_y:
            years_sel = st.multiselect("Роки", options=fetch_year_options(client), default=[])
        with col_m:
            months_sel = st.multiselect("Місяці", options=fetch_month_options(), default=[])
        # Автовибір/відображення М.П. залежно від ролі користувача
        cur_user = get_current_user()
        cur_full_name = (cur_user.get('full_name') if isinstance(cur_user, dict) else None) or ""
        user_type = ((cur_user.get('type') if isinstance(cur_user, dict) else '') or '').lower()
        if cur_full_name and cur_full_name not in mp_options:
            mp_options = [cur_full_name] + mp_options
        if user_type == 'admin':
            # Адміністратор бачить і може редагувати фільтр
            default_admin = [cur_full_name] if cur_full_name else []
            selected_mps = st.multiselect(
                "М.П. (з profiles.full_name)",
                options=mp_options,
                default=default_admin,
            )
        else:
            # Не-адміністратор: приховуємо віджет, автоматично підставляємо власне full_name
            selected_mps = [cur_full_name] if cur_full_name else []
        submitted = st.form_submit_button("Отримати дані")

    # Обчислюємо ефективний вибір (порожній => нічого)
    effective_mps = selected_mps

    # Якщо натиснули кнопку — оновлюємо дані в сесії
    if submitted:
        if not years_sel or not months_sel:
            st.info("Оберіть хоча б один рік і один місяць, потім натисніть \"Отримати дані\".")
            st.stop()
        if not effective_mps:
            st.info("Оберіть хоча б одного М.П. і натисніть \"Отримати дані\".")
            st.stop()
        months_int = [k for k, v in MONTH_NAMES.items() if v in set(months_sel)]

        with st.spinner("Завантажую дані doctor_points..."):
            df_new = fetch_doctor_points_by_mp(
                client,
                effective_mps,
                year=years_sel,
                month=months_int,
            )
            if not df_new.empty:
                df_new = df_new.reset_index(drop=True)
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
    period_years = ", ".join(map(str, years_sel)) if years_sel else "—"
    period_months = ", ".join(months_sel) if months_sel else "—"
    st.success(
        f"Період: Роки [{period_years}] | Місяці [{period_months}] | М.П.: {len(st.session_state.dp_selection)} | Рядків: {len(df):,} × {df.shape[1]}"
    )
    col1, col2 = st.columns([4,2])
    with col1:
        # --- Діаграми з сирих даних (перед фільтрами) ---
        st.subheader("Діаграми за періодами")

        # Переконаємось, що є колонки year/month -> будуємо period
        df_ch = df.copy()
        if "year" in df_ch.columns and "month" in df_ch.columns:
            try:
                df_ch["year"] = df_ch["year"].astype(int)
                df_ch["month"] = df_ch["month"].astype(int)
            except Exception:
                pass
            df_ch["period"] = df_ch["year"].astype(str) + "-" + df_ch["month"].astype(int).astype(str).str.zfill(2)
        else:
            df_ch["period"] = "—"

        # Хелпер пошуку колонок
        def _first_present(cols: list[str], df_cols: list[str]) -> str | None:
            for c in cols:
                if c in df_cols:
                    return c
            return None

        product_col = _first_present(
        ["Препарат", "Найменування", "Назва препарату", "Найменування препарату", "Препарат (Найменування)"],
        df_ch.columns.tolist()
        )
        qty_col = _first_present(
        ["Кількість", "Кіл-сть", "К-сть", "Кіл-сть упаковок (рах. автомат.)", "Кіл-сть упаковок загальна", "Кількість, уп."],
        df_ch.columns.tolist()
        )
        city_col = "Місто" if "Місто" in df_ch.columns else None
        doctor_col = "П.І.Б. лікаря" if "П.І.Б. лікаря" in df_ch.columns else None
        spec_col = "Спеціалізація лікаря" if "Спеціалізація лікаря" in df_ch.columns else None
        points_col = "Сума Балів (поточ.міс.)" if "Сума Балів (поточ.міс.)" in df_ch.columns else None

        # Мапінг ПІБ лікаря → Спеціальність для ховерів на діаграмах
        spec_map = None
        if doctor_col and spec_col:
            # беремо першу унікальну спеціальність на лікаря
            spec_map = (
                df_ch[[doctor_col, spec_col]]
                .dropna(subset=[doctor_col])
                .drop_duplicates(subset=[doctor_col])
            )

        # 1) Діаграма загальної кількості препаратів (за періодами різні кольори)
        if product_col and qty_col:
            g1 = (df_ch.groupby([product_col, "period"], dropna=False)[qty_col]
                    .sum(min_count=1)
                    .reset_index()
                )
            fig1 = px.bar(
                g1,
                x=product_col,
                y=qty_col,
                color="period" if df_ch["period"].nunique() > 1 else None,
                barmode="group",
                title="Кількість препаратів по періодах"
            )
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("Для діаграми кількості препаратів не знайдено колонки з назвою препарату або кількістю.")

        # Спеціальності × кількості
        if spec_col and qty_col:
            g5 = (
                df_ch.groupby([spec_col, "period"], dropna=False)[qty_col]
                    .sum(min_count=1)
                    .reset_index()
                    .sort_values(qty_col, ascending=False)
            )
            st.markdown("**Спеціальності × кількості**")
            st.dataframe(g5.style.background_gradient(cmap="Blues"), use_container_width=True, hide_index=True)

        # Спеціальності × суми
        if spec_col and doctor_col and points_col:
            d6 = (
                df_ch.groupby([doctor_col, "period"], dropna=False)[points_col]
                    .max()
                    .reset_index()
                    .sort_values(points_col, ascending=False)
            )
            spec_map = (
                df_ch[[doctor_col, spec_col]]
                .dropna(subset=[doctor_col])
                .drop_duplicates()
            )
            d6 = d6.merge(spec_map, on=doctor_col, how="left")
            g6 = (
                d6.groupby([spec_col, "period"], dropna=False)[points_col]
                .sum(min_count=1)
                .reset_index()
                .sort_values(points_col, ascending=False)
            )
            st.markdown("**Спеціальності × сум**")
            st.dataframe(g6.style.background_gradient(cmap="Greens"), use_container_width=True, hide_index=True)
    with col2:
        # 2) ТОП-5 міст по кількостях
        fig2 = None
        if city_col and qty_col:
            g2 = (
                df_ch.groupby(city_col, dropna=False)[qty_col]
                    .sum(min_count=1)
                    .reset_index()
                    .sort_values(qty_col, ascending=False)
                    .head(5)
                    .sort_values(qty_col, ascending=True)
            )
            st.markdown("**ТОП-5 міст по кількостях**")
            st.dataframe(g2.style.background_gradient(cmap="Blues"), use_container_width=True, hide_index=True)

        # 3) ТОП-10 лікарів по кількостях (з відображенням спеціальності у hover)
        if doctor_col and qty_col:
            g3 = (
                df_ch.groupby(doctor_col, dropna=False)[qty_col]
                    .sum(min_count=1)
                    .reset_index()
                    .sort_values(qty_col, ascending=False)
                    .head(10)
                    
            )
            st.markdown("**ТОП-10 лікарів по кількостях**")
            st.dataframe(g3.style.background_gradient(cmap="Blues"), use_container_width=True, hide_index=True)


        # 4) ТОП-10 лікарів по сумах (дедупл. max на період) з відображенням спеціальності у hover
        if doctor_col and points_col:
            d4 = (
                df_ch.groupby([doctor_col, "period"], dropna=False)[points_col]
                    .max()
                    .reset_index()
            )
            g4 = (
                d4.groupby(doctor_col, dropna=False)[points_col]
                .sum(min_count=1)
                .reset_index()
                .sort_values(points_col, ascending=False)
                .head(10)
            )
            st.markdown("**ТОП-10 лікарів по сумах (дедупл. max на період)**")
            st.dataframe(g4.style.background_gradient(cmap="Greens"), use_container_width=True, hide_index=True)


    


    col3, col4 = st.columns([2,6])
    with col3:
        # --- Залежні фільтри (каскадні) ---
        st.subheader("Фільтри: Місто / ЛПЗ / П.І.Б. лікаря / Спеціалізація лікаря")

        # беремо актуальні дані з session_state
        if st.session_state.dp_df is None or st.session_state.dp_df.empty:
            st.info("Спочатку оберіть М.П., рік та місяць і натисніть 'Отримати дані'.")
            st.stop()

        df = st.session_state.dp_df.copy()

        required_cols = ["Місто", "ЛПЗ", "П.І.Б. лікаря", "Спеціалізація лікаря"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            st.warning("У даних відсутні колонки: " + ", ".join(missing))
            df_filtered = df
        else:
            # 1) Місто
            cities = sorted([x for x in df["Місто"].dropna().unique().tolist() if str(x).strip()])
            city_sel = st.multiselect("Місто", options=cities, default=[])
            df_step1 = df[df["Місто"].isin(city_sel)] if city_sel else df

            # 2) ЛПЗ (залежить від міста)
            lpz_opts = sorted([x for x in df_step1["ЛПЗ"].dropna().unique().tolist() if str(x).strip()])
            lpz_sel = st.multiselect("ЛПЗ", options=lpz_opts, default=[])
            df_step2 = df_step1[df_step1["ЛПЗ"].isin(lpz_sel)] if lpz_sel else df_step1

            # 3) П.І.Б. лікаря (залежить від міста та ЛПЗ)
            doc_opts = sorted([x for x in df_step2["П.І.Б. лікаря"].dropna().unique().tolist() if str(x).strip()])
            doc_sel = st.multiselect("ПІБ лікаря", options=doc_opts, default=[])
            df_step3 = df_step2[df_step2["П.І.Б. лікаря"].isin(doc_sel)] if doc_sel else df_step2

            # 4) Спеціалізація лікаря (залежить від попередніх)
            spec_opts = sorted([x for x in df_step3["Спеціалізація лікаря"].dropna().unique().tolist() if str(x).strip()])
            spec_sel = st.multiselect("Спеціалізація лікаря", options=spec_opts, default=[])
            df_filtered = df_step3[df_step3["Спеціалізація лікаря"].isin(spec_sel)] if spec_sel else df_step3

            # 5) Фільтр Препарати
            # Визначення drug_col так само як у підсумкових таблицях
            def _first_present(cols: list[str], df_cols: list[str]) -> str | None:
                for c in cols:
                    if c in df_cols:
                        return c
                return None
            drug_col = _first_present([
                "Препарат",
                "Найменування",
                "Назва препарату",
                "Найменування препарату",
                "Препарат (Найменування)",
            ], df_filtered.columns.tolist())
            if drug_col:
                drug_options = sorted([x for x in df_filtered[drug_col].dropna().unique().tolist() if str(x).strip()])
                drug_sel = st.multiselect("Препарат", options=drug_options, default=[])
                df_filtered = df_filtered[df_filtered[drug_col].isin(drug_sel)] if drug_sel else df_filtered

            st.caption(f"Відібрано рядків після фільтрів: {len(df_filtered):,}")
    with col4:

        # --- Підсумкові таблиці по місяцях ---
        st.subheader("Підсумки по місяцях")

        # Хелпер: знаходимо першу наявну колонку з переліку варіантів
        def _first_present(cols: list[str], df_cols: list[str]) -> str | None:
            for c in cols:
                if c in df_cols:
                    return c
            return None

        # Перевіряємо наявність year/month
        if ("year" not in df_filtered.columns) or ("month" not in df_filtered.columns):
            st.warning("Відсутні колонки year/month у даних — не можу побудувати підсумки по місяцях.")
        else:
            dfm = df_filtered.copy()
            # Період у форматі YYYY-MM
            try:
                dfm["year"] = dfm["year"].astype(int)
                dfm["month"] = dfm["month"].astype(int)
            except Exception:
                pass
            dfm["period"] = dfm["year"].astype(str) + "-" + dfm["month"].astype(int).astype(str).str.zfill(2)

            pt_qty_df = None
            pt_points_df = None
            pt_qty_total_max_df = None

            # Назва препарату: пробуємо кілька варіантів
            drug_col = _first_present([
                "Препарат",
                "Найменування",
                "Назва препарату",
                "Найменування препарату",
                "Препарат (Найменування)",
            ], dfm.columns.tolist())

            if not drug_col:
                st.warning("Не знайдено колонки з назвою препарату. Доступні колонки: " + ", ".join(dfm.columns))
            else:
                # 1) Препарати × Кількість по місяцях
                qty_col = _first_present([
                    "Кількість",
                    "Кіл-сть",
                    "К-сть",
                    "Кіл-сть упаковок (рах. автомат.)",
                    "Кіл-сть упаковок загальна",
                    "Кількість, уп.",
                ], dfm.columns.tolist())

                if qty_col:
                    doctor_col = "П.І.Б. лікаря"
                    if doctor_col not in dfm.columns:
                        st.warning("Не знайдено колонку 'П.І.Б. лікаря' для побудови підсумку за кількістю.")
                    else:
                        pt_qty = (
                            dfm.groupby([drug_col, doctor_col, "period"], dropna=False)[qty_col]
                            .sum(min_count=1)
                            .reset_index()
                            .pivot(index=[drug_col, doctor_col], columns="period", values=qty_col)
                            .fillna(0)
                        )
                        # на випадок нечислових dtype
                        pt_qty = pt_qty.apply(pd.to_numeric, errors="ignore").fillna(0)
                        try:
                            pt_qty = pt_qty.astype(int)
                        except Exception:
                            pass
                        pt_qty = pt_qty.reset_index()
                        # ПІБ на початок колонок
                        cols_order = [doctor_col, drug_col] + [c for c in pt_qty.columns if c not in [doctor_col, drug_col]]
                        pt_qty = pt_qty[cols_order]
                        pt_qty_df = pt_qty
                else:
                    st.info("Не знайдено колонку кількості (наприклад, 'Кількість' або 'Кіл-сть упаковок (рах. автомат.)').")

                # 2) Препарати × Сума Балів по місяцях
                points_col = "Сума Балів (поточ.міс.)"
                if points_col in dfm.columns:
                    doctor_col = "П.І.Б. лікаря"
                    if doctor_col not in dfm.columns:
                        st.warning("Не знайдено колонку 'П.І.Б. лікаря' для побудови підсумку за балами.")
                    else:
                        # Сума унікальних значень для кожного лікаря + період, потім сума по всіх лікарях
                        df_unique_points = dfm.groupby([doctor_col, "period"])[points_col].apply(lambda x: x.drop_duplicates().sum()).reset_index()
                        pt_points_df = df_unique_points.groupby("period")[points_col].sum().to_frame().T
                        pt_points_df = pt_points_df.apply(pd.to_numeric, errors="ignore").fillna(0)
                else:
                    st.info("У даних немає колонки 'Сума Балів (поточ.міс.)'.")

                # 3) Сума унікальних "Кіл-сть упаковок загальна" по лікарях та місяцях
                qty_total_col = "Кіл-сть упаковок загальна"
                if qty_total_col in dfm.columns and doctor_col in dfm.columns:
                    # Сума унікальних значень для кожного лікаря + період, потім сума по всіх лікарях
                    df_unique = dfm.groupby([doctor_col, "period"])[qty_total_col].apply(lambda x: x.drop_duplicates().sum()).reset_index()
                    pt_qty_total_max_df = df_unique.groupby("period")[qty_total_col].sum().to_frame().T
                    pt_qty_total_max_df = pt_qty_total_max_df.apply(pd.to_numeric, errors="ignore").fillna(0)
                else:
                    st.info("У даних немає колонки 'Кіл-сть упаковок загальна'.")

            # Відображення у двох колонках
            if (pt_qty_df is not None) or (pt_points_df is not None) or (pt_qty_total_max_df is not None):
                col_left, col_right = st.columns(2)
                with col_left:
                    if pt_qty_total_max_df is not None:
                        st.markdown("**Кіл-сть упаковок загальна по місяцях**")
                        st.dataframe(pt_qty_total_max_df, use_container_width=True)
                with col_right:
                    if pt_points_df is not None:
                        st.markdown("**Сума балів по місяцях**")
                        st.dataframe(pt_points_df, use_container_width=True)


    tab1, tab2 = st.tabs(["Зведена таблиця", "Таблиця"])
    with tab1:
        if pt_qty_df is not None:
            st.markdown("**Препарати × Кількість по місяцях (з ПІБ лікаря) – зведена таблиця**")
            
            # Перетворюємо pt_qty_df у long формат
            id_vars = ["П.І.Б. лікаря", "Препарат"] if "Препарат" in pt_qty_df.columns else ["П.І.Б. лікаря", pt_qty_df.columns[1]]
            value_vars = [c for c in pt_qty_df.columns if c not in id_vars]

            df_long = pt_qty_df.melt(
                id_vars=id_vars,
                value_vars=value_vars,
                var_name="Період",
                value_name="Кількість"
            )

            # Додаємо колонку М.П. для pivot
            df_long["М.П."] = df_long["П.І.Б. лікаря"].map(
                lambda x: dfm.loc[dfm["П.І.Б. лікаря"] == x, "М.П."].iloc[0] 
                if x in dfm["П.І.Б. лікаря"].values else ""
            )

            # Pivot: індекс = ПІБ + Період + М.П., колонки = Препарат
            pivot_df = df_long.pivot_table(
                index=["М.П.","П.І.Б. лікаря", "Період"],
                columns="Препарат",
                values="Кількість",
                aggfunc="sum",
                fill_value=0
            ).reset_index()

            st.dataframe(pivot_df, use_container_width=True, hide_index=True)
    with tab2:
        if pt_qty_df is not None:
                    st.markdown("**Препарати × Кількість по місяцях (з ПІБ лікаря)**")
                    st.dataframe(pt_qty_df, use_container_width=True)


def show_doctor_points_page():
    """
    Сторінка: 👨‍⚕️ Лікарі
    Обгортка для інтеграції з навігацією
    """
    show()