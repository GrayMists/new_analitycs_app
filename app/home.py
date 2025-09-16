# app/home.py
from __future__ import annotations
import os, sys
import streamlit as st
from streamlit_option_menu import option_menu

# Приховуємо стандартну бокову панель Streamlit
st.set_page_config(
    page_title="Analytics App",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Завантажуємо CSS стилі для приховування стандартної навігації
def load_css():
    with open(".streamlit/style.css") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()

# Додаємо корінь проєкту до sys.path для імортів
APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(APP_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from app.auth.authentication import load_auth_from_cookies, logout_user, get_current_user, is_authenticated
from app.auth.login_form import render_login_form
from app.dashboard.user_dashboard import display_user_profile, display_sales_data
from app.ui.navigation import render_navigation_menu, handle_navigation


def render_home_page():
    """Відображає головну сторінку з дашбордом користувача"""
    st.title("🏠 Головна сторінка")
    
    user = get_current_user()
    if user:
        profile_data = display_user_profile(user)
        display_sales_data(profile_data, user)
    else:
        st.info("Будь ласка, увійдіть в систему для доступу до дашборду.")


def render_page_content(selected_page):
    """Відображає контент вибраної сторінки"""
    if selected_page == "🏠 Головна":
        render_home_page()
    else:
        # Для всіх інших сторінок використовуємо навігацію
        handle_navigation(selected_page)


# Основна логіка додатку
def main():
    """Головна функція додатку"""
    # Ініціалізація аутентифікації
    if 'auth_user' not in st.session_state:
        saved_auth = load_auth_from_cookies()
        if saved_auth:
            st.session_state['auth_user'] = saved_auth
        else:
            st.session_state['auth_user'] = None

    # Перевіряємо чи користувач авторизований
    if is_authenticated():
        # Показуємо меню навігації та контент
        selected_page = render_navigation_menu()
        render_page_content(selected_page)
    else:
        # Показуємо форму логіну
        st.title("📊 Analytics App")
        render_login_form()


if __name__ == "__main__":
    main()
