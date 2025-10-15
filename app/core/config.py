from dataclasses import dataclass
from typing import List, Dict
import os
import streamlit as st
try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None

# ---------------------------
# Supabase конфіг
# ---------------------------
@dataclass
class SupabaseConf:
    url: str | None
    key: str | None


def get_supabase_conf() -> SupabaseConf:
    """
    Читає налаштування Supabase зі st.secrets.
    
    Очікує секцію [supabase] з ключами SUPABASE_URL та SUPABASE_KEY:
    
    [supabase]
    SUPABASE_URL = "your_supabase_url"
    SUPABASE_KEY = "your_service_or_anon_key"
    
    Повертає SupabaseConf з url та key або None, якщо ключі не знайдені.
    """
    try:
        # 1) Основне джерело: секція [supabase]
        supa = st.secrets.get("supabase", {})
        url = supa.get("SUPABASE_URL")
        key = supa.get("SUPABASE_KEY")

        # 2) Резерв: верхній рівень st.secrets (на випадок, якщо секція не використовується)
        if not url:
            url = st.secrets.get("SUPABASE_URL")
        if not key:
            key = st.secrets.get("SUPABASE_KEY")

        # 3) Резерв: змінні оточення
        if not url:
            url = os.environ.get("SUPABASE_URL")
        if not key:
            key = os.environ.get("SUPABASE_KEY")

        # 4) Резерв: пряме читання файлу .streamlit/secrets.toml з кореня проєкту
        secrets_path = None
        if (not url or not key) and tomllib is not None:
            try:
                # app/core/config.py -> app/core -> app -> PROJECT_ROOT
                current_dir = os.path.dirname(os.path.abspath(__file__))
                app_dir = os.path.dirname(current_dir)
                project_root = os.path.dirname(app_dir)
                secrets_path = os.path.join(project_root, ".streamlit", "secrets.toml")
                if os.path.exists(secrets_path):
                    with open(secrets_path, "rb") as f:
                        parsed = tomllib.load(f)  # type: ignore[arg-type]
                    file_supa = parsed.get("supabase", {}) if isinstance(parsed, dict) else {}
                    if not url:
                        url = (file_supa.get("SUPABASE_URL")
                               or parsed.get("SUPABASE_URL"))
                    if not key:
                        key = (file_supa.get("SUPABASE_KEY")
                               or parsed.get("SUPABASE_KEY"))
            except Exception as _:
                pass

        # Діагностика при відсутності ключів
        if not url or not key:
            st.error(
                f"""
            🔍 Діагностика секретів:
            - Всі секрети (Streamlit): {dict(st.secrets)}
            - Секція supabase (Streamlit): {supa}
            - SUPABASE_URL: {url}
            - SUPABASE_KEY: {'ЗНАЙДЕНО' if bool(key) else 'НЕ ЗНАЙДЕНО'}

            Перевірте варіанти джерел:
            1) .streamlit/secrets.toml з секцією [supabase]
               SUPABASE_URL = "your_url"
               SUPABASE_KEY = "your_key"
            2) АБО верхній рівень secrets (без секції) з тими ж ключами
            3) АБО змінні оточення SUPABASE_URL / SUPABASE_KEY
            4) Файл проєкту .streamlit/secrets.toml (читання напряму) — переконайтесь, що він існує тут:
               {secrets_path if 'secrets_path' in locals() else '<project_root>/.streamlit/secrets.toml'}
            Додаткова діагностика:
            - CWD (os.getcwd): {os.getcwd()}
            - tomllib доступний: {bool(tomllib)}
            - Існування secrets_path: {os.path.exists(secrets_path) if secrets_path else None}
            """
            )

    except Exception as e:
        st.error(f"Помилка читання секретів: {e}")
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