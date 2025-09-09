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
    Читає налаштування Supabase зі st.secrets з підтримкою кількох форматів.

    Підтримувані варіанти у .streamlit/secrets.toml або у Secrets на Streamlit Cloud:

    1) Плоский варіант (корінь):
       SUPABASE_URL = "https://xxx.supabase.co"
       SUPABASE_KEY = "<service_or_anon_key>"

    2) Секція [general]:
       [general]
       SUPABASE_URL = "https://xxx.supabase.co"
       SUPABASE_KEY = "<service_or_anon_key>"

    3) Секція [supabase] (рекомендовано):
       [supabase]
       url = "https://xxx.supabase.co"
       anon_key = "<anon_key>"

    Повертає SupabaseConf з url та key або None, якщо ключі не знайдені.
    """
    try:
        # Підтримка всіх поширених форматів secrets:
        # 1) Плоскі ключі у корені
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")

        # 2) Усередині секції [general]
        if not url or not key:
            general = st.secrets.get("general", {})
            if not url:
                url = general.get("SUPABASE_URL")
            if not key:
                key = general.get("SUPABASE_KEY")

        # 3) Усередині секції [supabase] (рекомендований формат)
        #    [supabase]
        #    url = "https://...supabase.co"
        #    anon_key = "..."
        if not url or not key:
            supa = st.secrets.get("supabase", {})
            if not url:
                url = supa.get("url")
            if not key:
                # основний рекомендований ключ
                key = supa.get("anon_key") or supa.get("key")
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