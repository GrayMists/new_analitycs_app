import streamlit as st
from supabase import create_client, Client
from app.core.config import get_supabase_conf

@st.cache_resource
def init_supabase_client() -> Client | None:
    """
    Ініціалізує клієнт Supabase.
    Використовує дані з st.secrets (через get_supabase_conf).
    Якщо ключів немає — повертає None.
    """
    conf = get_supabase_conf()
    if not conf.url or not conf.key:
        st.warning("Не знайдено SUPABASE_URL або SUPABASE_KEY у secrets.toml")
        return None

    try:
        client = create_client(conf.url, conf.key)
        return client
    except Exception as e:
        st.error(f"Не вдалося ініціалізувати Supabase: {e}")
        return None