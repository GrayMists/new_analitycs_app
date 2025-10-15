# app/dashboard/user_dashboard.py
import streamlit as st
import datetime as dt
import pandas as pd
from app.io.supabase_client import init_supabase_client
from app.io import loader_sales as data_loader
from app.services.sales_data_service import SalesDataService
from app.services.sales_analytics_service import SalesAnalyticsService
from app.services.sales_charts_service import SalesChartsService
from app.utils.sales_formatters import SalesFormatters


def fetch_user_sales_independent(profile: dict):
    """
    Незалежно від сторінки Sales:
    1) зчитує фільтри з профілю (region_id, region, territory(tech), line),
    2) визначає останній період (year, month, decade),
    3) тягне дані через data_loader.fetch_all_sales_data(...),
    4) обрізає датафрейм до ОСТАННЬОЇ ДЕКАДИ цього місяця,
    5) повертає (df_trim, meta) без жодних side-effects.
    """
    client = init_supabase_client()
    if not client:
        raise RuntimeError("Supabase не ініціалізовано.")

    # фільтри з профілю
    region_id = profile.get("region_id")
    region_name = profile.get("region")  # Використовуємо повну назву з профілю, напр. '24. Тернопіль'
    if isinstance(region_name, str):
        region_name = region_name.strip()
    territory_tech = (profile.get("territory") or "").strip() or "Всі"   # у профілі вже технічна назва
    line_param = (profile.get("line") or "Всі").strip() or "Всі"

    # Використовуємо поточний календарний місяць (без обмеження декадою)
    today = dt.date.today()
    current_year = today.year
    current_month = today.month
    months_param = [f"{current_month:02d}"]  # лоадер очікує рядки "MM"

    # завантажити "як на Sales" (той самий лоадер, але це незалежно від самої сторінки)
    df_loaded = data_loader.fetch_all_sales_data(
        region_name=region_name or None,   # лоадер приймає назву регіону (не id)
        territory=territory_tech,          # технічна назва або "Всі"
        line=line_param,                   # "Всі"/"Лінія 1"/"Лінія 2"
        months=months_param
    )

    df_trim = df_loaded.copy()  # залишаємо весь поточний місяць (усі декади)

    meta = {
        "region_id": region_id,
        "region_name": region_name,
        "territory": territory_tech,
        "line": line_param,
        "period": {"year": current_year, "month": current_month, "decade": None},
        "months_param": months_param,
        "rows": int(len(df_trim)),
    }
    return df_trim, meta


def display_user_profile(user):
   

    # Отримуємо повні дані користувача з таблиці profiles
    if user.get('id'):
        client = init_supabase_client()
        if client:
            try:
                # Отримуємо дані користувача з таблиці profiles за id
                result = client.table("profiles").select("*").eq("id", user['id']).execute()
                
                if result.data and len(result.data) > 0:
                    profile_data = result.data[0]
                    return profile_data
                else:
                    st.warning("Дані користувача не знайдено в таблиці profiles")
                    return None
            except Exception as e:
                st.error(f"Помилка при отриманні даних з profiles: {e}")
                return None
        else:
            st.error("Supabase не ініціалізовано. Перевірте секцію [supabase] у st.secrets з SUPABASE_URL та SUPABASE_KEY.")
            return None
    else:
        st.warning("ID користувача не знайдено")
        return None


