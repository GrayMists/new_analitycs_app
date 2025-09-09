# app/io/uploader.py
from __future__ import annotations

import time
import pandas as pd
import streamlit as st
from app.core.config import SUPABASE_INSERT_BATCH

def upload_doctor_points(client, df_long: pd.DataFrame, table_name: str = "doctor_points") -> int:
    """
    Завантажує дані у Supabase таблицю `doctor_points` батчами.
    Повертає кількість успішно вставлених рядків.

    - client: Supabase client (init_supabase_client())
    - df_long: DataFrame у довгому форматі
    - table_name: назва таблиці
    """
    if client is None:
        st.error("Supabase client не ініціалізовано.")
        return 0

    rows = df_long.to_dict(orient="records")
    total_inserted = 0

    for i in range(0, len(rows), SUPABASE_INSERT_BATCH):
        batch = rows[i : i + SUPABASE_INSERT_BATCH]
        try:
            response = client.table(table_name).insert(batch).execute()
            if response.data is not None:
                total_inserted += len(batch)
        except Exception as e:
            st.error(f"Помилка при вставці батчу {i // SUPABASE_INSERT_BATCH + 1}: {e}")
            # невелика пауза перед наступною спробою
            time.sleep(1)

    return total_inserted