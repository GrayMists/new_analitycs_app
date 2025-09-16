# app/utils/sales_formatters.py
from __future__ import annotations

import streamlit as st
import pandas as pd
from typing import Any


class SalesFormatters:
    """Утиліти для форматування та стилізації даних продажів"""
    
    @staticmethod
    def format_currency(value: float) -> str:
        """Форматує валюту"""
        return f"{value:,.2f} грн"
    
    @staticmethod
    def format_percentage(value: float) -> str:
        """Форматує відсотки"""
        return f"{value:.1f}%"
    
    @staticmethod
    def format_number(value: float) -> str:
        """Форматує числа"""
        return f"{value:,.0f}"
    
    @staticmethod
    def style_product_summary_table(df: pd.DataFrame) -> Any:
        """Стилізує таблицю зведення по продуктах"""
        return (
            df.style
            .format({'К-сть': '{:,.0f}', 'Сума': '{:,.2f} грн'})
            .background_gradient(cmap='Blues', subset=['К-сть'])
            .background_gradient(cmap='Greens', subset=['Сума'])
        )
    
    @staticmethod
    def style_abc_table(df: pd.DataFrame, metric: str) -> Any:
        """Стилізує таблицю ABC аналізу"""
        if metric == 'revenue':
            return (
                df.style
                .format({'Значення':'{:,.2f} грн','Частка, %':'{:,.2f}','Кумулятивна частка, %':'{:,.2f}'})
                .background_gradient(cmap='Greens', subset=['Значення'])
                .background_gradient(cmap='Blues', subset=['Частка, %'])
            )
        else:  # quantity
            return (
                df.style
                .format({'Значення':'{:,.0f}','Частка, %':'{:,.2f}','Кумулятивна частка, %':'{:,.2f}'})
                .background_gradient(cmap='Blues', subset=['Значення'])
                .background_gradient(cmap='Greens', subset=['Частка, %'])
            )
    
    @staticmethod
    def style_top_pharmacies_table(df: pd.DataFrame, sort_by: str) -> Any:
        """Стилізує таблицю топ аптек"""
        if sort_by == 'revenue':
            return (
                df.style
                .format({'Сума':'{:,.2f} грн'})
                .background_gradient(cmap='Greens', subset=['Сума'])
            )
        else:  # quantity
            return (
                df.style
                .format({'К-сть':'{:,.0f}'})
                .background_gradient(cmap='Blues', subset=['К-сть'])
            )
    
    @staticmethod
    def style_growth_table(df: pd.DataFrame, metric: str) -> Any:
        """Стилізує таблицю росту"""
        if metric == 'revenue':
            return (
                df.style
                .format({'rev_last':'{:,.2f}','rev_prev':'{:,.2f}','Δ₴':'{:,.2f}','Δ%':'{:,.1f}'})
                .background_gradient(cmap='Greens', subset=['Δ₴'])
            )
        else:  # quantity
            return (
                df.style
                .format({'qty_last':'{:,.0f}','qty_prev':'{:,.0f}','Δк-сть':'{:,.0f}','Δ%':'{:,.1f}'})
                .background_gradient(cmap='Blues', subset=['Δк-сть'])
            )
    
    @staticmethod
    def style_top_products_table(df: pd.DataFrame, metric: str) -> Any:
        """Стилізує таблицю топ продуктів"""
        if metric == 'quantity':
            return (
                df.style
                .format({'К-сть': '{:,.0f}'})
                .background_gradient(cmap='Blues', subset=['К-сть'])
            )
        else:  # revenue
            return (
                df.style
                .format({'Сума': '{:,.2f} грн'})
                .background_gradient(cmap='Greens', subset=['Сума'])
            )
    
    @staticmethod
    def create_kpi_metrics(kpis: dict) -> None:
        """Створює KPI метрики"""
        kpi_row = st.columns(5)
        
        with kpi_row[0]:
            st.metric("Загальна кількість (ост. декада)", f"{kpis['total_quantity']:,}")
        with kpi_row[1]:
            st.metric("Загальна сума (ост. декада)", f"{kpis['total_revenue_sum']:,.2f} грн")
        with kpi_row[2]:
            st.metric("Середній чек (період)", f"{kpis['avg_check_top']:,.2f} грн")
        with kpi_row[3]:
            st.metric("Сер. к-сть/клієнта (період)", f"{kpis['avg_qty_per_client_top']:,.2f}")
        with kpi_row[4]:
            st.metric("Унікальних клієнтів (період)", f"{kpis['uniq_clients_top']:,}")
    
    @staticmethod
    def format_forecast_data(forecast_data: dict) -> pd.DataFrame:
        """Форматує дані прогнозу"""
        return pd.DataFrame({
            'Показник': ['Прогноз, грн', '95% Low', '95% High', 'Робочі дні пройшли', 'Лишилось робочих днів'],
            'Значення': [
                f"{forecast_data['point_forecast_revenue']:,.2f}",
                f"{forecast_data['conf_interval_revenue'][0]:,.0f}",
                f"{forecast_data['conf_interval_revenue'][1]:,.0f}",
                forecast_data['workdays_passed'],
                forecast_data['workdays_left'],
            ],
        })
    
    @staticmethod
    def format_backtest_data(rows: list) -> Any:
        """Форматує дані ретроспективного тестування"""
        if not rows:
            return None
        
        df_backtest = pd.DataFrame(rows)
        
        # Безпечне форматування числових колонок
        num_cols_bt = ['Прогноз, грн', '95% Low', '95% High', 'Факт (грн)', 'Похибка, грн', 'MAPE, %']
        for c in num_cols_bt:
            if c in df_backtest.columns:
                df_backtest[c] = pd.to_numeric(df_backtest[c], errors='coerce')
        
        _fmt2 = lambda x: "" if pd.isna(x) else f"{x:,.2f}"
        
        return (
            df_backtest.style
            .format({
                'Прогноз, грн': _fmt2,
                '95% Low': _fmt2,
                '95% High': _fmt2,
                'Факт (грн)': _fmt2,
                'Похибка, грн': _fmt2,
                'MAPE, %': _fmt2,
            })
            .background_gradient(cmap='Greens', subset=['Факт (грн)'] if 'Факт (грн)' in df_backtest.columns else None)
            .background_gradient(cmap='Blues', subset=['Прогноз, грн'] if 'Прогноз, грн' in df_backtest.columns else None)
            .background_gradient(cmap='Reds', subset=['Похибка, грн'] if 'Похибка, грн' in df_backtest.columns else None)
        )
