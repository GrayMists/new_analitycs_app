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
        st.warning(
            "Supabase не ініціалізовано. Перевірте st.secrets:\n"
            "- SUPABASE_URL / SUPABASE_KEY (корінь)\n"
            "- [general] секція\n"
            "- [supabase] url / anon_key"
        )
        return None

    try:
        client = create_client(conf.url, conf.key)
        return client
    except Exception as e:
        st.error(f"Не вдалося ініціалізувати Supabase: {e}")
        return None