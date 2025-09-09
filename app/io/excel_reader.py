# app/io/excel_reader.py
from __future__ import annotations

import io
import pandas as pd
import streamlit as st
from app.core.config import DEFAULT_SHEET_NAME, DEFAULT_HEADER_ROW

@st.cache_data(show_spinner=False)
def list_sheets(file_bytes: bytes) -> list[str]:
    """Повертає список аркушів у файлі. Кешується по вмісту файлу."""
    with pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl") as xls:
        return xls.sheet_names

@st.cache_data(show_spinner=False)
def read_excel_bytes(
    file_bytes: bytes,
    sheet_name: str | None = DEFAULT_SHEET_NAME,
    header_row: int = DEFAULT_HEADER_ROW,
) -> pd.DataFrame:
    """
    Зчитує Excel у DataFrame.
    - sheet_name=None означає перший аркуш.
    - header_row — 0-based індекс рядка заголовків (за замовчуванням 2 => третій рядок).
    Кеш-ключ включає байти файлу + sheet_name + header_row.
    """
    with pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl") as xls:
        target_sheet = sheet_name or xls.sheet_names[0]
    df = pd.read_excel(
        io.BytesIO(file_bytes),
        sheet_name=target_sheet,
        header=header_row,
        engine="openpyxl",
        dtype_backend="pyarrow",  # швидший та економніший по пам’яті на великих таблицях
    )
    return df