def display_sales_data(profile_data, user):
    """Відображає дані продажів користувача"""
    if not profile_data:
        return


    # Спробуємо ще раз отримати повний профіль (за email), щоб мати region/territory/line/region_id/type/city
    client = init_supabase_client()
    profile_row = None
    try:
        if client:
            prof_q = client.table("profiles").select("*").eq("email", user['email']).limit(1).execute()
            profile_row = (prof_q.data or [None])[0]
    except Exception as e:
        st.warning(f"Не вдалося повторно отримати профіль: {e}")

    if profile_row:
        try:
            # Завантажуємо зріз продажів за параметрами профілю
            df_sales, meta = fetch_user_sales_independent(profile_row)
            # Зберігаємо у власний state для home (НЕ впливає на сторінку Sales)
            st.session_state['home_sales_df'] = df_sales
            st.session_state['home_sales_meta'] = meta

            if df_sales is None or df_sales.empty:
                st.info("Даних для цього зрізу не знайдено.")
                return

            # -------- Далі відтворюємо основні блоки як на сторінці "Продажі" --------
            data_service = SalesDataService()
            analytics_service = SalesAnalyticsService()
            charts_service = SalesChartsService()
            formatters = SalesFormatters()

            # Підготовка робочих даних
            df_work = data_service.prepare_work_data(df_sales)

            # Завантаження цін для поточного місяця (якщо є region_id)
            price_df_all = pd.DataFrame()
            region_id = meta.get('region_id')
            all_months_int = df_work['month_int'].dropna().astype(int).unique().tolist() if 'month_int' in df_work.columns else []
            if all_months_int and region_id:
                price_df_all = data_service.fetch_price_data(region_id, all_months_int)

            # Додавання даних про доходи
            df_with_revenue = data_service.add_revenue_data(df_work, price_df_all)

            # Остання декада для KPI і таблиць
            df_latest_decade, last_decade, cur_year, cur_month = data_service.get_latest_decade_data(df_work)
            df_latest_with_revenue = df_latest_decade.copy()
            if cur_month is not None and region_id:
                price_df_cur = data_service.fetch_price_data(region_id, [cur_month])
                if not price_df_cur.empty:
                    df_latest_with_revenue = pd.merge(
                        df_latest_with_revenue,
                        price_df_cur,
                        left_on=['product_name','month_int'],
                        right_on=['product_name','month_int'],
                        how='left'
                    )
                    if 'quantity' in df_latest_with_revenue.columns and 'price' in df_latest_with_revenue.columns:
                        df_latest_with_revenue['revenue'] = df_latest_with_revenue['quantity'] * df_latest_with_revenue['price']
                if 'revenue' not in df_latest_with_revenue.columns:
                    df_latest_with_revenue['revenue'] = 0.0
            
            # Блок з KPI та графіком і зведеною таблицею
            col1, col2 = st.columns([5, 2])
            # Ліва колонка: KPI (локальний розмір шрифту) + графік у контейнері з рамкою
            with col1:
                with st.container(border=True):
            
                    analytics_kpis = analytics_service.calculate_kpis(
                        df_latest_decade,
                        df_latest_with_revenue,
                        df_with_revenue,
                    )
                    # Рендеримо KPI як HTML з інлайн-стилями (локальне керування розміром шрифту)
                    k_total_qty = f"{analytics_kpis['total_quantity']:,}"
                    k_total_sum = f"{analytics_kpis['total_revenue_sum']:,.2f} грн"
                    k_avg_check = f"{analytics_kpis['avg_check_top']:,.2f} грн"
                    k_avg_qty_pc = f"{analytics_kpis['avg_qty_per_client_top']:,.2f}"
                    k_uniq_clients = f"{analytics_kpis['uniq_clients_top']:,}"

                    kpi_html = f"""
                    <div style='display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px;'>
                      <div style='flex:1;min-width:160px;'>
                        <div style='font-size:14px;color:#6b7280;'>Загальна кількість (ост. декада)</div>
                        <div style='font-size:20px;font-weight:600;'>{k_total_qty}</div>
                      </div>
                      <div style='flex:1;min-width:160px;'>
                        <div style='font-size:14px;color:#6b7280;'>Загальна сума (ост. декада)</div>
                        <div style='font-size:20px;font-weight:600;'>{k_total_sum}</div>
                      </div>
                      <div style='flex:1;min-width:160px;'>
                        <div style='font-size:14px;color:#6b7280;'>Середній чек (період)</div>
                        <div style='font-size:20px;font-weight:600;'>{k_avg_check}</div>
                      </div>
                      <div style='flex:1;min-width:160px;'>
                        <div style='font-size:14px;color:#6b7280;'>Сер. к-сть/клієнта (період)</div>
                        <div style='font-size:20px;font-weight:600;'>{k_avg_qty_pc}</div>
                      </div>
                      <div style='flex:1;min-width:160px;'>
                        <div style='font-size:14px;color:#6b7280;'>Унікальних клієнтів (період)</div>
                        <div style='font-size:20px;font-weight:600;'>{k_uniq_clients}</div>
                      </div>
                    </div>
                    """
                    st.markdown(kpi_html, unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)

                    charts_service.render_product_quantity_chart(
                        df_work,
                        df_latest_decade,
                        [],
                        last_decade,
                        cur_month,
                        cur_year,
                    )
                    st.markdown('</div>', unsafe_allow_html=True)
            # Права колонка: зведена таблиця
            with col2:
                with st.container(border=True):
                    # Контейнер фіксованої висоти для таблиці

                    st.subheader("Сума по продуктах")
                    combined_prod = analytics_service.calculate_product_summary(
                        df_latest_decade,
                        df_latest_with_revenue,
                    )
                    # Показуємо лише стовпці Препарат і Сума
                    sum_cols = [c for c in ['Препарат', 'Сума'] if c in combined_prod.columns]
                    df_sum_only = combined_prod[sum_cols].copy().sort_values('Сума', ascending=False) if sum_cols else combined_prod.copy()
                    styled_table = (
                        df_sum_only.style
                        .format({'Сума': '{:,.2f} грн'})
                        .background_gradient(cmap='Greens', subset=['Сума'] if 'Сума' in df_sum_only.columns else None)
                        
                    )
                    st.dataframe(styled_table, use_container_width=True, hide_index=True, height=627)
                    st.markdown('</div>', unsafe_allow_html=True)

            col3, col4 = st.columns([5,2])
            # ТОП аптек (за виручкою/кількістю)
            with col3:
                st.subheader("ТОП-10 аптек")
                top_pharmacies = analytics_service.calculate_top_pharmacies(df_with_revenue)
                if not top_pharmacies.empty:
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
                else:
                    st.info("Не вдалось сформувати унікальну адресу для агрегації аптек.")

            with col4:
                # Аналітичні таблиці (ТОП-5, ABC)
                st.subheader("ТОП-5 препаратів")
                top_qty = combined_prod[['Препарат', 'К-сть']].sort_values('К-сть', ascending=False).head(5) if not combined_prod.empty else pd.DataFrame()
                if not top_qty.empty:
                    styled_qty = formatters.style_top_products_table(top_qty, 'quantity')
                    st.dataframe(styled_qty, use_container_width=True, hide_index=True)
                top_rev = combined_prod[['Препарат', 'Сума']].sort_values('Сума', ascending=False).head(5) if not combined_prod.empty else pd.DataFrame()
                if not top_rev.empty:
                    styled_rev = formatters.style_top_products_table(top_rev, 'revenue')
                    st.dataframe(styled_rev, use_container_width=True, hide_index=True)

            st.subheader("ABC аналітика")
            col5, col6 = st.columns(2)
            with col5:
                abc_rev = analytics_service.calculate_abc_analysis(df_with_revenue, 'revenue')
                if not abc_rev.empty:
                    styled_abc_rev = formatters.style_abc_table(abc_rev, 'revenue')
                    st.dataframe(styled_abc_rev, use_container_width=True, hide_index=True)
            with col6:
                abc_qty = analytics_service.calculate_abc_analysis(df_with_revenue, 'quantity')
                if not abc_qty.empty:
                    styled_abc_qty = formatters.style_abc_table(abc_qty, 'quantity')
                    st.dataframe(styled_abc_qty, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Помилка завантаження незалежного зрізу: {e}")
    else:
        st.info("Профіль (region/territory/line/region_id) не знайдено або неповний.")
