from dataclasses import dataclass
from typing import List, Dict
import streamlit as st

# ---------------------------
# Supabase конфіг
# ---------------------------
@dataclass
class SupabaseConf:
    url: str | None
    key: str | None


def get_supabase_conf() -> SupabaseConf:
    """
    Читає SUPABASE_URL та SUPABASE_KEY зі st.secrets.
    Якщо ключів немає — повертає None для відповідних полів.

    Очікувані ключі у .streamlit/secrets.toml (у корені або в секції [general]):
    SUPABASE_URL = "https://xxx.supabase.co"
    SUPABASE_KEY = "<service_or_anon_key>"
    
    або
    
    [general]
    SUPABASE_URL = "https://xxx.supabase.co"
    SUPABASE_KEY = "<service_or_anon_key>"
    """
    try:
        # Дозволяємо зберігати у корені або в секції [general]
        url = st.secrets.get("SUPABASE_URL") or st.secrets.get("general", {}).get("SUPABASE_URL")  # type: ignore[attr-defined]
        key = st.secrets.get("SUPABASE_KEY") or st.secrets.get("general", {}).get("SUPABASE_KEY")  # type: ignore[attr-defined]
    except Exception:
        url, key = None, None

    return SupabaseConf(url=url, key=key)

# ---------------------------
# Базові константи / дефолти
# ---------------------------
DEFAULT_SHEET_NAME: str | None = None   # None = перший аркуш
DEFAULT_HEADER_ROW: int = 2             # 0-based (тобто 3-й рядок у Excel)
SUPABASE_INSERT_BATCH: int = 500

# ---------------------------
# Бізнес-колонки
# ---------------------------
PIN_COLS: List[str] = [
    "Регіон",
    "М.П.",
    "Область",
    "Місто",
    "ЛПЗ",
    "Вулиця",
    "№ будинку",
    "П.І.Б. лікаря",
    "Спеціалізація лікаря",
    "Форма",
    "Видача балів",
    "Сума Балів (поточ.міс.)",
    "Накопичення за весь час",
    "Видача накопичень",
    "Залишок Накопичень на наст.міс.",
    "Аванс",
    "Залишок на наст. міс.",
    "Кіл-сть упаковок загальна",
]

DROP_COLS: List[str] = [
    "Мобільний телефон лікаря",
    "Номер",
    "Назва",
    "ПІБ",
    "Коментар",
]

# Перейменування «довгих» назв у короткі
RENAME_MAP: Dict[str, str] = {
    "Регіон (вибір зі списку)": "Регіон",
    "М.П. (вибір зі списку)": "М.П.",
    "Область (вибір зі списку)": "Область",
    "Спеціалізація лікаря (вибір зі списку)": "Спеціалізація лікаря",
    "Форма (вибір зі списку)": "Форма",
    "Сума Балів (поточ.міс.) рахується автоматично": "Сума Балів (поточ.міс.)",
    "Залишок Накопичень на наст.міс. (рахується автоматично)": "Залишок Накопичень на наст.міс.",
    "Залишок на наст. міс. (рахується автоматично)": "Залишок на наст. міс.",
    "Кіл-сть упаковок (рах. автомат.)": "Кіл-сть упаковок загальна",
}

# Числові колонки у «широкій» таблиці, які треба привести до числа
NUMERIC_WIDE_COLS: List[str] = [
    "Видача накопичень",
    "Аванс",
    "Залишок Накопичень на наст.міс.",
    "Залишок на наст. міс.",
]