# app/ui/navigation.py
import streamlit as st
from streamlit_option_menu import option_menu
from app.auth.authentication import logout_user, get_current_user


def render_navigation_menu():
    """Відображає меню навігації між сторінками"""
    with st.sidebar:
        # Показуємо інформацію про користувача
        user = get_current_user()
        if user:
            st.info(f"👤 {user.get('email', 'Користувач')}")
            if user.get('full_name'):
                st.info(f"👤 {user['full_name']}")
        
        # Формуємо список опцій меню залежно від типу користувача
        menu_options = [
            "🏠 Головна", 
            "📈 Продажі", 
            "👨‍⚕️ Лікарі", 
            "🏪 Аптеки"
        ]
        
        # Додаємо Excel тільки для адміністраторів
        user_type = user.get('type', '').lower()
        if user_type == 'admin':
            menu_options.append("📊 Excel")
        
        # Меню навігації
        selected = option_menu(
            menu_title="📊 Analytics App",
            options=menu_options,
            icons=[
                "house", 
                "graph-up", 
                "person-badge", 
                "building"
            ] + (["file-earmark-spreadsheet"] if user_type == 'admin' else []),
            menu_icon="cast",
            default_index=0,
            key="main_navigation_menu",  # Додаємо унікальний ключ
            styles={
                "container": {"padding": "0!important", "background-color": "#fafafa"},
                "icon": {"color": "orange", "font-size": "25px"}, 
                "nav-link": {
                    "font-size": "16px", 
                    "text-align": "left", 
                    "margin":"0px", 
                    "--hover-color": "#eee"
                },
                "nav-link-selected": {"background-color": "#02ab21"},
            }
        )
        
        # Кнопка виходу
        st.divider()
        if st.button("🚪 Вийти", use_container_width=True, key="logout_button"):
            logout_user()
    
    return selected


def handle_navigation(selected_page):
    """Обробляє навігацію між сторінками"""
    if selected_page == "🏠 Головна":
        # Головна сторінка вже відображається в home.py
        pass
    elif selected_page == "📈 Продажі":
        from app.views.sales_page import show_sales_page
        show_sales_page()
    elif selected_page == "👨‍⚕️ Лікарі":
        from app.views.doctor_points_page import show_doctor_points_page
        show_doctor_points_page()
    elif selected_page == "🏪 Аптеки":
        from app.views.drug_store_page import show_drug_store_page
        show_drug_store_page()
    elif selected_page == "📊 Excel":
        from app.views.excel_page import show_excel_page
        show_excel_page()
