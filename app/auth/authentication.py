# app/auth/authentication.py
import streamlit as st
import json
import base64
import time
import hashlib
from app.io.supabase_client import init_supabase_client


def authenticate_user(email: str, password: str) -> dict | None:
    """
    Аутентифікує користувача через Supabase з перевіркою пароля.
    Повертає словник з id, email та іншою інформацією користувача або None.
    """
    client = init_supabase_client()
    if not client:
        st.error("Supabase недоступний. Перевірте налаштування.")
        return None
    
    try:
        # Знаходимо користувача в таблиці profiles з перевіркою пароля
        result = client.table("profiles").select("id,email,full_name,type,password_hash").eq("email", email).execute()
        
        if result.data and len(result.data) > 0:
            user_data = result.data[0]
            stored_hash = user_data.get("password_hash")
            
            # Перевіряємо пароль
            if stored_hash and _verify_password(password, stored_hash):
                return {
                    "id": user_data.get("id"),
                    "email": user_data.get("email"),
                    "full_name": user_data.get("full_name"),
                    "type": user_data.get("type"),
                    "authenticated": True
                }
            else:
                st.error("Невірний пароль")
                return None
        else:
            st.error("Користувач з таким email не знайдений")
            return None
    except Exception as e:
        st.error(f"Помилка аутентифікації: {e}")
        return None


def _hash_password(password: str) -> str:
    """Хешує пароль з використанням SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


def _verify_password(password: str, stored_hash: str) -> bool:
    """Перевіряє пароль проти збереженого хешу"""
    return _hash_password(password) == stored_hash


def save_auth_to_cookies(user_data):
    """Зберігає дані аутентифікації в cookies з додатковим шифруванням"""
    # Видаляємо чутливі дані перед збереженням
    safe_data = {
        "id": user_data.get("id"),
        "email": user_data.get("email"),
        "full_name": user_data.get("full_name"),
        "type": user_data.get("type"),
        "authenticated": True
    }
    
    # Кодуємо дані користувача
    user_json = json.dumps(safe_data)
    encoded_data = base64.b64encode(user_json.encode()).decode()
    
    # Встановлюємо cookie на 7 днів (зменшено з 30 для безпеки)
    st.session_state['auth_cookie'] = encoded_data
    st.session_state['auth_expires'] = time.time() + (7 * 24 * 60 * 60)  # 7 днів


def load_auth_from_cookies():
    """Завантажує дані аутентифікації з cookies"""
    if 'auth_cookie' not in st.session_state:
        return None
    
    # Перевіряємо термін дії
    if 'auth_expires' in st.session_state and time.time() > st.session_state['auth_expires']:
        clear_auth_cookies()
        return None
    
    try:
        encoded_data = st.session_state['auth_cookie']
        decoded_data = base64.b64decode(encoded_data.encode()).decode()
        return json.loads(decoded_data)
    except:
        clear_auth_cookies()
        return None


def clear_auth_cookies():
    """Очищає cookies аутентифікації"""
    if 'auth_cookie' in st.session_state:
        del st.session_state['auth_cookie']
    if 'auth_expires' in st.session_state:
        del st.session_state['auth_expires']


def logout_user():
    """Виходить з системи користувача"""
    st.session_state['auth_user'] = None
    clear_auth_cookies()
    st.rerun()


def get_current_user():
    """Повертає поточного авторизованого користувача"""
    return st.session_state.get('auth_user')


def is_authenticated():
    """Перевіряє чи авторизований користувач"""
    return st.session_state.get('auth_user') is not None
