# app/data/processing_sales.py
from __future__ import annotations

import pandas as pd
import numpy as np
from datetime import date, timedelta

# --- робочі дні України (guarded import) ---
try:
    from workalendar.europe import Ukraine  # type: ignore
    _CAL_UA = Ukraine()
    _HAVE_WORKALENDAR = True
except Exception:
    Ukraine = None  # type: ignore
    _CAL_UA = None
    _HAVE_WORKALENDAR = False


def is_working_day(dt: date) -> bool:
    """
    True, якщо робочий день в Україні.
    Якщо workalendar недоступний — просте правило пн–пт.
    """
    if _HAVE_WORKALENDAR and _CAL_UA is not None:
        return _CAL_UA.is_working_day(dt)
    return dt.weekday() < 5


def create_full_address(df: pd.DataFrame) -> pd.DataFrame:
    """
    Створює єдину колонку 'full_address' з city, street, house_number (якщо її ще немає).
    """
    if 'full_address' not in df.columns:
        df = df.copy()
        df['full_address'] = (
            df.get('city', '').astype(str).fillna('') + ", " +
            df.get('street', '').astype(str).fillna('') + ", " +
            df.get('house_number', '').astype(str).fillna('')
        ).str.strip(' ,')
    return df


def compute_actual_sales(df: pd.DataFrame) -> pd.DataFrame:
    """
    Розраховує «фактичні» (чисті) продажі між декадами.

    Припущення: у вхідному df колонка 'quantity' — КУМУЛЯТИВНЕ значення на кінець декади.
    Алгоритм:
      1) очищення ключових текстових полів;
      2) створення 'full_address';
      3) агрегація продажів у межах декади;
      4) віднімання значення попередньої декади (shift) => actual_quantity;
      5) фільтр actual_quantity != 0.
    """
    req = [
        'decade', 'distributor', 'product_name', 'quantity',
        'year', 'month', 'city', 'street', 'house_number', 'new_client'
    ]
    for col in req:
        if col not in df.columns:
            # Повертаємо порожній df зі стандартними колонками — зручніше для UI
            return pd.DataFrame(
                columns=['distributor', 'product_name', 'full_address',
                         'year', 'month', 'decade', 'actual_quantity', 'new_client']
            )

    if df.empty:
        return pd.DataFrame(
            columns=['distributor', 'product_name', 'full_address',
                     'year', 'month', 'decade', 'actual_quantity', 'new_client']
        )

    # --- очищення текстових полів ---
    text_cols = ['distributor', 'product_name', 'city', 'street', 'house_number', 'new_client']
    df = df.copy()
    for c in text_cols:
        if c in df.columns:
            df[c] = df[c].fillna('').astype(str).str.strip()

    # повна адреса
    df = create_full_address(df)
    df = df[df['full_address'] != '']

    # decade у число
    df['decade'] = pd.to_numeric(df['decade'], errors='coerce').fillna(0).astype(int)

    if (df['distributor'] == '').all():
        return pd.DataFrame(
            columns=['distributor', 'product_name', 'full_address',
                     'year', 'month', 'decade', 'actual_quantity', 'new_client']
        )

    # 1) агрегація всередині декади
    df = df.groupby(
        ['distributor', 'product_name', 'full_address', 'year', 'month', 'decade', 'new_client'],
        as_index=False
    )['quantity'].sum()

    # 2) сортування для коректного shift
    df = df.sort_values(
        by=['distributor', 'product_name', 'full_address', 'year', 'month', 'new_client', 'decade']
    )

    # 3) попередня декада
    df['prev_decade_quantity'] = df.groupby(
        ['distributor', 'product_name', 'full_address', 'year', 'month', 'new_client']
    )['quantity'].shift(1).fillna(0)

    # 4) чисті продажі
    df['actual_quantity'] = df['quantity'] - df['prev_decade_quantity']

    # 5) вихід
    result = df[[
        'distributor', 'product_name', 'full_address',
        'year', 'month', 'decade', 'actual_quantity', 'new_client'
    ]].copy()

    # decade назад у рядок — якщо так очікує UI
    result['decade'] = result['decade'].astype(str)

    return result[result['actual_quantity'] != 0]


