# app/dashboard/user_dashboard.py
import streamlit as st
import datetime as dt
from app.io.supabase_client import init_supabase_client
from app.io import loader_sales as data_loader


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
    """Відображає профіль користувача"""
    st.success(f"Увійшли як {user['email']}")
    
    # Отримуємо повні дані користувача з таблиці profiles
    if user.get('id'):
        client = init_supabase_client()
        if client:
            try:
                # Отримуємо дані користувача з таблиці profiles за id
                result = client.table("profiles").select("*").eq("id", user['id']).execute()
                
                if result.data and len(result.data) > 0:
                    profile_data = result.data[0]
                    st.info(f"👤 ID: {profile_data.get('id')}")
                    if profile_data.get('full_name'):
                        st.info(f"👤 Повне ім'я: {profile_data.get('full_name')}")
                    if profile_data.get('email'):
                        st.info(f"📧 Email: {profile_data.get('email')}")
                    
                    # Показуємо всі доступні поля з profiles
                    st.subheader("📋 Дані з таблиці profiles:")
                    for key, value in profile_data.items():
                        if value is not None and key not in ['id', 'email', 'full_name']:
                            st.write(f"**{key}**: {value}")
                    
                    return profile_data
                else:
                    st.warning("Дані користувача не знайдено в таблиці profiles")
                    return None
            except Exception as e:
                st.error(f"Помилка при отриманні даних з profiles: {e}")
                return None
        else:
            st.error("Supabase не ініціалізовано")
            return None
    else:
        st.warning("ID користувача не знайдено")
        return None


def display_sales_data(profile_data, user):
    """Відображає дані продажів користувача"""
    if not profile_data:
        return
    
    st.divider()
    st.subheader("Незалежний зріз продажів (остання декада останнього місяця)")

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
            df_sales, meta = fetch_user_sales_independent(profile_row)
            st.caption(
                f"Фільтри: регіон='{meta['region_name'] or 'Всі'}' (id={meta['region_id']}), "
                f"територія='{meta['territory']}', лінія='{meta['line']}'."
            )
            p = meta['period']
            if p.get('decade') is not None:
                st.caption(f"Період: {p['year']}-{p['month']:02d}, декада {p['decade']} • Рядків: {meta['rows']:,}")
            else:
                st.caption(f"Період: {p['year']}-{p['month']:02d} • Рядків: {meta['rows']:,}")

            # Зберігаємо у власний state для home (НЕ впливає на сторінку Sales)
            st.session_state['home_sales_df'] = df_sales
            st.session_state['home_sales_meta'] = meta

            if df_sales is not None and not df_sales.empty:
                st.dataframe(df_sales.head(50), use_container_width=True)
                # Додаткова таблиця: групування за product_name з сумою quantity
                if "product_name" in df_sales.columns and "quantity" in df_sales.columns:
                    grouped = (
                        df_sales.groupby("product_name", as_index=False)["quantity"]
                        .sum()
                        .sort_values("quantity", ascending=False)
                    )
                    st.subheader("Сума кількості за препаратом")
                    st.dataframe(grouped, use_container_width=True)
            else:
                st.info("Даних для цього зрізу не знайдено.")
        except Exception as e:
            st.error(f"Помилка завантаження незалежного зрізу: {e}")
    else:
        st.info("Профіль (region/territory/line/region_id) не знайдено або неповний.")
