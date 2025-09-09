# app/home.py
from __future__ import annotations
import os, sys
import streamlit as st

st.title("Welcome to the Analytics App")
if 'auth_user' not in st.session_state:
    st.session_state['auth_user'] = None

if st.session_state['auth_user']:
    st.success(f"Logged in as {st.session_state['auth_user']['email']}")
    if st.button("Logout"):
        st.session_state['auth_user'] = None
        st.rerun()
else:
    st.subheader("Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        # Placeholder for authentication logic
        # On success:
        st.session_state['auth_user'] = {"email": email}
        st.rerun()

    st.subheader("Register")
    new_email = st.text_input("New Email", key="reg_email")
    new_password = st.text_input("New Password", type="password", key="reg_password")
    if st.button("Register"):
        # Placeholder for registration logic
        st.success("Registration successful. Please log in.")

    st.subheader("Magic Link")
    magic_email = st.text_input("Email for Magic Link", key="magic_email")
    if st.button("Send Magic Link"):
        # Placeholder for magic link logic
        st.info(f"Magic link sent to {magic_email}. Please check your email.")