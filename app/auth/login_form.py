# app/auth/login_form.py
import streamlit as st
from .authentication import authenticate_user, save_auth_to_cookies


def render_login_form():
    """Відображає форму логіну"""
    st.subheader("Вхід в систему")
    
    email = st.text_input("Email")
    password = st.text_input("Пароль", type="password")
    remember_me = st.checkbox("Запам'ятати мене", value=True)
    
    if st.button("Увійти"):
        if email and password:
            user_data = authenticate_user(email, password)
            if user_data:
                st.session_state['auth_user'] = user_data
                
                if remember_me:
                    save_auth_to_cookies(user_data)
                    st.success("Успішно увійшли в систему! Сесія збережена на 30 днів.")
                else:
                    st.success("Успішно увійшли в систему!")
                
                st.rerun()
            else:
                st.error("Помилка аутентифікації. Перевірте дані.")
        else:
            st.warning("Будь ласка, введіть email та пароль.")
