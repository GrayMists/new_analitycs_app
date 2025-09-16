# app/views/drug_store_page.py
from __future__ import annotations

import os, sys
import streamlit as st
import pandas as pd

# --- Auth guard: require login before viewing this page ---

def _require_login():
    user = st.session_state.get('auth_user')
    if not user:
        st.warning("Будь ласка, увійдіть на головній сторінці, щоб переглядати цю сторінку.")
        st.stop()

# Ensure "from app..." imports work when run by Streamlit
PAGES_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(PAGES_DIR)
PROJECT_ROOT = os.path.dirname(APP_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# Internal modules
from app.io import loader_sales as data_loader
from app.io.supabase_client import init_supabase_client
# Видаляємо імпорт навігації, оскільки вона вже є в основному файлі
from app.utils import UKRAINIAN_MONTHS

@st.cache_data(show_spinner=False, ttl=1800)
def _cached_fetch_sales(region_name, territory, line, months):
    return data_loader.fetch_all_sales_data(
        region_name=region_name,
        territory=territory,
        line=line,
        months=months,
    )

# Cached price fetcher (analogous to Sales page)
@st.cache_data(show_spinner=False, ttl=1800)
def _cached_fetch_price(region_id: int, months: list[int]):
    return data_loader.fetch_price_data(region_id=region_id, months=months)

# --- URL state sync & normalization (same as Sales) ---
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

    # Only adopt URL values if user hasn't explicitly submitted on this page
    # and there isn't an ongoing local edit (filters_dirty)
    apply_from_url = not ss.get('sales_submit_once', False) and not ss.get('filters_dirty', False)

    def _maybe_apply(key, url_val, default_val):
        if not apply_from_url:
            return
        # Apply if key is missing OR still at its default value
        if key not in ss or ss.get(key) in (None, default_val, []):
            ss[key] = (url_val if (url_val is not None and url_val != '') else default_val)

    if 'reg' in qp:
        _maybe_apply('sales_region', qp.get('reg'), _DEF_ALL)
    if 'terr' in qp:
        _maybe_apply('sales_territory_name', qp.get('terr'), _DEF_ALL)
    if 'line' in qp:
        _maybe_apply('sales_line', qp.get('line'), _DEF_ALL)
    if 'months' in qp:
        # months default is []
        if apply_from_url and ('sales_months' not in ss or ss.get('sales_months') in (None, [],)):
            ss['sales_months'] = _months_from_param(qp.get('months'))


# --- Helper: Restore filters from memory if URL is empty ---
def _ensure_filters_from_memory_if_url_empty():
    """If user navigates to this page without query params, prefill filters from
    last_submitted_filters or from _shared_sales_filters so sidebar shows
    consistent values, but do NOT auto-fetch."""
    ss = st.session_state
    qp = st.query_params
    if not any(k in qp for k in ('reg','terr','line','months')):
        src = ss.get('last_submitted_filters')
        if not src:
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
            ss['sales_months'] = _norm_months_list(src.get('months_int') or ss.get('sales_months', []))
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

@st.cache_data(show_spinner=False, ttl=1800)
def _fetch_regions(_client):
    try:
        rows = _client.table("region").select("id,name").order("name").execute().data or []
        return [
            {"id": r.get("id"), "name": r.get("name")}
            for r in rows
            if r.get("id") and r.get("name")
        ]
    except Exception:
        return []

@st.cache_data(show_spinner=False, ttl=1800)
def _fetch_territories(_client, region_id: int | None):
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


def show():
    _require_login()
    st.set_page_config(layout="wide")
    st.title("🏪 Аптеки — аналіз")
    client = init_supabase_client()
    if client is None:
        st.error("Supabase не ініціалізовано. Перевірте st.secrets['SUPABASE_URL'|'SUPABASE_KEY'].")
        st.stop()

    # --- persistent filter state (shared keys with Sales) ---
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

    # Read URL params into shared state
    _read_query_params_into_state()
    _ensure_filters_from_memory_if_url_empty()

    def _mark_filters_dirty():
        st.session_state['filters_dirty'] = True

    # --- Sidebar: same filter widgets as Sales ---
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
        # Preserve previously selected territory if not present
        prev_terr = ss.get('sales_territory_name', _DEF_ALL)
        terr_choices = [_DEF_ALL] + territory_names
        if prev_terr and prev_terr != _DEF_ALL and prev_terr not in terr_choices:
            terr_choices = [prev_terr] + terr_choices[1:]
        st.selectbox("Територія", terr_choices, key="sales_territory_name", on_change=_mark_filters_dirty)

        ss['sales_territory_technical'] = None
        if ss['sales_territory_name'] and ss['sales_territory_name'] != _DEF_ALL:
            match_t = next((t for t in territories if t["name"] == ss['sales_territory_name']), None)
            ss['sales_territory_technical'] = match_t["technical_name"] if match_t else None

        lines_all = ["Лінія 1", "Лінія 2"]
        # Preserve previously selected line if not present
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

        month_keys = list(UKRAINIAN_MONTHS.keys())
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

    # Якщо кнопка не натиснута, але є спільний датасет зі сторінки Sales — використовуємо його.
    # Інакше просимо натиснути кнопку і зупиняємо виконання.
    if not st.session_state.get('sales_submit_once', False):
        shared_df = st.session_state.get('_shared_sales_df')
        if shared_df is None or shared_df.empty:
            st.info('Оберіть фільтри в сайдбарі та натисніть "Отримати дані".')
            st.stop()

    # Build params
    sel_region_name = ss['sales_region']
    sel_territory_name = ss['sales_territory_name']
    sel_territory_technical = ss['sales_territory_technical']
    sel_line = ss['sales_line']
    sel_months_int = _norm_months_list(ss['sales_months'])

    region_param = None if (not sel_region_name or sel_region_name == _DEF_ALL) else sel_region_name
    territory_param = sel_territory_technical if sel_territory_technical else (None if sel_territory_name == _DEF_ALL else sel_territory_name)
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
            #st.caption("Дані взяті зі спільного кешу (без повторного запиту до БД). Натисніть \"Отримати дані\" для перезавантаження.")
        else:
            st.info('Фільтри змінені. Натисніть "Отримати дані" для застосування.')
            st.stop()
    else:
        df_loaded = None
        used_shared = False

        # 1) Якщо дані вже завантажені на сторінці Sales і фільтри збігаються — беремо їх без БД
        shared_df = st.session_state.get('_shared_sales_df')
        shared_filters = st.session_state.get('_shared_sales_filters')
        if shared_df is not None and isinstance(shared_filters, dict):
            if (
                shared_filters.get('region_name') == region_param and
                shared_filters.get('territory') == (territory_param or "Всі") and
                shared_filters.get('line') == line_param and
                (shared_filters.get('months') or None) == (months_param or None)
            ):
                df_loaded = shared_df
                used_shared = True

        # 2) Інакше — локальний кеш сесії; якщо промах — тягнемо з БД
        if df_loaded is None:
            with st.spinner("Завантажую дані продажів із Supabase..."):
                sales_cache, _ = _get_session_cache()
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

        #if used_shared:
            #st.caption("Дані взяті зі спільного кешу сторінки Sales (без повторного запиту до БД).")
        else:
            st.success(f"Завантажено {len(df_loaded):,} рядків.")

        # Оновлюємо спільний кеш, щоб інші сторінки могли використати цей зріз
        st.session_state['_shared_sales_df'] = df_loaded
        st.session_state['_shared_sales_filters'] = {
            'region_name': region_param,
            'territory': territory_param or "Всі",
            'line': line_param,
            'months': months_param,
        }

    # Підготовка та розрахунок revenue на повний період
    df_work = df_loaded.copy()
    if 'month_int' not in df_work.columns:
        df_work['month_int'] = pd.to_numeric(df_work.get('month'), errors='coerce').astype('Int64')
    for col in ("year", "decade"):
        if col in df_work.columns:
            df_work[col] = pd.to_numeric(df_work[col], errors='coerce').astype('Int64')

    # Прайси для всіх присутніх у даних місяців
    all_months_int = df_work['month_int'].dropna().astype(int).unique().tolist()
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
        if 'revenue' not in df_with_revenue.columns:
            df_with_revenue['revenue'] = 0.0

    # --- Дві колонки: 1) Мережі/точки  2) ABC-аналіз аптек ---
    col_net, col_abc = st.columns([2,5])

    with col_net:
        # --- Tabs: 1) Торгові точки  2) Упаковки  3) Суми ---
        tab_points, tab_packs, tab_sum_period = st.tabs([
            "Торгові точки", "Упаковки", "Сума"
        ])

        with tab_points:
            st.subheader("Мережі та кількість торгових точок")
            net_src = df_with_revenue.copy()
            if 'new_client' not in net_src.columns:
                st.info("Колонка 'new_client' відсутня — неможливо порахувати мережі.")
            else:
                # Сформуємо адресний ключ
                if {'city','street','house_number'}.issubset(net_src.columns):
                    net_tmp = net_src.copy()
                    net_tmp['__city__'] = net_tmp['city'].fillna('').astype(str).str.strip()
                    net_tmp['__street__'] = net_tmp['street'].fillna('').astype(str).str.strip()
                    net_tmp['__house__'] = net_tmp['house_number'].fillna('').astype(str).str.strip()
                    net_tmp['__addr_key__'] = (
                        net_tmp['__city__'].str.lower() + '|' + net_tmp['__street__'].str.lower() + '|' + net_tmp['__house__'].str.lower()
                    )
                else:
                    net_tmp = net_src.copy()
                    if 'full_address_processed' in net_tmp.columns:
                        net_tmp['__addr_key__'] = net_tmp['full_address_processed'].astype(str).fillna('').str.strip().str.lower()
                    elif 'address' in net_tmp.columns:
                        net_tmp['__addr_key__'] = net_tmp['address'].astype(str).fillna('').str.strip().str.lower()
                    else:
                        net_tmp['__addr_key__'] = ''
                # Назва мережі
                net_tmp['__network__'] = net_tmp['new_client'].astype(str).fillna('').str.strip()
                # Відкидаємо порожні
                net_tmp = net_tmp[(net_tmp['__network__'] != '') & (net_tmp['__addr_key__'] != '')].copy()
                if net_tmp.empty:
                    st.info("Немає достатніх даних (мережа/адреса) для підрахунку торгових точок.")
                else:
                    # Унікальні пари (мережа, адреса)
                    net_pairs = net_tmp[['__network__','__addr_key__']].drop_duplicates()
                    # Кількість унікальних адрес (торгових точок) на мережу
                    net_cnt = (
                        net_pairs.groupby('__network__', as_index=False)['__addr_key__']
                        .nunique()
                        .rename(columns={'__network__':'Мережа','__addr_key__':'Точок'})
                        .sort_values('Точок', ascending=False)
                    )
                    total_points = int(net_cnt['Точок'].sum()) or 1
                    net_cnt['Частка, %'] = 100.0 * net_cnt['Точок'] / total_points
                    net_cnt['Кумулятивна, %'] = net_cnt['Частка, %'].cumsum()
                    # (Необов’язково) кількість міст для мережі
                    if 'city' in net_src.columns:
                        city_pairs = net_tmp[['__network__','city']].drop_duplicates()
                        city_cnt = city_pairs.groupby('__network__', as_index=False)['city'].nunique().rename(columns={'__network__':'Мережа','city':'Міста(к-сть)'})
                        net_cnt = net_cnt.merge(city_cnt, on='Мережа', how='left')
                    # Вивід
                    cols_net = ['Мережа','Точок','Частка, %','Кумулятивна, %'] + ([ 'Міста(к-сть)'] if 'Міста(к-сть)' in net_cnt.columns else [])
                    st.dataframe(
                        net_cnt[cols_net]
                            .style
                            .format({'Точок':'{:,.0f}','Частка, %':'{:,.2f}','Кумулятивна, %':'{:,.2f}'})
                            .background_gradient(cmap='Blues', subset=['Точок']),
                        use_container_width=True,
                        hide_index=True,
                        height=600
                    )

        with tab_packs:
            st.subheader("Мережі та кількість упаковок")
            qty_src = df_with_revenue.copy()
            if 'new_client' not in qty_src.columns:
                st.info("Колонка 'new_client' відсутня — неможливо порахувати мережі.")
            elif 'quantity' not in qty_src.columns:
                st.info("Колонка 'quantity' відсутня — неможливо порахувати кількість упаковок.")
            else:
                qty_tmp = qty_src.copy()
                # Назва мережі
                qty_tmp['__network__'] = qty_tmp['new_client'].astype(str).fillna('').str.strip()
                # Відкидаємо порожні
                qty_tmp = qty_tmp[(qty_tmp['__network__'] != '')].copy()
                if qty_tmp.empty:
                    st.info("Немає достатніх даних (мережа) для підрахунку упаковок.")
                else:
                    # Гарантуємо числовий тип для quantity
                    qty_tmp['quantity'] = pd.to_numeric(qty_tmp['quantity'], errors='coerce').fillna(0)
                    net_qty = (
                        qty_tmp.groupby('__network__', as_index=False)['quantity']
                        .sum()
                        .rename(columns={'__network__':'Мережа','quantity':'Упаковок'})
                        .sort_values('Упаковок', ascending=False)
                    )
                    total_qty = float(net_qty['Упаковок'].sum()) or 1.0
                    net_qty['Частка, %'] = 100.0 * net_qty['Упаковок'] / total_qty
                    net_qty['Кумулятивна, %'] = net_qty['Частка, %'].cumsum()
                    st.dataframe(
                        net_qty[['Мережа','Упаковок','Частка, %','Кумулятивна, %']]
                            .style
                            .format({'Упаковок':'{:,.0f}','Частка, %':'{:,.2f}','Кумулятивна, %':'{:,.2f}'})
                            .background_gradient(cmap='Blues', subset=['Упаковок'])
                            .background_gradient(cmap='Greens', subset=['Частка, %']),
                        use_container_width=True,
                        hide_index=True,
                        height=600
                    )

        with tab_sum_period:
            st.subheader("Сума по мережах (за обраний період)")
            sum_src = df_with_revenue.copy()
            if 'new_client' not in sum_src.columns:
                st.info("Колонка 'new_client' відсутня — неможливо порахувати мережі.")
            elif 'revenue' not in sum_src.columns:
                st.info("Колонка 'revenue' відсутня — суми не розраховані.")
            else:
                tmp = sum_src.copy()
                tmp['__network__'] = tmp['new_client'].astype(str).fillna('').str.strip()
                tmp = tmp[tmp['__network__'] != '']
                if tmp.empty:
                    st.info("Немає достатніх даних (мережа) для підрахунку суми.")
                else:
                    tmp['revenue'] = pd.to_numeric(tmp['revenue'], errors='coerce').fillna(0.0)
                    net_sum = (
                        tmp.groupby('__network__', as_index=False)['revenue']
                        .sum()
                        .rename(columns={'__network__':'Мережа','revenue':'Сума'})
                        .sort_values('Сума', ascending=False)
                    )
                    total_rev = float(net_sum['Сума'].sum()) or 1.0
                    net_sum['Частка, %'] = 100.0 * net_sum['Сума'] / total_rev
                    net_sum['Кумулятивна, %'] = net_sum['Частка, %'].cumsum()
                    st.dataframe(
                        net_sum[['Мережа','Сума','Частка, %','Кумулятивна, %']]
                            .style
                            .format({'Сума':'{:,.2f} грн','Частка, %':'{:,.2f}','Кумулятивна, %':'{:,.2f}'})
                            .background_gradient(cmap='Greens', subset=['Сума'])
                            .background_gradient(cmap='Blues', subset=['Частка, %']),
                        use_container_width=True,
                        hide_index=True,
                        height=600
                    )

    with col_abc:
        # === ABC-аналіз аптек (за унікальною адресою) ===
        st.markdown("**ABC-аналіз аптек (за унікальною адресою)**")

        # Optional filter by products for pharmacy ABC
        prod_col_filter = 'product_name'
        if prod_col_filter in df_with_revenue.columns:
            prod_options = (
                df_with_revenue[prod_col_filter]
                .dropna()
                .astype(str)
                .str.strip()
                .sort_values()
                .unique()
                .tolist()
            )
            selected_products = st.multiselect(
                'Фільтр препаратів для ABC аптек',
                options=prod_options,
                default=[],
                help='Оберіть один або кілька препаратів. Порожній вибір = всі препарати.'
            )
        else:
            selected_products = []

        df_pharm_abc = df_with_revenue.copy()
        if selected_products and prod_col_filter in df_pharm_abc.columns:
            df_pharm_abc = df_pharm_abc[df_pharm_abc[prod_col_filter].astype(str).str.strip().isin(selected_products)]
            if df_pharm_abc.empty:
                st.info('За обраними препаратами даних немає для ABC-аналізу аптек.')

        # Build address key and display fields
        if {'city','street','house_number'}.issubset(df_pharm_abc.columns):
            tmp2 = df_pharm_abc.copy()
            tmp2['__city__'] = tmp2['city'].fillna('').astype(str).str.strip()
            tmp2['__street__'] = tmp2['street'].fillna('').astype(str).str.strip()
            tmp2['__house__'] = tmp2['house_number'].fillna('').astype(str).str.strip()
            tmp2['__addr_key__'] = (
                tmp2['__city__'].str.lower() + '|' + tmp2['__street__'].str.lower() + '|' + tmp2['__house__'].str.lower()
            )
            tmp2['__city_disp__'] = tmp2['__city__']
            tmp2['__addr_disp__'] = (tmp2['__street__'] + ' ' + tmp2['__house__']).str.strip()
            name_cols = [c for c in ['new_client','client','pharmacy','client_name'] if c in tmp2.columns]
            if name_cols:
                tmp2['__client_name__'] = tmp2[name_cols[0]].astype(str).fillna('').str.strip()
            else:
                tmp2['__client_name__'] = ''
        else:
            tmp2 = df_pharm_abc.copy()
            if 'full_address_processed' in tmp2.columns:
                tmp2['__addr_key__'] = tmp2['full_address_processed'].astype(str).fillna('').str.strip().str.lower()
                tmp2['__addr_disp__'] = tmp2['full_address_processed'].astype(str).fillna('').str.strip()
            elif 'address' in tmp2.columns:
                tmp2['__addr_key__'] = tmp2['address'].astype(str).fillna('').str.strip().str.lower()
                tmp2['__addr_disp__'] = tmp2['address'].astype(str).fillna('').str.strip()
            else:
                tmp2['__addr_key__'] = ''
                tmp2['__addr_disp__'] = ''
            tmp2['__city_disp__'] = tmp2.get('city', pd.Series('', index=tmp2.index)).astype(str).fillna('').str.strip()
            name_cols = [c for c in ['new_client','client','pharmacy','client_name'] if c in tmp2.columns]
            if name_cols:
                tmp2['__client_name__'] = tmp2[name_cols[0]].astype(str).fillna('').str.strip()
            else:
                tmp2['__client_name__'] = ''

        if (tmp2['__addr_key__'] == '').all():
            st.info("Не вдалось сформувати унікальну адресу для ABC-аналізу аптек.")
            return

        # Aggregate by address
        pharm_rev = (
            tmp2.groupby('__addr_key__', as_index=False)['revenue']
            .sum().rename(columns={'revenue':'Сума'})
            .sort_values('Сума', ascending=False)
        )
        pharm_qty = (
            tmp2.groupby('__addr_key__', as_index=False)['quantity']
            .sum().rename(columns={'quantity':'К-сть'})
            .sort_values('К-сть', ascending=False)
        )
        disp2 = tmp2[['__addr_key__','__city_disp__','__addr_disp__','__client_name__']].groupby('__addr_key__', as_index=False).agg(
            __city_disp__=('__city_disp__', lambda s: next((x for x in s if str(x).strip()), '')),
            __addr_disp__=('__addr_disp__', lambda s: next((x for x in s if str(x).strip()), '')),
            __client_name__=('__client_name__', lambda s: next((x for x in s if str(x).strip()), '')),
        )
        pharm_rev = pharm_rev.merge(disp2, on='__addr_key__', how='left').rename(columns={'__city_disp__':'Місто','__addr_disp__':'Адреса','__client_name__':'Аптека'})
        pharm_qty = pharm_qty.merge(disp2, on='__addr_key__', how='left').rename(columns={'__city_disp__':'Місто','__addr_disp__':'Адреса','__client_name__':'Аптека'})

        tab_ph_rev, tab_ph_qty = st.tabs(["За виручкою", "За кількістю"])
        with tab_ph_rev:
            if not pharm_rev.empty:
                total_r = float(pharm_rev['Сума'].sum()) or 1.0
                pharm_rev['Частка, %'] = 100.0 * pharm_rev['Сума'] / total_r
                pharm_rev['Кумулятивна частка, %'] = pharm_rev['Частка, %'].cumsum()
                def _abc_class_addr_r(x):
                    if x <= 80: return 'A'
                    if x <= 95: return 'B'
                    return 'C'
                pharm_rev['Клас'] = pharm_rev['Кумулятивна частка, %'].apply(_abc_class_addr_r)
                st.dataframe(
                    pharm_rev[['Сума','Місто','Адреса','Аптека','Частка, %','Кумулятивна частка, %','Клас']]
                        .style
                        .format({'Сума':'{:,.2f} грн','Частка, %':'{:,.2f}','Кумулятивна частка, %':'{:,.2f}'} )
                        .background_gradient(cmap='Greens', subset=['Сума'])
                        .background_gradient(cmap='Blues', subset=['Частка, %']),
                    use_container_width=True,
                    hide_index=True,
                    height=545
                )
            else:
                st.info("Немає даних для ABC-аналізу аптек за виручкою.")
        with tab_ph_qty:
            if not pharm_qty.empty:
                total_q = float(pharm_qty['К-сть'].sum()) or 1.0
                pharm_qty['Частка, %'] = 100.0 * pharm_qty['К-сть'] / total_q
                pharm_qty['Кумулятивна частка, %'] = pharm_qty['Частка, %'].cumsum()
                def _abc_class_addr_q(x):
                    if x <= 80: return 'A'
                    if x <= 95: return 'B'
                    return 'C'
                pharm_qty['Клас'] = pharm_qty['Кумулятивна частка, %'].apply(_abc_class_addr_q)
                st.dataframe(
                    pharm_qty[['К-сть','Місто','Адреса','Аптека','Частка, %','Кумулятивна частка, %','Клас']]
                        .style
                        .format({'К-сть':'{:,.0f}','Частка, %':'{:,.2f}','Кумулятивна частка, %':'{:,.2f}'})
                        .background_gradient(cmap='Blues', subset=['К-сть'])
                        .background_gradient(cmap='Greens', subset=['Частка, %']),
                    use_container_width=True,
                    hide_index=True,
                    height=545
                )
            else:
                st.info("Немає даних для ABC-аналізу аптек за кількістю.")


def show_drug_store_page():
    """
    Сторінка: 🏪 Аптеки
    Обгортка для інтеграції з навігацією
    """
    show()

if __name__ == "__main__":
    show()