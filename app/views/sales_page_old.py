# app/views/sales_page.py
from __future__ import annotations

import os, sys
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk

# Optional online geocoding (wrapped in try/except)
try:
    from geopy.geocoders import Nominatim
    from geopy.extra.rate_limiter import RateLimiter
except Exception:  # geopy is optional
    Nominatim = None
    RateLimiter = None
 

# --- забезпечуємо імпорти виду "from app...." коли запускається як пакет Streamlit ---
PAGES_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(PAGES_DIR)
PROJECT_ROOT = os.path.dirname(APP_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# --- внутрішні модулі ---
 
from app.io import loader_sales as data_loader
from app.io.supabase_client import init_supabase_client
from app.data import processing_sales as data_processing
# Видаляємо імпорт навігації, оскільки вона вже є в основному файлі

from app.utils import UKRAINIAN_MONTHS

# --- Auth guard: require login before viewing this page ---
def _require_login():
    user = st.session_state.get('auth_user')
    if not user:
        st.warning("Будь ласка, увійдіть на головній сторінці, щоб переглядати цю сторінку.")
        st.stop()


def _ensure_numeric_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Приводить year, month, decade, quantity до числових типів (без падінь)."""
    out = df.copy()
    for col in ("year", "month", "decade"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "quantity" in out.columns:
        out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce").fillna(0)
    return out

# --- Cached wrappers and session-state helpers ---
@st.cache_data(show_spinner=False, ttl=1800)
def _cached_fetch_sales(region_name, territory, line, months):
    return data_loader.fetch_all_sales_data(
        region_name=region_name,
        territory=territory,
        line=line,
        months=months,
    )

@st.cache_data(show_spinner=False, ttl=1800)
def _cached_fetch_price(region_id: int, months: list[int]):
    return data_loader.fetch_price_data(region_id=region_id, months=months)

# --- Geocoding helpers (offline-first) ---
@st.cache_data(show_spinner=False, ttl=3600)
def _load_coords_catalog(path: str) -> pd.DataFrame:
    try:
        if os.path.exists(path):
            df = pd.read_csv(path)
            # normalize expected columns
            needed = {'addr_key','lat','lon','city','street','house_number'}
            for col in needed:
                if col not in df.columns:
                    df[col] = None
            return df
    except Exception:
        pass
    return pd.DataFrame(columns=['addr_key','lat','lon','city','street','house_number'])

def _save_coords_catalog(df: pd.DataFrame, path: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Avoid writing cached copy; write a fresh copy
        df.to_csv(path, index=False)
    except Exception as e:
        st.warning(f"Не вдалося зберегти довідник координат: {e}")

def _canonical_addr_key(city: str, street: str, house: str) -> str:
    city = str(city or '').strip().lower()
    street = str(street or '').strip().lower()
    house = str(house or '').strip().lower()
    return f"{city}|{street}|{house}"

def _attach_coords_from_catalog(df_addr: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    out = df_addr.copy()
    out['addr_key'] = out.apply(lambda r: _canonical_addr_key(r.get('__city__',''), r.get('__street__',''), r.get('__house__','')), axis=1)
    if not catalog.empty:
        merged = out.merge(catalog[['addr_key','lat','lon']], on='addr_key', how='left')
    else:
        merged = out
        merged['lat'] = None
        merged['lon'] = None
    return merged

def _online_geocode_missing(df_addr: pd.DataFrame, user_agent: str = 'sales-analytics-app') -> pd.DataFrame:
    """Try to geocode missing coordinates via Nominatim if geopy is available. Returns df with lat/lon filled where possible."""
    if Nominatim is None or RateLimiter is None:
        st.info("Бібліотека geopy не встановлена — онлайн-геокодування вимкнено.")
        return df_addr
    geolocator = Nominatim(user_agent=user_agent, timeout=10)
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
    df = df_addr.copy()
    # Build full address string: City, Street House, Ukraine
    def _addr_str(row):
        city = str(row.get('__city__','')).strip()
        street = str(row.get('__street__','')).strip()
        house = str(row.get('__house__','')).strip()
        pieces = [p for p in [city, f"{street} {house}".strip()] if p]
        base = ', '.join(pieces)
        # You can change country if needed
        return f"{base}, Ukraine" if base else None
    need = df[df['lat'].isna() | df['lon'].isna()].copy()
    results = []
    for _, r in need.iterrows():
        q = _addr_str(r)
        lat = None; lon = None
        if q:
            try:
                loc = geocode(q)
                if loc:
                    lat = loc.latitude
                    lon = loc.longitude
            except Exception:
                pass
        results.append({'addr_key': r['addr_key'], 'lat': lat, 'lon': lon})
    if results:
        res_df = pd.DataFrame(results)
        df = df.merge(res_df, on='addr_key', how='left', suffixes=('','_new'))
        df['lat'] = df['lat'].fillna(df['lat_new'])
        df['lon'] = df['lon'].fillna(df['lon_new'])
        df.drop(columns=[c for c in ['lat_new','lon_new'] if c in df.columns], inplace=True)
    return df

# --- session cache keys ---
    # --- helpers for URL state sync & normalization ---
_DEF_ALL = "(усі)"

def _norm_months_list(months):
    if not months:
        return []
    try:
        return sorted({int(m) for m in months})
    except Exception:
        clean = []
        for m in months:
            try:
                clean.append(int(m))
            except Exception:
                pass
        return sorted(set(clean))

def _months_to_param(months_int_list):
    return ",".join(f"{int(m):02d}" for m in _norm_months_list(months_int_list))

def _months_from_param(param_str: str):
    if not param_str:
        return []
    parts = [p.strip() for p in str(param_str).split(',') if p.strip()]
    out = []
    for p in parts:
        try:
            out.append(int(p))
        except Exception:
            pass
    return _norm_months_list(out)

def _read_query_params_into_state():
    ss = st.session_state
    qp = st.query_params

    apply_from_url = not ss.get('sales_submit_once', False) and not ss.get('filters_dirty', False)

    def _maybe_apply(key, url_val, default_val):
        if not apply_from_url:
            return
        if key not in ss or ss.get(key) in (None, default_val, []):
            ss[key] = (url_val if (url_val is not None and url_val != '') else default_val)

    if 'reg' in qp:
        _maybe_apply('sales_region', qp.get('reg'), _DEF_ALL)
    if 'terr' in qp:
        _maybe_apply('sales_territory_name', qp.get('terr'), _DEF_ALL)
    if 'line' in qp:
        _maybe_apply('sales_line', qp.get('line'), _DEF_ALL)
    if 'months' in qp:
        if apply_from_url and ('sales_months' not in ss or ss.get('sales_months') in (None, [],)):
            ss['sales_months'] = _months_from_param(qp.get('months'))


# --- Helper: Restore filters from memory if URL is empty ---
def _ensure_filters_from_memory_if_url_empty():
    """If user navigates to this page without query params, prefill filters from
    last_submitted_filters or from _shared_sales_filters so sidebar shows
    consistent values, but do NOT auto-fetch."""
    ss = st.session_state
    qp = st.query_params
    # If there are no relevant query params at all, try restoring from memory
    if not any(k in qp for k in ('reg','terr','line','months')):
        src = ss.get('last_submitted_filters')
        if not src:
            # fallback to the shared dataset's filters if available
            sh = ss.get('_shared_sales_filters')
            if isinstance(sh, dict):
                src = {
                    'region_name': sh.get('region_name'),
                    'territory_name': sh.get('territory'),
                    'line': sh.get('line'),
                    'months_int': [int(m) for m in (sh.get('months') or []) if str(m).isdigit()],
                }
        if src:
            ss['sales_region'] = src.get('region_name') or _DEF_ALL
            ss['sales_territory_name'] = src.get('territory_name') or _DEF_ALL
            ss['sales_line'] = src.get('line') or _DEF_ALL
            # Keep months as ints in state; widgets will sanitize further
            ss['sales_months'] = _norm_months_list(src.get('months_int') or ss.get('sales_months', []))
            # Reflect in URL for deep-linking across pages
            _write_state_to_query_params(
                ss['sales_region'], ss['sales_territory_name'], ss['sales_line'], ss['sales_months'], False
            )

def _write_state_to_query_params(sel_region, sel_territory_name, sel_line, sel_months_int, submitted: bool):
    st.query_params.update({
        'reg': sel_region or _DEF_ALL,
        'terr': sel_territory_name or _DEF_ALL,
        'line': sel_line or _DEF_ALL,
        'months': _months_to_param(sel_months_int),
    })

def _make_sales_key(region_name, territory, line, months):
    return (
        region_name or _DEF_ALL,
        territory or "Всі",
        line or "Всі",
        tuple(sorted(months)) if months else None,
    )

def _get_session_cache():
    if "_sales_session_cache" not in st.session_state:
        st.session_state["_sales_session_cache"] = {}
    if "_price_session_cache" not in st.session_state:
        st.session_state["_price_session_cache"] = {}
    return st.session_state["_sales_session_cache"], st.session_state["_price_session_cache"]


def show():
    """
    Сторінка: 📊 Аналіз продажів
    Очікує, що у st.session_state.sales_df_full вже лежать дані продажів (наприклад, з окремої вхідної сторінки/фільтрів).
    Також потребує st.session_state.selected_region_id (для завантаження прайсів).
    """
    _require_login()
    st.set_page_config(layout="wide")
    st.title("📊 Аналіз продажів")
    client = init_supabase_client()
    if client is None:
        st.error("Supabase не ініціалізовано. Перевірте st.secrets['SUPABASE_URL'|'SUPABASE_KEY'].")
        st.stop()

    @st.cache_data(show_spinner=False, ttl=1800)
    def _fetch_regions(_client):
        try:
            rows = _client.table("region").select("id,name").order("name").execute().data or []
            return [{"id": r.get("id"), "name": r.get("name")}] if False else [
                {"id": r.get("id"), "name": r.get("name")}
                for r in rows
                if r.get("id") and r.get("name")
            ]
        except Exception:
            return []

    @st.cache_data(show_spinner=False, ttl=1800)
    def _fetch_territories(_client, region_id: int | None):
        """Повертає список територій (name, technical_name), опційно відфільтрованих за region_id."""
        try:
            q = _client.table("territory").select("name,technical_name,region_id").order("name")
            if region_id:
                q = q.eq("region_id", region_id)
            rows = q.execute().data or []
            territories = []
            for r in rows:
                n = (r.get("name") or "").strip()
                t = (r.get("technical_name") or "").strip()
                if n and t:
                    territories.append({"name": n, "technical_name": t, "region_id": r.get("region_id")})
            return territories
        except Exception:
            return []


    # --- persistent filter state ---
    ss = st.session_state
    if 'sales_region' not in ss:
        ss['sales_region'] = _DEF_ALL
    if 'sales_territory_name' not in ss:
        ss['sales_territory_name'] = _DEF_ALL
    if 'sales_territory_technical' not in ss:
        ss['sales_territory_technical'] = None
    if 'sales_line' not in ss:
        ss['sales_line'] = _DEF_ALL
    if 'sales_months' not in ss:
        ss['sales_months'] = []
    if 'sales_submit_once' not in ss:
        ss['sales_submit_once'] = False
    ss.setdefault('filters_dirty', False)
    ss.setdefault('last_submitted_filters', None)
    # Do NOT reset on each rerun — preserve once the user has clicked "Отримати дані"
    # (Removing the forced reset prevents data loss on other button clicks on the page.)

    # --- read URL params into state before widgets ---
    _read_query_params_into_state()
    _ensure_filters_from_memory_if_url_empty()

    def _mark_filters_dirty():
        st.session_state['filters_dirty'] = True

    with st.sidebar:
        st.markdown("### Фільтри")
        regions = _fetch_regions(client)
        region_names = [r["name"] for r in regions]
        # Preserve previously selected region if it is not in the freshly fetched list
        prev_region = ss.get('sales_region', _DEF_ALL)
        if prev_region and prev_region != _DEF_ALL and prev_region not in region_names:
            region_names = [prev_region] + region_names
        st.selectbox("Регіон", [_DEF_ALL] + region_names, key="sales_region", on_change=_mark_filters_dirty)

        sel_region_id = None
        if ss['sales_region'] and ss['sales_region'] != _DEF_ALL:
            match_r = next((r for r in regions if r["name"] == ss['sales_region']), None)
            sel_region_id = match_r["id"] if match_r else None

        territories = _fetch_territories(client, sel_region_id)
        territory_names = [t["name"] for t in territories]
        prev_terr = ss.get('sales_territory_name', _DEF_ALL)
        terr_choices = [_DEF_ALL] + territory_names
        if prev_terr and prev_terr != _DEF_ALL and prev_terr not in terr_choices:
            terr_choices = [prev_terr] + terr_choices[1:]
        st.selectbox("Територія", terr_choices, key="sales_territory_name", on_change=_mark_filters_dirty)

        # update technical name in session state after selection
        ss['sales_territory_technical'] = None
        if ss['sales_territory_name'] and ss['sales_territory_name'] != _DEF_ALL:
            match_t = next((t for t in territories if t["name"] == ss['sales_territory_name']), None)
            ss['sales_territory_technical'] = match_t["technical_name"] if match_t else None

        # Лінія продукту — статичний список
        lines_all = ["Лінія 1", "Лінія 2"]
        prev_line = ss.get('sales_line', _DEF_ALL)
        line_choices = [_DEF_ALL] + lines_all
        if prev_line and prev_line != _DEF_ALL and prev_line not in line_choices:
            line_choices = [prev_line] + line_choices[1:]
        st.selectbox(
            "Лінія продукту",
            line_choices,
            key="sales_line",
            on_change=_mark_filters_dirty,
        )

        # Місяці
        month_keys = list(UKRAINIAN_MONTHS.keys())
        # sanitize any pre-set value from session/query params to valid options
        ss['sales_months'] = [m for m in ss.get('sales_months', []) if m in month_keys]

        st.multiselect(
            "Місяці",
            options=month_keys,
            format_func=lambda m: UKRAINIAN_MONTHS.get(m, str(m)),
            key="sales_months",
            on_change=_mark_filters_dirty,
        )

        if st.button("Отримати дані", type="primary", use_container_width=True):
            ss['sales_submit_once'] = True
            ss['filters_dirty'] = False
            # snapshot of filters at submission time (normalized ints for months)
            ss['last_submitted_filters'] = {
                'region_name': (None if (ss['sales_region'] == _DEF_ALL or not ss['sales_region']) else ss['sales_region']),
                'territory_name': ss['sales_territory_name'],
                'territory_technical': ss.get('sales_territory_technical'),
                'line': ("Всі" if (ss['sales_line'] == _DEF_ALL or not ss['sales_line']) else ss['sales_line']),
                'months_int': _norm_months_list(ss['sales_months']),
            }
            _write_state_to_query_params(
                ss['sales_region'],
                ss['sales_territory_name'],
                ss['sales_line'],
                ss['sales_months'],
                True,
            )

    if not ss['sales_submit_once']:
        st.info("Оберіть фільтри зліва і натисніть \"Отримати дані\".")
        st.stop()

    # формуємо параметри для запиту з session_state
    sel_region_name = ss['sales_region']
    sel_territory_name = ss['sales_territory_name']
    sel_territory_technical = ss['sales_territory_technical']
    sel_line = ss['sales_line']
    sel_months_int = _norm_months_list(ss['sales_months'])

    region_param = None if (not sel_region_name or sel_region_name == _DEF_ALL) else sel_region_name
    territory_param = None if (not sel_territory_technical) else sel_territory_technical
    line_param = "Всі" if (not sel_line or sel_line == _DEF_ALL) else sel_line
    months_param = ([f"{int(m):02d}" for m in sel_months_int] if sel_months_int else None)

    # Do not auto-fetch if filters were changed after last submit
    cur_snapshot = {
        'region_name': region_param,
        'territory_name': ss['sales_territory_name'],
        'territory_technical': ss.get('sales_territory_technical'),
        'line': line_param,
        'months_int': _norm_months_list(ss['sales_months']),
    }
    if (not ss.get('sales_submit_once')) or ss.get('filters_dirty') or (ss.get('last_submitted_filters') != cur_snapshot):
        # Allow viewing preloaded shared dataset if it matches current filters; otherwise require explicit click
        shared_df = st.session_state.get('_shared_sales_df')
        shared_filters = st.session_state.get('_shared_sales_filters')
        if (
            shared_df is not None and isinstance(shared_filters, dict) and
            shared_filters.get('region_name') == region_param and
            shared_filters.get('territory') == (territory_param or "Всі") and
            shared_filters.get('line') == line_param and
            (shared_filters.get('months') or None) == (months_param or None)
        ):
            df_loaded = shared_df
            st.caption("Дані взяті зі спільного кешу (без повторного запиту до БД). Натисніть \"Отримати дані\" для перезавантаження.")
        else:
            st.info('Фільтри змінені. Натисніть "Отримати дані" для застосування.')
            st.stop()
    else:
        with st.spinner("Завантажую дані продажів із Supabase..."):
            sales_cache, price_cache = _get_session_cache()
            sales_key = _make_sales_key(region_param, territory_param or "Всі", line_param, months_param)
            if sales_key in sales_cache:
                df_loaded = sales_cache[sales_key]
            else:
                df_loaded = _cached_fetch_sales(
                    region_param,
                    territory_param or "Всі",
                    line_param,
                    months_param,
                )
                sales_cache[sales_key] = df_loaded

        if df_loaded is None or df_loaded.empty:
            st.warning("Дані не знайдені для обраних фільтрів.")
            st.stop()

        st.success(f"Завантажено {len(df_loaded):,} рядків.")
        ss = st.session_state
        ss['_shared_sales_df'] = df_loaded
        ss['_shared_sales_filters'] = {
            'region_name': region_param,
            'territory': territory_param or "Всі",
            'line': line_param,
            'months': months_param,
        }
    # Підготовка до розрахунків (revenue, прогноз)
    df_work = df_loaded.copy()
    # гарантуємо month_int
    if 'month_int' not in df_work.columns:
        df_work['month_int'] = pd.to_numeric(df_work.get('month'), errors='coerce').astype('Int64')
    # уніфікуємо типи
    for col in ("year", "decade"):
        if col in df_work.columns:
            df_work[col] = pd.to_numeric(df_work[col], errors='coerce').astype('Int64')
    # нормалізація назв продуктів для діаграм: прибрати префіксні коди/символи (напр., "08 ")
    if 'product_name' in df_work.columns:
        df_work['product_name_clean'] = (
            df_work['product_name']
            .astype(str)
            .str.replace(r'^\s*[\d\W_]+', '', regex=True)
            .str.strip()
        )

    # тягнемо прайси для всіх присутніх у даних місяців (для таблиці доходу по продуктах)
    all_months_int = df_work['month_int'].dropna().astype(int).unique().tolist()
    # Session-state aware cached fetch for price_df_all
    if all_months_int and sel_region_id:
        _, price_cache = _get_session_cache()
        price_key_all = (sel_region_id, tuple(sorted(all_months_int)))
        if price_key_all in price_cache:
            price_df_all = price_cache[price_key_all]
        else:
            price_df_all = _cached_fetch_price(sel_region_id, all_months_int)
            price_cache[price_key_all] = price_df_all
    else:
        price_df_all = pd.DataFrame()

    df_with_revenue = df_work.copy()
    if not price_df_all.empty:
        df_with_revenue = pd.merge(
            df_with_revenue,
            price_df_all,
            left_on=['product_name', 'month_int'],
            right_on=['product_name', 'month_int'],
            how='left'
        )
        df_with_revenue['revenue'] = df_with_revenue['quantity'] * df_with_revenue['price']
    else:
        df_with_revenue['revenue'] = 0.0

    # --- Використовуємо лише останню доступну декаду останнього місяця ---
    df_latest_decade = df_work.copy()
    last_decade = None
    cur_year = None
    cur_month = None
    if {'year','month_int','decade'}.issubset(df_work.columns):
        df_dec = df_work.dropna(subset=['year','month_int','decade']).copy()
        if not df_dec.empty:
            max_dec_per = df_dec.groupby(['year','month_int'])['decade'].transform('max')
            latest_per_month = df_dec[df_dec['decade'] == max_dec_per].copy()
            latest_pair = (
                latest_per_month[['year','month_int']]
                .drop_duplicates()
                .sort_values(['year','month_int'])
                .iloc[-1]
            )
            cur_year = int(latest_pair['year'])
            cur_month = int(latest_pair['month_int'])
            last_decade = int(
                latest_per_month[
                    (latest_per_month['year'] == cur_year) & (latest_per_month['month_int'] == cur_month)
                ]['decade'].max()
            )
            df_latest_decade = latest_per_month[
                (latest_per_month['year'] == cur_year) & (latest_per_month['month_int'] == cur_month)
            ].copy()

    # Рахуємо revenue лише для цього зрізу (останній місяць/остання декада)
    df_latest_with_revenue = df_latest_decade.copy()
    price_df_cur = pd.DataFrame()
    if cur_month is not None and sel_region_id:
        _, price_cache = _get_session_cache()
        price_key_cur = (sel_region_id, (cur_month,))
        if price_key_cur in price_cache:
            price_df_cur = price_cache[price_key_cur]
        else:
            price_df_cur = _cached_fetch_price(sel_region_id, [cur_month])
            price_cache[price_key_cur] = price_df_cur
        if not price_df_cur.empty:
            df_latest_with_revenue = pd.merge(
                df_latest_with_revenue,
                price_df_cur,
                left_on=['product_name','month_int'],
                right_on=['product_name','month_int'],
                how='left'
            )
            df_latest_with_revenue['revenue'] = df_latest_with_revenue['quantity'] * df_latest_with_revenue['price']
        else:
            df_latest_with_revenue['revenue'] = 0.0
    elif 'revenue' not in df_latest_with_revenue.columns:
        df_latest_with_revenue['revenue'] = 0.0

    

    # === KPI: один рядок над усім контентом ===
    # Загальна кількість (остання декада)
    if not df_latest_decade.empty:
        total_quantity = int(pd.to_numeric(df_latest_decade.get('quantity', pd.Series(dtype=float)), errors='coerce').fillna(0).sum())
    else:
        total_quantity = 0
    # Загальна сума (остання декада)
    if not df_latest_with_revenue.empty and 'revenue' in df_latest_with_revenue.columns:
        total_revenue_sum = float(pd.to_numeric(df_latest_with_revenue['revenue'], errors='coerce').fillna(0).sum())
    else:
        total_revenue_sum = 0.0
    # Показники за весь обраний період
    df_period_top = df_with_revenue.copy() if 'df_with_revenue' in locals() else df_work.copy()
    if 'revenue' not in df_period_top.columns:
        df_period_top['revenue'] = 0.0
    total_qty_period_top = float(pd.to_numeric(df_period_top.get('quantity', pd.Series(dtype=float)), errors='coerce').fillna(0).sum())
    total_rev_period_top = float(pd.to_numeric(df_period_top.get('revenue', pd.Series(dtype=float)), errors='coerce').fillna(0).sum())
    avg_check_top = (total_rev_period_top / total_qty_period_top) if total_qty_period_top > 0 else 0.0
    # Унікальні клієнти = унікальні адреси (city + street + house_number)
    client_cols_pref = ['client', 'full_address_processed', 'pharmacy', 'client_name']
    client_col_top = next((c for c in client_cols_pref if c in df_period_top.columns), None)

    uniq_clients_top = 0
    if {'city','street','house_number'}.issubset(df_period_top.columns):
        addr_series = (
            df_period_top['city'].fillna('').astype(str).str.strip() + '|' +
            df_period_top['street'].fillna('').astype(str).str.strip() + '|' +
            df_period_top['house_number'].fillna('').astype(str).str.strip()
        )
        uniq_clients_top = int(addr_series.nunique())
    elif 'full_address_processed' in df_period_top.columns:
        uniq_clients_top = int(df_period_top['full_address_processed'].astype(str).str.strip().nunique())
    elif 'address' in df_period_top.columns:
        uniq_clients_top = int(df_period_top['address'].astype(str).str.strip().nunique())
    elif client_col_top:
        uniq_clients_top = int(df_period_top[client_col_top].astype(str).str.strip().nunique())
    else:
        uniq_clients_top = 0

    avg_qty_per_client_top = (total_qty_period_top / uniq_clients_top) if uniq_clients_top > 0 else 0.0

    kpi_row = st.columns(5)
    with kpi_row[0]:
        st.metric("Загальна кількість (ост. декада)", f"{total_quantity:,}")
    with kpi_row[1]:
        st.metric("Загальна сума (ост. декада)", f"{total_revenue_sum:,.2f} грн")
    with kpi_row[2]:
        st.metric("Середній чек (період)", f"{avg_check_top:,.2f} грн")
    with kpi_row[3]:
        st.metric("Сер. к-сть/клієнта (період)", f"{avg_qty_per_client_top:,.2f}")
    with kpi_row[4]:
        st.metric("Унікальних клієнтів (період)", f"{uniq_clients_top:,}")

    # 1-й рядок: 3 колонки
    col1, col2 = st.columns([2,5])

    # 1) Комбінована таблиця по продуктах: кількість і сума (алфавітне сортування)
    with col1:
        st.subheader("Кількість та сума по продуктах")
       
        # вибираємо колонку продукту (очищену, якщо доступна)
        prod_col = 'product_name_clean' if 'product_name_clean' in df_latest_decade.columns else 'product_name'

        # кількість
        qty_by_product = (
            df_latest_decade.groupby(prod_col, as_index=False)['quantity']
            .sum()
            .rename(columns={'quantity': 'К-сть'})
        )

        # сума
        if 'revenue' in df_latest_with_revenue.columns:
            rev_by_product = (
                df_latest_with_revenue.groupby(prod_col, as_index=False)['revenue']
                .sum()
                .rename(columns={'revenue': 'Сума'})
            )
        else:
            # якщо немає цін — сума = 0
            rev_by_product = qty_by_product[[prod_col]].copy()
            rev_by_product['Сума'] = 0.0

        # обʼєднуємо
        combined_prod = (
            pd.merge(qty_by_product, rev_by_product, on=prod_col, how='left')
            .rename(columns={prod_col: 'Препарат'})
            .fillna({'Сума': 0.0})
            .sort_values('К-сть', ascending=False)
        )

        combined_style = (
            combined_prod.style
            .format({'К-сть': '{:,.0f}', 'Сума': '{:,.2f} грн'})
            .background_gradient(cmap='Blues', subset=['К-сть'])
            .background_gradient(cmap='Greens', subset=['Сума'])
        )
        st.dataframe(combined_style, use_container_width=True, hide_index=True)

        # Прогноз до кінця місяця (показуємо лише якщо остання декада < 30)
        df_for_overview = df_work.copy()
        if {'year','month_int','decade'}.issubset(df_for_overview.columns):
            # визначаємо останній (year, month)
            # фільтр на максимальну декаду в кожному (year, month)
            max_dec_per = df_for_overview.groupby(['year','month_int'])['decade'].transform('max')
            latest_per_month = df_for_overview[df_for_overview['decade'] == max_dec_per].copy()
            # вибираємо найсвіжіший місяць
            latest_per_month = latest_per_month.dropna(subset=['year','month_int'])
            if not latest_per_month.empty:
                latest_pair = (
                    latest_per_month[['year','month_int']]
                    .drop_duplicates()
                    .sort_values(['year','month_int'])
                    .iloc[-1]
                )
                cur_year = int(latest_pair['year'])
                cur_month = int(latest_pair['month_int'])
                df_latest = latest_per_month[
                    (latest_per_month['year'] == cur_year) & (latest_per_month['month_int'] == cur_month)
                ].copy()

                # мердж з цінами лише для поточного місяця
                price_df_cur = pd.DataFrame()
                if sel_region_id:
                    _, price_cache = _get_session_cache()
                    price_key_cur = (sel_region_id, (cur_month,))
                    if price_key_cur in price_cache:
                        price_df_cur = price_cache[price_key_cur]
                    else:
                        price_df_cur = _cached_fetch_price(sel_region_id, [cur_month])
                        price_cache[price_key_cur] = price_df_cur
                if not price_df_cur.empty:
                    df_latest = pd.merge(
                        df_latest,
                        price_df_cur,
                        left_on=['product_name','month_int'],
                        right_on=['product_name','month_int'],
                        how='left'
                    )
                    df_latest['revenue'] = df_latest['quantity'] * df_latest['price']
                else:
                    df_latest['revenue'] = 0.0

                # визначаємо останню декаду та показуємо блок лише якщо < 30
                try:
                    last_decade = int(df_latest['decade'].max()) if not df_latest.empty else 0
                except Exception:
                    last_decade = 0

                if last_decade < 30:
                    forecast_data = data_processing.calculate_forecast_with_bootstrap(
                        df_for_current_month=df_latest[['revenue','quantity','decade','product_name']].copy(),
                        last_decade=last_decade,
                        year=cur_year,
                        month=cur_month,
                    )
                    if forecast_data:
                        st.subheader("Прогноз до кінця місяця")
                        # KPI: прогноз доходу (точковий)
                        st.metric(
                            "Прогноз доходу (до кінця місяця)",
                            f"{forecast_data['point_forecast_revenue']:,.2f} грн",
                            help=f"Остання декада для розрахунку: {last_decade}"
                        )
                        st.dataframe(
                            pd.DataFrame(
                                {
                                    'Показник': ['Прогноз, грн', '95% Low', '95% High', 'Робочі дні пройшли', 'Лишилось робочих днів'],
                                    'Значення': [
                                        f"{forecast_data['point_forecast_revenue']:,.2f}",
                                        f"{forecast_data['conf_interval_revenue'][0]:,.0f}",
                                        f"{forecast_data['conf_interval_revenue'][1]:,.0f}",
                                        forecast_data['workdays_passed'],
                                        forecast_data['workdays_left'],
                                    ],
                                }
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.info("Недостатньо даних для прогнозу.")
                else:
                    # Ретроспективні прогнози: показати, що б ми прогнозували на 10-й та 20-й декадах, і порівняти з фактом
                    # Побудуємо зріз всього поточного місяця (усі декади), з цінами
                    df_month_all = df_for_overview[
                        (df_for_overview['year'] == cur_year) & (df_for_overview['month_int'] == cur_month)
                    ].copy()
                    if not price_df_cur.empty:
                        df_month_all = pd.merge(
                            df_month_all,
                            price_df_cur,
                            left_on=['product_name','month_int'],
                            right_on=['product_name','month_int'],
                            how='left'
                        )
                        df_month_all['revenue'] = df_month_all['quantity'] * df_month_all['price']
                    else:
                        if 'revenue' not in df_month_all.columns:
                            df_month_all['revenue'] = 0.0

                    # Факт = сума доходу останньої декади місяця (30 або максимальна)
                    max_dec_m = int(pd.to_numeric(df_month_all['decade'], errors='coerce').max()) if not df_month_all.empty else 30
                    fact_revenue = float(pd.to_numeric(df_month_all[df_month_all['decade'] == max_dec_m]['revenue'], errors='coerce').fillna(0).sum())

                    def _compute_forecast_at(dec_cut: int):
                        df_cut = df_month_all[pd.to_numeric(df_month_all['decade'], errors='coerce') <= dec_cut][['revenue','quantity','decade','product_name']].copy()
                        if df_cut.empty:
                            return None
                        try:
                            return data_processing.calculate_forecast_with_bootstrap(
                                df_for_current_month=df_cut,
                                last_decade=dec_cut,
                                year=cur_year,
                                month=cur_month,
                            )
                        except Exception:
                            return None

                    f10 = _compute_forecast_at(10)
                    f20 = _compute_forecast_at(20)

                    rows = []
                    if f10:
                        err10 = f10['point_forecast_revenue'] - fact_revenue
                        mape10 = (abs(err10) / fact_revenue * 100) if fact_revenue else None
                        rows.append({
                            'Стан (декада)': '10',
                            'Прогноз, грн': f10['point_forecast_revenue'],
                            '95% Low': f10['conf_interval_revenue'][0],
                            '95% High': f10['conf_interval_revenue'][1],
                            'Факт (грн)': fact_revenue,
                            'Похибка, грн': err10,
                            'MAPE, %': mape10,
                        })
                    if f20:
                        err20 = f20['point_forecast_revenue'] - fact_revenue
                        mape20 = (abs(err20) / fact_revenue * 100) if fact_revenue else None
                        rows.append({
                            'Стан (декада)': '20',
                            'Прогноз, грн': f20['point_forecast_revenue'],
                            '95% Low': f20['conf_interval_revenue'][0],
                            '95% High': f20['conf_interval_revenue'][1],
                            'Факт (грн)': fact_revenue,
                            'Похибка, грн': err20,
                            'MAPE, %': mape20,
                        })

                    st.subheader("Ретроспективні прогнози (10/20 декада) та точність")
                    if rows:
                        df_backtest = pd.DataFrame(rows)
                        # Безпечне форматування числових колонок (None/NaN не ламають стиль)
                        num_cols_bt = ['Прогноз, грн', '95% Low', '95% High', 'Факт (грн)', 'Похибка, грн', 'MAPE, %']
                        for c in num_cols_bt:
                            if c in df_backtest.columns:
                                df_backtest[c] = pd.to_numeric(df_backtest[c], errors='coerce')

                        _fmt2 = lambda x: "" if pd.isna(x) else f"{x:,.2f}"

                        styler_bt = (
                            df_backtest.style
                                .format({
                                    'Прогноз, грн': _fmt2,
                                    '95% Low': _fmt2,
                                    '95% High': _fmt2,
                                    'Факт (грн)': _fmt2,
                                    'Похибка, грн': _fmt2,
                                    'MAPE, %': _fmt2,
                                })
                                .background_gradient(cmap='Greens', subset=['Факт (грн)'] if 'Факт (грн)' in df_backtest.columns else None)
                                .background_gradient(cmap='Blues', subset=['Прогноз, грн'] if 'Прогноз, грн' in df_backtest.columns else None)
                                .background_gradient(cmap='Reds', subset=['Похибка, грн'] if 'Похибка, грн' in df_backtest.columns else None)
                        )
                        st.dataframe(
                            styler_bt,
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.info("Немає достатньо даних для ретроспективних прогнозів (10/20 декада).")
            else:
                st.info("Немає даних для визначення останньої декади.")
        else:
            st.info("Немає колонок year/month/decade для прогнозу.")

        st.subheader("ТОП-10 аптек")
        _df_for_clients = df_with_revenue.copy() if 'df_with_revenue' in locals() else df_work.copy()
        if 'revenue' not in _df_for_clients.columns:
            _df_for_clients['revenue'] = 0.0

        # ЄДИНИЙ канонічний ключ адреси: city|street|house_number (нижній регістр, трім)
        if {'city','street','house_number'}.issubset(_df_for_clients.columns):
            tmp = _df_for_clients.copy()
            tmp['__city__'] = tmp['city'].fillna('').astype(str).str.strip()
            tmp['__street__'] = tmp['street'].fillna('').astype(str).str.strip()
            tmp['__house__'] = tmp['house_number'].fillna('').astype(str).str.strip()
            tmp['__addr_key__'] = (
                tmp['__city__'].str.lower() + '|' + tmp['__street__'].str.lower() + '|' + tmp['__house__'].str.lower()
            )
            # Відображення
            tmp['__city_disp__'] = tmp['__city__']
            tmp['__addr_disp__'] = (tmp['__street__'] + ' ' + tmp['__house__']).str.strip()
            # Назва аптеки: беремо new_client, якщо є; інакше client/pharmacy
            name_cols = [c for c in ['new_client','client','pharmacy','client_name'] if c in tmp.columns]
            if name_cols:
                tmp['__client_name__'] = tmp[name_cols[0]].astype(str).fillna('').str.strip()
            else:
                tmp['__client_name__'] = ''
        else:
            # fallback: пробуємо готові адресні колонки
            tmp = _df_for_clients.copy()
            if 'full_address_processed' in tmp.columns:
                tmp['__addr_key__'] = tmp['full_address_processed'].astype(str).fillna('').str.strip().str.lower()
                tmp['__addr_disp__'] = tmp['full_address_processed'].astype(str).fillna('').str.strip()
            elif 'address' in tmp.columns:
                tmp['__addr_key__'] = tmp['address'].astype(str).fillna('').str.strip().str.lower()
                tmp['__addr_disp__'] = tmp['address'].astype(str).fillna('').str.strip()
            else:
                tmp['__addr_key__'] = ''
                tmp['__addr_disp__'] = ''
            tmp['__city_disp__'] = tmp.get('city', pd.Series('', index=tmp.index)).astype(str).fillna('').str.strip()
            name_cols = [c for c in ['new_client','client','pharmacy','client_name'] if c in tmp.columns]
            tmp['__client_name__'] = tmp[name_cols[0]].astype(str).fillna('').str.strip() if name_cols else ''

        if (tmp['__addr_key__'] == '').all():
            st.info("Не вдалось сформувати унікальну адресу для агрегації аптек.")
        else:
            # Агрегація **лише за адресним ключем**
            grp = tmp.groupby('__addr_key__', as_index=False).agg(
                Сума=('revenue','sum'),
                **{'К-сть': ('quantity','sum')}
            ).sort_values('Сума', ascending=False)

            # Додати відображення: місто, адреса, аптека (перше непорожнє значення)
            disp = tmp[['__addr_key__','__city_disp__','__addr_disp__','__client_name__']].copy()
            disp = disp.groupby('__addr_key__', as_index=False).agg(
                Місто=('__city_disp__', lambda s: next((x for x in s if str(x).strip()), '')),
                Адреса=('__addr_disp__', lambda s: next((x for x in s if str(x).strip()), '')),
                Аптека=('__client_name__', lambda s: next((x for x in s if str(x).strip()), '')),
            )
            top_join = grp.merge(disp, on='__addr_key__', how='left')

            # Таб «За виручкою» та «За кількістю», head(10)
            tab_cli_rev, tab_cli_qty = st.tabs(["За виручкою", "За кількістю"])
            with tab_cli_rev:
                df_rev10 = top_join.sort_values('Сума', ascending=False).head(10)
                # Порядок колонок: метрика попереду
                cols_rev = ['Сума','Аптека','Місто','Адреса'] + [c for c in df_rev10.columns if c not in ['__addr_key__','Сума','К-сть','Аптека','Місто','Адреса']]
                st.dataframe(
                    df_rev10[cols_rev].style
                        .format({'Сума':'{:,.2f} грн'})
                        .background_gradient(cmap='Greens', subset=['Сума']),
                    use_container_width=True, hide_index=True
                )
            with tab_cli_qty:
                df_qty10 = top_join.sort_values('К-сть', ascending=False).head(10)
                cols_qty = ['К-сть','Аптека','Місто','Адреса'] + [c for c in df_qty10.columns if c not in ['__addr_key__','Сума','К-сть','Аптека','Місто','Адреса']]
                st.dataframe(
                    df_qty10[cols_qty].style
                        .format({'К-сть':'{:,.0f}'})
                        .background_gradient(cmap='Blues', subset=['К-сть']),
                    use_container_width=True, hide_index=True
                )






    with col2:
        main_container = st.container()

        with main_container:
            # Діаграми в табах
            tab_qty, tab_city, tab_trend, tab_bcg = st.tabs(["Кількість по продуктах", "Виручка по містах (+ к-сть)", "Тренд по декадах ", "BCG"])

            with tab_qty:
                # Кількість по продуктах
                # Якщо обрано кілька місяців — показати згруповані стовпчики по кожному місяцю
                if len(sel_months_int) > 1:
                    prod_col_chart = 'product_name_clean' if 'product_name_clean' in df_work.columns else 'product_name'
                    # Drop first 3 symbols from names for chart labels
                    df_work = df_work.copy()
                    df_work[prod_col_chart] = df_work[prod_col_chart].astype(str).str[3:].str.strip()
                    # Агрегуємо ТІЛЬКИ по останній декаді кожного обраного місяця
                    if {'year','month_int','decade'}.issubset(df_work.columns):
                        dfm = (
                            df_work[df_work['month_int'].isin(sel_months_int)]
                            .dropna(subset=['year','month_int','decade'])
                            .copy()
                        )
                        if not dfm.empty:
                            max_dec = dfm.groupby(['year','month_int'])['decade'].transform('max')
                            df_lastdec = dfm[dfm['decade'] == max_dec].copy()
                            multi_df = (
                                df_lastdec
                                .groupby([prod_col_chart, 'month_int'], as_index=False)['quantity']
                                .sum()
                                .rename(columns={'quantity': 'total_quantity'})
                            )
                        else:
                            multi_df = pd.DataFrame()
                    else:
                        # Фолбек, якщо бракує колонок: агрегуємо по повному місяцю (як раніше)
                        multi_df = (
                            df_work[df_work['month_int'].isin(sel_months_int)]
                            .groupby([prod_col_chart, 'month_int'], as_index=False)['quantity']
                            .sum()
                            .rename(columns={'quantity': 'total_quantity'})
                        )

                    if not multi_df.empty:
                        multi_df['Місяць'] = multi_df['month_int'].astype(int).map(lambda m: UKRAINIAN_MONTHS.get(int(m), str(m)))
                        # Впорядкуємо продукти за загальною к-стю (сума по місяцях), щоб сортування було логічним
                        order_df = multi_df.groupby(prod_col_chart, as_index=False)['total_quantity'].sum().sort_values('total_quantity', ascending=False)
                        category_order = order_df[prod_col_chart].tolist()
                        st.subheader("Кількість по продуктах (останні декади обраних місяців)")
                        fig_qty_grouped = px.bar(
                            multi_df,
                            x=prod_col_chart,
                            y='total_quantity',
                            color='Місяць',
                            barmode='group',
                            category_orders={prod_col_chart: category_order},
                            labels={prod_col_chart: 'Продукт', 'total_quantity': 'К-сть'},
                            text='total_quantity',
                        )
                        fig_qty_grouped.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                        fig_qty_grouped.update_layout(
                            xaxis_tickangle=-45,
                            margin=dict(l=10, r=10, t=10, b=80),
                            height=550,
                        )
                        st.plotly_chart(fig_qty_grouped, use_container_width=True) 
                    else:
                        st.info("Немає даних для побудови діаграми за кілька місяців.")
                else:
                    # Один місяць: показуємо лише останню декаду
                    prod_col_chart = 'product_name_clean' if 'product_name_clean' in df_latest_decade.columns else 'product_name'
                    # Drop first 3 symbols from names for chart labels
                    df_latest_decade = df_latest_decade.copy()
                    df_latest_decade[prod_col_chart] = df_latest_decade[prod_col_chart].astype(str).str[3:].str.strip()
                    qty_chart_df = (
                        df_latest_decade.groupby(prod_col_chart, as_index=False)['quantity']
                        .sum()
                        .rename(columns={'quantity': 'total_quantity'})
                        .sort_values('total_quantity', ascending=False)
                    )
                    if not qty_chart_df.empty:
                        title_text = "Кількість по продуктах (остання декада)"
                        if last_decade is not None and cur_month is not None and cur_year is not None:
                            title_text += f" — декада {int(last_decade)}, {UKRAINIAN_MONTHS.get(int(cur_month), str(cur_month))} {cur_year}"
                        st.subheader(title_text)
                        fig_qty_overall = px.bar(
                            qty_chart_df,
                            x=prod_col_chart,
                            y='total_quantity',
                            labels={prod_col_chart: 'Продукт', 'total_quantity': 'К-сть'},
                            text='total_quantity',
                        )
                        fig_qty_overall.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                        fig_qty_overall.update_layout(
                            xaxis_tickangle=-45,
                            margin=dict(l=10, r=10, t=10, b=80),
                            height=550,
                        )
                        st.plotly_chart(fig_qty_overall, use_container_width=True)
                    else:
                        st.info("Немає даних для побудови діаграми (остання декада).")

                # Матриця BCG (обсяг vs темп росту) — під діаграмою кількості у цій вкладці
            

            with tab_city:
                # Комбінована діаграма: виручка по містах + кількість
                df_city_src = df_with_revenue.copy() if 'df_with_revenue' in locals() else df_work.copy()
                if 'revenue' not in df_city_src.columns:
                    df_city_src['revenue'] = 0.0
                city_col2 = 'city' if 'city' in df_city_src.columns else None
                if city_col2:
                    by_city = (
                        df_city_src.groupby(city_col2, as_index=False)[['revenue','quantity']]
                        .sum()
                        .sort_values('revenue', ascending=False)
                        .head(30)
                    )
                    if not by_city.empty:
                        st.subheader("Виручка по містах (+ кількість)")
                        fig_combo = go.Figure()
                        # Бар по виручці
                        fig_combo.add_trace(go.Bar(x=by_city[city_col2], y=by_city['revenue'], name='Сума'))
                        # Лінія по кількості на вторинній осі
                        fig_combo.add_trace(go.Scatter(x=by_city[city_col2], y=by_city['quantity'], name='К-сть', mode='lines+markers', yaxis='y2'))
                        fig_combo.update_layout(
                            yaxis=dict(title='Сума, грн'),
                            yaxis2=dict(title='К-сть', overlaying='y', side='right'),
                            xaxis=dict(tickangle=-45),
                            margin=dict(l=10, r=10, t=10, b=80), height=550,
                            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
                        )
                        st.plotly_chart(fig_combo, use_container_width=True)
                    else:
                        st.info("Немає даних для міст.")
                else:
                    st.info("Колонка міста відсутня у вибраному зрізі.")

            with tab_trend:
                st.subheader("Тренд по декадах у вибраному періоді")
                # Використовуємо весь вибраний період (усі обрані місяці)
                df_period_trend = df_with_revenue.copy() if 'df_with_revenue' in locals() else df_work.copy()
                if 'revenue' not in df_period_trend.columns:
                    df_period_trend = df_period_trend.copy()
                    df_period_trend['revenue'] = 0.0
                if {'year','month_int','decade','revenue'}.issubset(df_period_trend.columns):
                    trend_df = (
                        df_period_trend
                        .dropna(subset=['year','month_int','decade'])
                        .groupby(['year','month_int','decade'], as_index=False)[['revenue','quantity']].sum()
                    )
                    if not trend_df.empty:
                        trend_df['Місяць'] = trend_df['month_int'].astype(int).map(lambda m: UKRAINIAN_MONTHS.get(int(m), str(m)))
                        fig_trend = px.line(
                            trend_df.sort_values(['year','month_int','decade']),
                            x='decade',
                            y='revenue',
                            color='Місяць',
                            markers=True,
                            labels={'decade':'Декада','revenue':'Сума'},
                        )
                        fig_trend.update_layout(margin=dict(l=10,r=10,t=10,b=10), height=550)
                        st.plotly_chart(fig_trend, use_container_width=True)
                    else:
                        st.info("Недостатньо даних для побудови тренду по декадах.")
                else:
                    st.info("Немає необхідних колонок (year, month_int, decade, revenue) для тренду по декадах.")
            with tab_bcg:
                st.subheader("Матриця BCG (обсяг vs темп росту)")
                df_period_bcg = df_with_revenue.copy() if 'df_with_revenue' in locals() else df_work.copy()
                if {'month_int','quantity','product_name'}.issubset(df_period_bcg.columns):
                    df_tmp = df_period_bcg.dropna(subset=['month_int']).copy()
                    # Нормалізуємо назви продуктів для коректного merge (щоб прибрати коди на початку)
                    if 'product_name_clean' not in df_tmp.columns and 'product_name' in df_tmp.columns:
                        df_tmp['product_name_clean'] = (
                            df_tmp['product_name'].astype(str)
                            .str.replace(r'^\s*[\d\W_]+', '', regex=True)
                            .str.strip()
                        )
                    prod_col_bcg = 'product_name_clean' if 'product_name_clean' in df_tmp.columns else 'product_name'
                    # Якщо доступні year/decade — беремо ТІЛЬКИ останні декади кожного місяця
                    if {'year','decade'}.issubset(df_tmp.columns):
                        df_tmp = df_tmp.dropna(subset=['year','decade']).copy()
                        df_tmp['year'] = pd.to_numeric(df_tmp['year'], errors='coerce')
                        df_tmp['decade'] = pd.to_numeric(df_tmp['decade'], errors='coerce')
                        max_dec_per = df_tmp.groupby(['year','month_int'])['decade'].transform('max')
                        df_lastdec = df_tmp[df_tmp['decade'] == max_dec_per].copy()
                    else:
                        # Фолбек: якщо немає decade/year — використовуємо увесь місяць (як раніше)
                        df_lastdec = df_tmp.copy()

                    # Агрегуємо по продуктах САМЕ за останні декади (використовуємо нормалізовану назву)
                    df_lastdec['month_int'] = df_lastdec['month_int'].astype(int)
                    vol_by_month = (
                        df_lastdec.groupby([prod_col_bcg, 'month_int'], as_index=False)['quantity'].sum()
                    )
                    months_sorted = sorted(vol_by_month['month_int'].unique().tolist())
                    if len(months_sorted) >= 2:
                        m_last, m_prev = months_sorted[-1], months_sorted[-2]
                        vol_last = vol_by_month[vol_by_month['month_int'] == m_last].rename(columns={'quantity':'qty_last'})
                        vol_prev = vol_by_month[vol_by_month['month_int'] == m_prev].rename(columns={'quantity':'qty_prev'})
                        bcg = pd.merge(
                            vol_last[[prod_col_bcg,'qty_last']],
                            vol_prev[[prod_col_bcg,'qty_prev']],
                            on=prod_col_bcg,
                            how='outer'
                        ).fillna(0)
                        bcg['growth_%'] = ((bcg['qty_last'] - bcg['qty_prev']) / bcg['qty_prev'].replace(0, pd.NA)) * 100
                        bcg['growth_%'] = bcg['growth_%'].fillna(0)
                        bcg = bcg.rename(columns={prod_col_bcg:'Препарат'})
                        # enrich hover info with quantities for both months
                        bcg['Місяць_останній'] = m_last
                        bcg['Місяць_попередній'] = m_prev
                        # Кольорове кодування за темпом росту
                        def _bucket_growth(g):
                            try:
                                g = float(g)
                            except Exception:
                                g = 0.0
                            if g < 0:
                                return 'Падіння (<0%)'
                            elif g < 3:
                                return 'Стабільно (0–3%)'
                            else:
                                return 'Ріст (>10%)'

                        bcg['Категорія'] = bcg['growth_%'].apply(_bucket_growth)

                        fig_bcg = px.scatter(
                            bcg,
                            x='qty_last',
                            y='growth_%',
                            text='Препарат',
                            color='Категорія',
                            category_orders={'Категорія': ['Падіння (<0%)','Стабільно (0–3%)','Ріст (>3%)']},
                            color_discrete_map={
                                'Падіння (<0%)': '#d62728',   # red
                                'Стабільно (0–10%)': '#ffbf00', # yellow
                                'Ріст (>3%)': '#2ca02c',      # green
                            },
                            hover_data={
                                'Препарат': True,
                                'qty_last': ':.0f',
                                'qty_prev': ':.0f',
                                'growth_%': ':.1f',
                                'Місяць_останній': True,
                                'Місяць_попередній': True,
                                'Категорія': False,
                            },
                            labels={
                                'qty_last':'Обсяг (к-сть, останній місяць)',
                                'growth_%':'Темп росту, %',
                                'qty_prev':'Обсяг (к-сть, попередній місяць)',
                                'Категорія':'Статус',
                            },
                        )
                        fig_bcg.update_traces(textposition='top center')
                        fig_bcg.update_layout(margin=dict(l=10,r=10,t=10,b=10), height=550, legend_title_text='Статус')
                        st.plotly_chart(fig_bcg, use_container_width=True)
                    else:
                        st.info("Для побудови матриці BCG потрібно щонайменше 2 обрані місяці.")
                else:
                    st.info("Недостатньо даних для матриці BCG (потрібні product_name, month_int, quantity).")
            # ТОП-5 препаратів і ABC-аналіз (поза вкладками, незалежні від вибору табів)
            cols_top_abc = st.columns([2,4])
            with cols_top_abc[0]:
                st.markdown("**ТОП-5 препаратів за кількістю**")
                top_qty = (
                    combined_prod[['Препарат', 'К-сть']]
                    .sort_values('К-сть', ascending=False)
                    .head(5)
                )
                if not top_qty.empty:
                    st.dataframe(
                        top_qty.style.format({'К-сть': '{:,.0f}'}).background_gradient(cmap='Blues', subset=['К-сть']),
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.info("Немає даних.")

                st.markdown("**ТОП-5 препаратів за сумою**")
                top_rev = (
                    combined_prod[['Препарат', 'Сума']]
                    .sort_values('Сума', ascending=False)
                    .head(5)
                )
                if not top_rev.empty:
                    st.dataframe(
                        top_rev.style.format({'Сума': '{:,.2f} грн'}).background_gradient(cmap='Greens', subset=['Сума']),
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.info("Немає даних.")

            with cols_top_abc[1]:
                st.markdown("**ABC-аналіз продуктів**")
                df_period_abc = df_with_revenue.copy() if 'df_with_revenue' in locals() else df_work.copy()
                if 'revenue' not in df_period_abc.columns:
                    df_period_abc['revenue'] = 0.0
                prod_col_full2 = 'product_name_clean' if 'product_name_clean' in df_period_abc.columns else ('product_name' if 'product_name' in df_period_abc.columns else None)
                if prod_col_full2:
                    tab_rev, tab_qty_abc = st.tabs(["За виручкою", "За кількістю"])

                    with tab_rev:
                        abc_rev = (
                            df_period_abc.groupby(prod_col_full2, as_index=False)['revenue']
                            .sum()
                            .rename(columns={prod_col_full2:'Препарат','revenue':'Сума'})
                            .sort_values('Сума', ascending=False)
                        )
                        if not abc_rev.empty:
                            total_rev_abc = float(abc_rev['Сума'].sum()) or 1.0
                            abc_rev['Частка, %'] = 100.0 * abc_rev['Сума'] / total_rev_abc
                            abc_rev['Кумулятивна частка, %'] = abc_rev['Частка, %'].cumsum()
                            def _abc_class_rev(x):
                                if x <= 80: return 'A'
                                if x <= 95: return 'B'
                                return 'C'
                            abc_rev['Клас'] = abc_rev['Кумулятивна частка, %'].apply(_abc_class_rev)
                            st.dataframe(
                                abc_rev.style
                                    .format({'Сума':'{:,.2f} грн','Частка, %':'{:,.2f}','Кумулятивна частка, %':'{:,.2f}'})
                                    .background_gradient(cmap='Greens', subset=['Сума'])
                                    .background_gradient(cmap='Blues', subset=['Частка, %']),
                                use_container_width=True,
                                hide_index=True,
                                height=430
                            )
                        else:
                            st.info("Немає даних для ABC-аналізу за виручкою.")

                    with tab_qty_abc:
                        abc_qty = (
                            df_period_abc.groupby(prod_col_full2, as_index=False)['quantity']
                            .sum()
                            .rename(columns={prod_col_full2:'Препарат','quantity':'К-сть'})
                            .sort_values('К-сть', ascending=False)
                        )
                        if not abc_qty.empty:
                            total_qty_abc = float(abc_qty['К-сть'].sum()) or 1.0
                            abc_qty['Частка, %'] = 100.0 * abc_qty['К-сть'] / total_qty_abc
                            abc_qty['Кумулятивна частка, %'] = abc_qty['Частка, %'].cumsum()
                            def _abc_class_qty(x):
                                if x <= 80: return 'A'
                                if x <= 95: return 'B'
                                return 'C'
                            abc_qty['Клас'] = abc_qty['Кумулятивна частка, %'].apply(_abc_class_qty)
                            st.dataframe(
                                abc_qty.style
                                    .format({'К-сть':'{:,.0f}','Частка, %':'{:,.2f}','Кумулятивна частка, %':'{:,.2f}'})
                                    .background_gradient(cmap='Blues', subset=['К-сть'])
                                    .background_gradient(cmap='Greens', subset=['Частка, %']),
                                use_container_width=True,
                                hide_index=True,
                                height=488
                            )
                        else:
                            st.info("Немає даних для ABC-аналізу за кількістю.")
                else:
                    st.info("Колонка продукту відсутня для ABC-аналізу.")

           


    # --- Якщо обрано більше одного місяця: динаміка, ТОП росту/падіння ---
    if len(sel_months_int) > 1:
        st.subheader("Динаміка при виборі кількох місяців")
        # Використовуємо весь вибраний період із revenue; якщо немає, додамо 0
        df_period_dyn = df_with_revenue.copy() if 'df_with_revenue' in locals() else df_work.copy()
        if 'revenue' not in df_period_dyn.columns:
            df_period_dyn['revenue'] = 0.0
        # Гарантуємо наявність month_int
        if 'month_int' not in df_period_dyn.columns:
            df_period_dyn['month_int'] = pd.to_numeric(df_period_dyn.get('month'), errors='coerce').astype('Int64')

        # Колонка продукту (очищена, якщо є)
        prod_col_full = 'product_name_clean' if 'product_name_clean' in df_period_dyn.columns else ('product_name' if 'product_name' in df_period_dyn.columns else None)

        if prod_col_full:
            # Агрегація по місяцях **тільки за останні декади**
            df_dyn_base = df_period_dyn.dropna(subset=['month_int']).copy()
            if {'year','decade'}.issubset(df_dyn_base.columns):
                df_dyn_base = df_dyn_base.dropna(subset=['year','decade']).copy()
                df_dyn_base['year'] = pd.to_numeric(df_dyn_base['year'], errors='coerce')
                df_dyn_base['decade'] = pd.to_numeric(df_dyn_base['decade'], errors='coerce')
                max_dec_per = df_dyn_base.groupby(['year','month_int'])['decade'].transform('max')
                df_lastdec_dyn = df_dyn_base[df_dyn_base['decade'] == max_dec_per].copy()
            else:
                # Фолбек: якщо нема decade/year — працюємо з усім місяцем
                df_lastdec_dyn = df_dyn_base

            month_prod = (
                df_lastdec_dyn
                .groupby([prod_col_full, 'month_int'], as_index=False)[['quantity', 'revenue']]
                .sum()
                .rename(columns={prod_col_full: 'Препарат'})
            )
            if not month_prod.empty and month_prod['month_int'].nunique() >= 2:
                # Визначаємо останній і попередній місяці
                months_sorted = sorted(month_prod['month_int'].dropna().astype(int).unique())
                last_month = int(months_sorted[-1])
                prev_month = int(months_sorted[-2])

                cur_rev = month_prod[month_prod['month_int'] == last_month][['Препарат', 'revenue']].rename(columns={'revenue': 'rev_last'})
                prev_rev = month_prod[month_prod['month_int'] == prev_month][['Препарат', 'revenue']].rename(columns={'revenue': 'rev_prev'})
                grow = pd.merge(cur_rev, prev_rev, on='Препарат', how='outer').fillna(0.0)
                grow['Δ₴'] = grow['rev_last'] - grow['rev_prev']
                grow['Δ%'] = ((grow['rev_last'] - grow['rev_prev']) / grow['rev_prev'].replace(0, pd.NA)) * 100
                grow['Δ%'] = grow['Δ%'].fillna(0.0)

                top_growth = grow.sort_values('Δ₴', ascending=False).head(5)
                top_drop = grow.sort_values('Δ₴').head(5)

                gcols = st.columns(2)
                with gcols[0]:
                    st.markdown("**ТОП-5 продуктів з найбільшим ростом (за сумою)**")
                    st.dataframe(
                        top_growth.style
                            .format({'rev_last':'{:,.2f}','rev_prev':'{:,.2f}','Δ₴':'{:,.2f}','Δ%':'{:,.1f}'})
                            .background_gradient(cmap='Greens', subset=['Δ₴']),
                        use_container_width=True, hide_index=True
                    )
                with gcols[1]:
                    st.markdown("**ТОП-5 продуктів з найбільшим падінням (за сумою)**")
                    st.dataframe(
                        top_drop.style
                            .format({'rev_last':'{:,.2f}','rev_prev':'{:,.2f}','Δ₴':'{:,.2f}','Δ%':'{:,.1f}'})
                            .background_gradient(cmap='Reds', subset=['Δ₴']),
                        use_container_width=True, hide_index=True
                    )

                # --- Додатково: ТОП-5 за КІЛЬКІСТЮ (зміна між останнім і попереднім місяцями) ---
                cur_qty = month_prod[month_prod['month_int'] == last_month][['Препарат', 'quantity']].rename(columns={'quantity': 'qty_last'})
                prev_qty = month_prod[month_prod['month_int'] == prev_month][['Препарат', 'quantity']].rename(columns={'quantity': 'qty_prev'})
                qty_grow = pd.merge(cur_qty, prev_qty, on='Препарат', how='outer').fillna(0.0)
                qty_grow['Δк-сть'] = qty_grow['qty_last'] - qty_grow['qty_prev']
                qty_grow['Δ%'] = ((qty_grow['qty_last'] - qty_grow['qty_prev']) / qty_grow['qty_prev'].replace(0, pd.NA)) * 100
                qty_grow['Δ%'] = qty_grow['Δ%'].fillna(0.0)

                qcols = st.columns(2)
                with qcols[0]:
                    st.markdown("**ТОП-5 продуктів з найбільшим ростом (за кількістю)**")
                    st.dataframe(
                        qty_grow.sort_values('Δк-сть', ascending=False).head(5)
                            .style
                            .format({'qty_last':'{:,.0f}','qty_prev':'{:,.0f}','Δк-сть':'{:,.0f}','Δ%':'{:,.1f}'})
                            .background_gradient(cmap='Blues', subset=['Δк-сть']),
                        use_container_width=True, hide_index=True
                    )
                with qcols[1]:
                    st.markdown("**ТОП-5 продуктів з найбільшим падінням (за кількістю)**")
                    st.dataframe(
                        qty_grow.sort_values('Δк-сть').head(5)
                            .style
                            .format({'qty_last':'{:,.0f}','qty_prev':'{:,.0f}','Δк-сть':'{:,.0f}','Δ%':'{:,.1f}'})
                            .background_gradient(cmap='Reds', subset=['Δк-сть']),
                        use_container_width=True, hide_index=True
                    )
            else:
                st.info("Недостатньо даних для порівняння між місяцями.")
        else:
            st.info("Колонка продукту відсутня для розрахунку динаміки.")
def show_sales_page():
    """
    Сторінка: 📊 Аналіз продажів
    Обгортка для інтеграції з навігацією
    """
    show()

# За правилами Streamlit, у сторінці лишаємо виклик show() при імпорті
# але краще явно:
if __name__ == "__main__":
    show()
else:
    show()