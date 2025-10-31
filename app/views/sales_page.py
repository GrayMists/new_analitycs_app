# app/views/sales_page.py
from __future__ import annotations

import os, sys
import streamlit as st
import pandas as pd
from typing import Dict, Any

# --- забезпечуємо імпорти виду "from app...." коли запускається як пакет Streamlit ---
PAGES_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(PAGES_DIR)
PROJECT_ROOT = os.path.dirname(APP_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

# --- імпорти сервісів ---
from app.services.sales_data_service import SalesDataService
from app.services.sales_analytics_service import SalesAnalyticsService
from app.services.sales_charts_service import SalesChartsService
from app.utils.sales_formatters import SalesFormatters
from app.utils.sales_cache import SalesCacheManager
from app.utils.geocoding_service import GeocodingService
from app.utils import UKRAINIAN_MONTHS


def _require_login():
    """Перевіряє авторизацію користувача"""
    user = st.session_state.get('auth_user')
    if not user:
        st.warning("Будь ласка, увійдіть на головній сторінці, щоб переглядати цю сторінку.")
        st.stop()


def _render_filters_sidebar(data_service: SalesDataService) -> Dict[str, Any]:
    """Рендерить фільтри в боковій панелі"""
    _DEF_ALL = "(усі)"
    
    # Ініціалізація стану фільтрів
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
    
    def _mark_filters_dirty():
        st.session_state['filters_dirty'] = True
    
    with st.sidebar:
        st.markdown("### Фільтри")
        
        # Регіон
        regions = data_service.fetch_regions()
        region_names = [r["name"] for r in regions]
        prev_region = ss.get('sales_region', _DEF_ALL)
        if prev_region and prev_region != _DEF_ALL and prev_region not in region_names:
            region_names = [prev_region] + region_names
        st.selectbox("Регіон", [_DEF_ALL] + region_names, key="sales_region", on_change=_mark_filters_dirty)
        
        # Територія
        sel_region_id = None
        if ss['sales_region'] and ss['sales_region'] != _DEF_ALL:
            match_r = next((r for r in regions if r["name"] == ss['sales_region']), None)
            sel_region_id = match_r["id"] if match_r else None
        
        territories = data_service.fetch_territories(sel_region_id)
        territory_names = [t["name"] for t in territories]
        prev_terr = ss.get('sales_territory_name', _DEF_ALL)
        terr_choices = [_DEF_ALL] + territory_names
        if prev_terr and prev_terr != _DEF_ALL and prev_terr not in terr_choices:
            terr_choices = [prev_terr] + terr_choices[1:]
        st.selectbox("Територія", terr_choices, key="sales_territory_name", on_change=_mark_filters_dirty)
        
        # Оновлюємо технічну назву території
        ss['sales_territory_technical'] = None
        if ss['sales_territory_name'] and ss['sales_territory_name'] != _DEF_ALL:
            match_t = next((t for t in territories if t["name"] == ss['sales_territory_name']), None)
            ss['sales_territory_technical'] = match_t["technical_name"] if match_t else None
        
        # Лінія продукту
        lines_all = ["Лінія 1", "Лінія 2"]
        prev_line = ss.get('sales_line', _DEF_ALL)
        line_choices = [_DEF_ALL] + lines_all
        if prev_line and prev_line != _DEF_ALL and prev_line not in line_choices:
            line_choices = [prev_line] + line_choices[1:]
        st.selectbox("Лінія продукту", line_choices, key="sales_line", on_change=_mark_filters_dirty)
        
        # Місяці
        month_keys = list(UKRAINIAN_MONTHS.keys())
        ss['sales_months'] = [m for m in ss.get('sales_months', []) if m in month_keys]
        st.multiselect(
            "Місяці",
            options=month_keys,
            format_func=lambda m: UKRAINIAN_MONTHS.get(m, str(m)),
            key="sales_months",
            on_change=_mark_filters_dirty,
        )
        
        # Кнопка отримання даних
        if st.button("Отримати дані", type="primary", use_container_width=True):
            ss['sales_submit_once'] = True
            ss['filters_dirty'] = False
            ss['last_submitted_filters'] = {
                'region_name': (None if (ss['sales_region'] == _DEF_ALL or not ss['sales_region']) else ss['sales_region']),
                'territory_name': ss['sales_territory_name'],
                'territory_technical': ss.get('sales_territory_technical'),
                'line': ("Всі" if (ss['sales_line'] == _DEF_ALL or not ss['sales_line']) else ss['sales_line']),
                'months_int': ss['sales_months'],
            }
    
    return {
        'region_id': sel_region_id,
        'region_name': ss['sales_region'],
        'territory_name': ss['sales_territory_name'],
        'territory_technical': ss['sales_territory_technical'],
        'line': ss['sales_line'],
        'months': ss['sales_months'],
        'submit_once': ss['sales_submit_once']
    }


def _render_kpi_metrics(analytics_service: SalesAnalyticsService, formatters: SalesFormatters,
                       df_latest_decade: pd.DataFrame, df_latest_with_revenue: pd.DataFrame, 
                       df_period_top: pd.DataFrame) -> None:
    """Рендерить KPI метрики"""
    kpis = analytics_service.calculate_kpis(df_latest_decade, df_latest_with_revenue, df_period_top)
    formatters.create_kpi_metrics(kpis)


def _render_product_summary(analytics_service: SalesAnalyticsService, formatters: SalesFormatters,
                          df_latest_decade: pd.DataFrame, df_latest_with_revenue: pd.DataFrame) -> pd.DataFrame:
    """Рендерить зведення по продуктах"""
    st.subheader("Кількість та сума по продуктах")
    
    combined_prod = analytics_service.calculate_product_summary(df_latest_decade, df_latest_with_revenue)
    styled_table = formatters.style_product_summary_table(combined_prod)
    st.dataframe(styled_table, use_container_width=True, hide_index=True)
    
    return combined_prod


def _render_top_pharmacies(analytics_service: SalesAnalyticsService, formatters: SalesFormatters,
                         df_with_revenue: pd.DataFrame) -> None:
    """Рендерить топ аптек"""
    st.subheader("ТОП-10 аптек")
    
    top_pharmacies = analytics_service.calculate_top_pharmacies(df_with_revenue)
    
    if top_pharmacies.empty:
        st.info("Не вдалось сформувати унікальну адресу для агрегації аптек.")
        return
    
    tab_cli_rev, tab_cli_qty = st.tabs(["За виручкою", "За кількістю"])
    
    with tab_cli_rev:
        df_rev10 = top_pharmacies.sort_values('Сума', ascending=False).head(10)
        cols_rev = ['Сума','Аптека','Місто','Адреса'] + [c for c in df_rev10.columns if c not in ['__addr_key__','Сума','К-сть','Аптека','Місто','Адреса']]
        styled_rev = formatters.style_top_pharmacies_table(df_rev10[cols_rev], 'revenue')
        st.dataframe(styled_rev, use_container_width=True, hide_index=True)
    
    with tab_cli_qty:
        df_qty10 = top_pharmacies.sort_values('К-сть', ascending=False).head(10)
        cols_qty = ['К-сть','Аптека','Місто','Адреса'] + [c for c in df_qty10.columns if c not in ['__addr_key__','Сума','К-сть','Аптека','Місто','Адреса']]
        styled_qty = formatters.style_top_pharmacies_table(df_qty10[cols_qty], 'quantity')
        st.dataframe(styled_qty, use_container_width=True, hide_index=True)


def _render_charts(charts_service: SalesChartsService, df_work: pd.DataFrame, df_latest_decade: pd.DataFrame,
                  df_city_src: pd.DataFrame, df_period_trend: pd.DataFrame, bcg_data: pd.DataFrame,
                  sel_months_int: list, last_decade: int, cur_month: int, cur_year: int) -> None:
    """Рендерить всі графіки"""
    tab_qty, tab_city, tab_trend, tab_bcg = st.tabs(["Кількість по продуктах", "Виручка по містах (+ к-сть)", "Тренд по декадах ", "BCG"])
    
    with tab_qty:
        charts_service.render_product_quantity_chart(df_work, df_latest_decade, sel_months_int, last_decade, cur_month, cur_year)
    
    with tab_city:
        charts_service.render_city_revenue_chart(df_city_src)
    
    with tab_trend:
        charts_service.render_trend_chart(df_period_trend)
    


def _render_analytics(analytics_service: SalesAnalyticsService, formatters: SalesFormatters,
                     combined_prod: pd.DataFrame, df_period_abc: pd.DataFrame, 
                     grow_rev: pd.DataFrame, grow_qty: pd.DataFrame) -> None:
    """Рендерить аналітичні таблиці"""
    cols_top_abc = st.columns([2,4])
    
    with cols_top_abc[0]:
        st.markdown("**ТОП-5 препаратів за кількістю**")
        top_qty = combined_prod[['Препарат', 'К-сть']].sort_values('К-сть', ascending=False).head(5)
        if not top_qty.empty:
            styled_qty = formatters.style_top_products_table(top_qty, 'quantity')
            st.dataframe(styled_qty, use_container_width=True, hide_index=True)
        else:
            st.info("Немає даних.")
        
        st.markdown("**ТОП-5 препаратів за сумою**")
        top_rev = combined_prod[['Препарат', 'Сума']].sort_values('Сума', ascending=False).head(5)
        if not top_rev.empty:
            styled_rev = formatters.style_top_products_table(top_rev, 'revenue')
            st.dataframe(styled_rev, use_container_width=True, hide_index=True)
        else:
            st.info("Немає даних.")
    
    with cols_top_abc[1]:
        st.markdown("**ABC-аналіз продуктів**")
        prod_col_full2 = 'product_name_clean' if 'product_name_clean' in df_period_abc.columns else ('product_name' if 'product_name' in df_period_abc.columns else None)
        
        if prod_col_full2:
            tab_rev, tab_qty_abc = st.tabs(["За виручкою", "За кількістю"])
            
            with tab_rev:
                abc_rev = analytics_service.calculate_abc_analysis(df_period_abc, 'revenue')
                if not abc_rev.empty:
                    styled_abc_rev = formatters.style_abc_table(abc_rev, 'revenue')
                    st.dataframe(styled_abc_rev, use_container_width=True, hide_index=True, height=430)
                else:
                    st.info("Немає даних для ABC-аналізу за виручкою.")
            
            with tab_qty_abc:
                abc_qty = analytics_service.calculate_abc_analysis(df_period_abc, 'quantity')
                if not abc_qty.empty:
                    styled_abc_qty = formatters.style_abc_table(abc_qty, 'quantity')
                    st.dataframe(styled_abc_qty, use_container_width=True, hide_index=True, height=488)
                else:
                    st.info("Немає даних для ABC-аналізу за кількістю.")
        else:
            st.info("Колонка продукту відсутня для ABC-аналізу.")


def _render_growth_analysis(analytics_service: SalesAnalyticsService, formatters: SalesFormatters,
                           df_period_dyn: pd.DataFrame) -> None:
    """Рендерить аналіз росту"""
    st.subheader("Динаміка при виборі кількох місяців")
    
    grow_rev, grow_qty = analytics_service.calculate_growth_metrics(df_period_dyn)
    
    if not grow_rev.empty and not grow_qty.empty:
        top_growth = grow_rev.sort_values('Δ₴', ascending=False).head(5)
        top_drop = grow_rev.sort_values('Δ₴').head(5)
        
        gcols = st.columns(2)
        with gcols[0]:
            st.markdown("**ТОП-5 продуктів з найбільшим ростом (за сумою)**")
            styled_growth = formatters.style_growth_table(top_growth, 'revenue')
            st.dataframe(styled_growth, use_container_width=True, hide_index=True)
        
        with gcols[1]:
            st.markdown("**ТОП-5 продуктів з найбільшим падінням (за сумою)**")
            styled_drop = formatters.style_growth_table(top_drop, 'revenue')
            st.dataframe(styled_drop, use_container_width=True, hide_index=True)
        
        # ТОП-5 за КІЛЬКІСТЮ
        qcols = st.columns(2)
        with qcols[0]:
            st.markdown("**ТОП-5 продуктів з найбільшим ростом (за кількістю)**")
            styled_qty_growth = formatters.style_growth_table(grow_qty.sort_values('Δк-сть', ascending=False).head(5), 'quantity')
            st.dataframe(styled_qty_growth, use_container_width=True, hide_index=True)
        
        with qcols[1]:
            st.markdown("**ТОП-5 продуктів з найбільшим падінням (за кількістю)**")
            styled_qty_drop = formatters.style_growth_table(grow_qty.sort_values('Δк-сть').head(5), 'quantity')
            st.dataframe(styled_qty_drop, use_container_width=True, hide_index=True)
    else:
        st.info("Недостатньо даних для порівняння між місяцями.")


def show():
    """Головна функція сторінки продажів"""
    _require_login()
    st.set_page_config(layout="wide")
    st.title("📊 Аналіз продажів")
    
    # Ініціалізація сервісів
    data_service = SalesDataService()
    analytics_service = SalesAnalyticsService()
    charts_service = SalesChartsService()
    formatters = SalesFormatters()
    cache_manager = SalesCacheManager()
    geocoding_service = GeocodingService()
    
    if data_service.client is None:
        st.error("Supabase не ініціалізовано. Перевірте st.secrets['SUPABASE_URL'|'SUPABASE_KEY'].")
        st.stop()
    
    # Рендеринг фільтрів
    filters = _render_filters_sidebar(data_service)
    
    if not filters['submit_once']:
        st.info("Оберіть фільтри зліва і натисніть \"Отримати дані\".")
        st.stop()
    
    # Підготовка параметрів
    region_param = None if (not filters['region_name'] or filters['region_name'] == "(усі)") else filters['region_name']
    territory_param = None if (not filters['territory_technical']) else filters['territory_technical']
    line_param = "Всі" if (not filters['line'] or filters['line'] == "(усі)") else filters['line']
    months_param = ([f"{int(m):02d}" for m in filters['months']] if filters['months'] else None)
    
    # Завантаження даних з кешуванням
    with st.spinner("Завантажую дані продажів із Supabase..."):
        sales_key = cache_manager.make_sales_key(region_param, territory_param or "Всі", line_param, months_param)
        df_loaded = cache_manager.get_cached_sales_data(sales_key)
        
        if df_loaded is None:
            df_loaded = data_service.fetch_sales_data(region_param, territory_param or "Всі", line_param, months_param)
            cache_manager.set_cached_sales_data(sales_key, df_loaded)
    
    if df_loaded is None or df_loaded.empty:
        st.warning("Дані не знайдені для обраних фільтрів.")
        st.stop()
    
    st.success(f"Завантажено {len(df_loaded):,} рядків.")
    
    # Підготовка даних
    df_work = data_service.prepare_work_data(df_loaded)
    
    # Завантаження цін
    all_months_int = df_work['month_int'].dropna().astype(int).unique().tolist()
    price_df_all = pd.DataFrame()
    if all_months_int and filters['region_id']:
        price_key_all = cache_manager.make_price_key(filters['region_id'], all_months_int)
        price_df_all = cache_manager.get_cached_price_data(price_key_all)
        if price_df_all is None:
            price_df_all = data_service.fetch_price_data(filters['region_id'], all_months_int)
            cache_manager.set_cached_price_data(price_key_all, price_df_all)
    
    # Додавання даних про доходи
    df_with_revenue = data_service.add_revenue_data(df_work, price_df_all)
    
    # Отримання даних останньої декади
    df_latest_decade, last_decade, cur_year, cur_month = data_service.get_latest_decade_data(df_work)
    
    # Розрахунок доходів для останньої декади
    df_latest_with_revenue = df_latest_decade.copy()
    if cur_month is not None and filters['region_id']:
        price_key_cur = cache_manager.make_price_key(filters['region_id'], [cur_month])
        price_df_cur = cache_manager.get_cached_price_data(price_key_cur)
        if price_df_cur is None:
            price_df_cur = data_service.fetch_price_data(filters['region_id'], [cur_month])
            cache_manager.set_cached_price_data(price_key_cur, price_df_cur)
        
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
    
    # Рендеринг KPI метрик
    _render_kpi_metrics(analytics_service, formatters, df_latest_decade, df_latest_with_revenue, df_with_revenue)
    
    # Основний контент
    col1, col2 = st.columns([2,5])
    
    with col1:
        # Зведення по продуктах
        combined_prod = _render_product_summary(analytics_service, formatters, df_latest_decade, df_latest_with_revenue)
        
        # Топ аптек
        _render_top_pharmacies(analytics_service, formatters, df_with_revenue)
    
    with col2:
        # Графіки
        _render_charts(charts_service, df_work, df_latest_decade, df_with_revenue, df_with_revenue, 
                      analytics_service.calculate_bcg_matrix(df_with_revenue), filters['months'], 
                      last_decade, cur_month, cur_year)
        
        # Аналітичні таблиці
        _render_analytics(analytics_service, formatters, combined_prod, df_with_revenue, 
                         pd.DataFrame(), pd.DataFrame())
        
        # Аналіз росту (якщо обрано кілька місяців)
        if len(filters['months']) > 1:
            _render_growth_analysis(analytics_service, formatters, df_with_revenue)


def show_sales_page():
    """Обгортка для інтеграції з навігацією"""
    show()


if __name__ == "__main__":
    show()
else:
    show()
