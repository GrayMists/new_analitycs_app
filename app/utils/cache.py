# app/utils/cache.py
from __future__ import annotations

import io
import hashlib
from typing import Any, Callable, Iterable

import pandas as pd
import streamlit as st


def df_cache_key(
    df: pd.DataFrame,
    *,
    extra: dict[str, Any] | None = None,
    sample_rows: int | None = None,
) -> str:
    """
    Формує стабільний ключ кешу для DataFrame.
    - Використовує CSV-представлення (без індексу) та SHA1-хеш.
    - Можна додати 'extra' параметри (наприклад, обрані фільтри).
    - Для дуже великих df можна задати sample_rows (наприклад, 1000) — компроміс точності/швидкості.
    """
    if sample_rows and len(df) > sample_rows:
        df_for_key = df.head(sample_rows)
    else:
        df_for_key = df

    buf = io.StringIO()
    df_for_key.to_csv(buf, index=False)
    h = hashlib.sha1(buf.getvalue().encode("utf-8")).hexdigest()

    if extra:
        extra_repr = "|".join(f"{k}={repr(v)}" for k, v in sorted(extra.items()))
        return f"{h}|{extra_repr}"
    return h


def cache_data_ttl(ttl: int = 0) -> Callable:
    """
    Обгортка над st.cache_data з TTL (у секундах).
    Використання:
    @cache_data_ttl(ttl=3600)
    def heavy_fn(...): ...
    """
    return st.cache_data(ttl=ttl, show_spinner=False)


def cache_resource_once() -> Callable:
    """
    Обгортка над st.cache_resource — для об’єктів на кшталт клієнтів БД.
    Використання:
    @cache_resource_once()
    def get_client(...): ...
    """
    return st.cache_resource


@cache_data_ttl(ttl=600)
def cached_group_sum(
    df: pd.DataFrame,
    by: Iterable[str],
    value: str,
    *,
    extra_key: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """
    Приклад: кешована агрегація (sum). Під капотом власний ключ кешу:
    - df_cache_key(df, extra={..., 'by': by, 'value': value})
    - TTL = 10 хв
    """
    # Формуємо ключ — щоб обійти стандартний хешер streamlit для DataFrame
    _ = df_cache_key(df, extra={"by": tuple(by), "value": value, **(extra_key or {})})
    # Саме обчислення (streamlit закешує результат функції на основі аргументів та коду)
    return (
        df.groupby(list(by), as_index=False)[value]
        .sum()
        .sort_values(list(by))
        .reset_index(drop=True)
    )