def calculate_forecast_with_bootstrap(
    df_for_current_month: pd.DataFrame,
    last_decade: int,
    year: int,
    month: int,
    n_iterations: int = 1000
) -> dict:
    """
    Прогноз доходу через бутстрап. Повертає:
      - point_forecast_revenue
      - conf_interval_revenue (2.5%, 97.5%)
      - bootstrap_distribution_revenue (масив)
      - workdays_passed, workdays_left
    """
    if df_for_current_month.empty or last_decade >= 30:
        return {}

    try:
        start_date = date(year, month, 1)
        end_date_of_period = date(year, month, last_decade)
    except ValueError:
        return {}

    # робочі дні пройшли
    workdays_passed = 0
    current_day = start_date
    while current_day <= end_date_of_period:
        if is_working_day(current_day):
            workdays_passed += 1
        current_day += timedelta(days=1)

    if workdays_passed <= 0:
        return {}

    # кінець місяця
    if month == 12:
        first_day_next = date(year + 1, 1, 1)
    else:
        first_day_next = date(year, month + 1, 1)
    last_day_of_month = first_day_next - timedelta(days=1)

    # скільки робочих днів лишилось
    workdays_left = 0
    if end_date_of_period < last_day_of_month:
        current_day = end_date_of_period + timedelta(days=1)
        while current_day <= last_day_of_month:
            if is_working_day(current_day):
                workdays_left += 1
            current_day += timedelta(days=1)

    total_revenue_so_far = df_for_current_month.get('revenue', pd.Series(dtype=float)).sum()

    # бутстрап за revenue
    sales_data = df_for_current_month.get('revenue', pd.Series(dtype=float)).values
    n_sales = len(sales_data)
    if n_sales == 0:
        return {}

    bootstrap_forecasts_revenue: list[float] = []
    for _ in range(n_iterations):
        idx = np.random.randint(0, n_sales, size=n_sales)
        sample = sales_data[idx]
        sample_revenue = float(sample.sum())
        daily_rate = sample_revenue / workdays_passed
        forecast_r = sample_revenue + (workdays_left * daily_rate)
        bootstrap_forecasts_revenue.append(forecast_r)

    conf_interval_revenue = (
        float(np.percentile(bootstrap_forecasts_revenue, 2.5)),
        float(np.percentile(bootstrap_forecasts_revenue, 97.5)),
    )

    point_forecast = total_revenue_so_far + (workdays_left * (total_revenue_so_far / workdays_passed))

    return {
        "point_forecast_revenue": float(point_forecast),
        "conf_interval_revenue": conf_interval_revenue,
        "bootstrap_distribution_revenue": bootstrap_forecasts_revenue,
        "workdays_passed": int(workdays_passed),
        "workdays_left": int(workdays_left),
    }


def calculate_product_level_forecast(
    df_for_current_month: pd.DataFrame,
    workdays_passed: int,
    workdays_left: int
) -> pd.DataFrame:
    """
    Точковий прогноз по кожному продукту: forecast_quantity / forecast_revenue.
    Очікує наявність колонок 'quantity' та 'revenue'.
    """
    if df_for_current_month.empty or workdays_passed <= 0:
        return pd.DataFrame()

    df = df_for_current_month.copy()

    # 1) зведення фактів
    product_summary = df.groupby('product_name').agg(
        quantity_so_far=('quantity', 'sum'),
        revenue_so_far=('revenue', 'sum')
    ).reset_index()

    # 2) швидкості
    product_summary['daily_quantity_rate'] = product_summary['quantity_so_far'] / workdays_passed
    product_summary['daily_revenue_rate'] = product_summary['revenue_so_far'] / workdays_passed

    # 3) прогноз
    product_summary['forecast_quantity'] = product_summary['quantity_so_far'] + (
        product_summary['daily_quantity_rate'] * workdays_left
    )
    product_summary['forecast_revenue'] = product_summary['revenue_so_far'] + (
        product_summary['daily_revenue_rate'] * workdays_left
    )

    return product_summary.sort_values(by='forecast_revenue', ascending=False)


def create_address_client_map(df: pd.DataFrame) -> dict:
    """
    Словник: full_address -> кома-розділений список клієнтів (new_client).
    """
    if 'full_address' not in df.columns or 'new_client' not in df.columns:
        return {}
    address_map = (
        df.groupby('full_address')['new_client']
        .unique()
        .apply(lambda x: ', '.join(sorted(x)))
        .to_dict()
    )
    return address_map


def calculate_main_kpis(df: pd.DataFrame) -> dict:
    """
    Повертає ключові KPI для огляду.
    """
    if df.empty:
        return {
            "total_quantity": 0,
            "unique_products": 0,
            "unique_clients": 0,
            "avg_quantity_per_client": 0,
            "top5_share": 0,
            "top_products": pd.Series(dtype=float),
            "rev_top_products": pd.Series(dtype=float),
        }

    total_quantity = df['quantity'].sum()
    unique_products = df['product_name'].nunique()
    unique_clients = df.drop_duplicates(subset=['new_client', 'full_address']).shape[0]
    avg_quantity_per_client = (total_quantity / unique_clients) if unique_clients else 0.0

    product_sales = df.groupby('product_name')['quantity'].sum().sort_values(ascending=False)
    top5_total = product_sales.head(5).sum()
    top5_share = (top5_total / total_quantity * 100) if total_quantity else 0.0

    return {
        "total_quantity": int(total_quantity),
        "unique_products": int(unique_products),
        "unique_clients": int(unique_clients),
        "avg_quantity_per_client": float(avg_quantity_per_client),
        "top5_share": float(top5_share),
        "top_products": product_sales.head(5),
        "rev_top_products": product_sales.sort_values(ascending=True).head(5),
    }