# app/services/sales_charts_service.py
from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from typing import Optional, List
from app.utils import UKRAINIAN_MONTHS


class SalesChartsService:
    """Сервіс для створення графіків продажів"""
    
    def render_product_quantity_chart(self, df_work: pd.DataFrame, df_latest_decade: pd.DataFrame, 
                                     sel_months_int: List[int], last_decade: Optional[int], 
                                     cur_month: Optional[int], cur_year: Optional[int]) -> None:
        """Рендерить графік кількості по продуктах"""
        if len(sel_months_int) > 1:
            self._render_multi_month_quantity_chart(df_work, sel_months_int)
        else:
            self._render_single_month_quantity_chart(df_latest_decade, last_decade, cur_month, cur_year)
    
    def _render_multi_month_quantity_chart(self, df_work: pd.DataFrame, sel_months_int: List[int]) -> None:
        """Рендерить графік для кількох місяців"""
        prod_col_chart = 'product_name_clean' if 'product_name_clean' in df_work.columns else 'product_name'
        
        # Drop first 3 symbols from names for chart labels
        df_work = df_work.copy()
        df_work[prod_col_chart] = df_work[prod_col_chart].astype(str).str[3:].str.strip()
        
        # Агрегуємо ТІЛЬКИ по останній декаді кожного обраного місяця
        if {'year','month_int','decade'}.issubset(df_work.columns):
            dfm = (
                df_work[df_work['month_int'].isin(sel_months_int)]
                .dropna(subset=['year','month_int','decade'])
                .copy()
            )
            if not dfm.empty:
                max_dec = dfm.groupby(['year','month_int'])['decade'].transform('max')
                df_lastdec = dfm[dfm['decade'] == max_dec].copy()
                multi_df = (
                    df_lastdec
                    .groupby([prod_col_chart, 'month_int'], as_index=False)['quantity']
                    .sum()
                    .rename(columns={'quantity': 'total_quantity'})
                )
            else:
                multi_df = pd.DataFrame()
        else:
            # Фолбек
            multi_df = (
                df_work[df_work['month_int'].isin(sel_months_int)]
                .groupby([prod_col_chart, 'month_int'], as_index=False)['quantity']
                .sum()
                .rename(columns={'quantity': 'total_quantity'})
            )
        
        if not multi_df.empty:
            multi_df['Місяць'] = multi_df['month_int'].astype(int).map(lambda m: UKRAINIAN_MONTHS.get(int(m), str(m)))
            
            # Впорядкуємо продукти за загальною к-стю
            order_df = multi_df.groupby(prod_col_chart, as_index=False)['total_quantity'].sum().sort_values('total_quantity', ascending=False)
            category_order = order_df[prod_col_chart].tolist()
            
            st.subheader("Кількість по продуктах (останні декади обраних місяців)")
            fig_qty_grouped = px.bar(
                multi_df,
                x=prod_col_chart,
                y='total_quantity',
                color='Місяць',
                barmode='group',
                category_orders={prod_col_chart: category_order},
                labels={prod_col_chart: 'Продукт', 'total_quantity': 'К-сть'},
                text='total_quantity',
            )
            fig_qty_grouped.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
            fig_qty_grouped.update_layout(
                xaxis_tickangle=-45,
                margin=dict(l=10, r=10, t=10, b=80),
                height=550,
            )
            st.plotly_chart(fig_qty_grouped, use_container_width=True)
        else:
            st.info("Немає даних для побудови діаграми за кілька місяців.")
    
    def _render_single_month_quantity_chart(self, df_latest_decade: pd.DataFrame, last_decade: Optional[int], 
                                          cur_month: Optional[int], cur_year: Optional[int]) -> None:
        """Рендерить графік для одного місяця"""
        prod_col_chart = 'product_name_clean' if 'product_name_clean' in df_latest_decade.columns else 'product_name'
        
        # Drop first 3 symbols from names for chart labels
        df_latest_decade = df_latest_decade.copy()
        df_latest_decade[prod_col_chart] = df_latest_decade[prod_col_chart].astype(str).str[3:].str.strip()
        
        qty_chart_df = (
            df_latest_decade.groupby(prod_col_chart, as_index=False)['quantity']
            .sum()
            .rename(columns={'quantity': 'total_quantity'})
            .sort_values('total_quantity', ascending=False)
        )
        
        if not qty_chart_df.empty:
            title_text = "Кількість по продуктах (остання декада)"
            if last_decade is not None and cur_month is not None and cur_year is not None:
                title_text += f" — декада {int(last_decade)}, {UKRAINIAN_MONTHS.get(int(cur_month), str(cur_month))} {cur_year}"
            
            st.subheader(title_text)
            fig_qty_overall = px.bar(
                qty_chart_df,
                x=prod_col_chart,
                y='total_quantity',
                labels={prod_col_chart: 'Продукт', 'total_quantity': 'К-сть'},
                text='total_quantity',
            )
            fig_qty_overall.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
            fig_qty_overall.update_layout(
                xaxis_tickangle=-45,
                margin=dict(l=10, r=10, t=10, b=80),
                height=550,
            )
            st.plotly_chart(fig_qty_overall, use_container_width=True)
        else:
            st.info("Немає даних для побудови діаграми (остання декада).")
    
    def render_city_revenue_chart(self, df_city_src: pd.DataFrame) -> None:
        """Рендерить комбіновану діаграму виручки по містах"""
        if 'revenue' not in df_city_src.columns:
            df_city_src['revenue'] = 0.0
        
        city_col2 = 'city' if 'city' in df_city_src.columns else None
        if city_col2:
            by_city = (
                df_city_src.groupby(city_col2, as_index=False)[['revenue','quantity']]
                .sum()
                .sort_values('revenue', ascending=False)
                .head(30)
            )
            
            if not by_city.empty:
                st.subheader("Виручка по містах (+ кількість)")
                fig_combo = go.Figure()
                
                # Бар по виручці
                fig_combo.add_trace(go.Bar(x=by_city[city_col2], y=by_city['revenue'], name='Сума'))
                
                # Лінія по кількості на вторинній осі
                fig_combo.add_trace(go.Scatter(x=by_city[city_col2], y=by_city['quantity'], name='К-сть', mode='lines+markers', yaxis='y2'))
                
                fig_combo.update_layout(
                    yaxis=dict(title='Сума, грн'),
                    yaxis2=dict(title='К-сть', overlaying='y', side='right'),
                    xaxis=dict(tickangle=-45),
                    margin=dict(l=10, r=10, t=10, b=80), height=550,
                    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
                )
                st.plotly_chart(fig_combo, use_container_width=True)
            else:
                st.info("Немає даних для міст.")
        else:
            st.info("Колонка міста відсутня у вибраному зрізі.")
    
    def render_trend_chart(self, df_period_trend: pd.DataFrame) -> None:
        """Рендерить трендовий графік по декадах"""
        st.subheader("Тренд по декадах у вибраному періоді")
        
        if 'revenue' not in df_period_trend.columns:
            df_period_trend = df_period_trend.copy()
            df_period_trend['revenue'] = 0.0
        
        if {'year','month_int','decade','revenue'}.issubset(df_period_trend.columns):
            trend_df = (
                df_period_trend
                .dropna(subset=['year','month_int','decade'])
                .groupby(['year','month_int','decade'], as_index=False)[['revenue','quantity']].sum()
            )
            
            if not trend_df.empty:
                trend_df['Місяць'] = trend_df['month_int'].astype(int).map(lambda m: UKRAINIAN_MONTHS.get(int(m), str(m)))
                fig_trend = px.line(
                    trend_df.sort_values(['year','month_int','decade']),
                    x='decade',
                    y='revenue',
                    color='Місяць',
                    markers=True,
                    labels={'decade':'Декада','revenue':'Сума'},
                )
                fig_trend.update_layout(margin=dict(l=10,r=10,t=10,b=10), height=550)
                st.plotly_chart(fig_trend, use_container_width=True)
            else:
                st.info("Недостатньо даних для побудови тренду по декадах.")
        else:
            st.info("Немає необхідних колонок (year, month_int, decade, revenue) для тренду по декадах.")
    
    def render_bcg_matrix(self, bcg_data: pd.DataFrame) -> None:
        """Рендерить BCG матрицю"""
        st.subheader("Матриця BCG (обсяг vs темп росту)")
        # Безпечні перевірки: None, пустий, необхідні колонки
        if bcg_data is None or not isinstance(bcg_data, pd.DataFrame) or bcg_data.empty:
            st.info("Для побудови матриці BCG потрібно щонайменше 2 обрані місяці або достатньо даних.")
            return

        required_cols = {'Препарат', 'qty_last', 'growth_%', 'Категорія'}
        missing = required_cols - set(bcg_data.columns)
        if missing:
            st.warning(f"Некоректні дані для BCG-матриці: відсутні колонки {sorted(missing)}")
            return

        # Перевіряємо, чи є хоча б один валідний числовий рядок для x/y
        try:
            x_vals = pd.to_numeric(bcg_data['qty_last'], errors='coerce')
            y_vals = pd.to_numeric(bcg_data['growth_%'], errors='coerce')
        except Exception:
            st.warning("Неможливо інтерпретувати числові поля у BCG-даних.")
            return

        if x_vals.dropna().empty or y_vals.dropna().empty:
            st.info("Недостатньо числових даних для побудови BCG-матриці.")
            return

        # Побудова графіка (безпечні hover-поля: включає лише існуючі стовпці)
        hover = {
            'Препарат': True,
            'qty_last': ':.0f',
            'qty_prev': ':.0f',
            'growth_%': ':.1f',
            'Категорія': False,
        }
        # відфільтруємо hover, якщо деяких колонок немає
        hover = {k: v for k, v in hover.items() if k in bcg_data.columns}

        # Підготуємо окремий DataFrame для побудови — залишимо лише потрібні/hover колонки
        keep_cols = ['Препарат', 'qty_last', 'growth_%', 'qty_prev', 'Категорія']
        keep_cols += [c for c in hover.keys() if c not in keep_cols and c in bcg_data.columns]
        df_plot = bcg_data.copy()[[c for c in keep_cols if c in bcg_data.columns]]

        # Приведемо типи: числові колонки — до numeric, інші — до простих скалярів (str)
        for num_c in ['qty_last', 'qty_prev', 'growth_%']:
            if num_c in df_plot.columns:
                df_plot[num_c] = pd.to_numeric(df_plot[num_c], errors='coerce')

        # Приводимо складні об'єкти (list/dict) до рядків, щоб Plotly не падав
        for c in df_plot.select_dtypes(include=['object']).columns:
            df_plot[c] = df_plot[c].apply(lambda v: v if (v is None or pd.isna(v)) else (v if isinstance(v, (str, int, float)) else str(v)))

        # Заповнимо категорію дефолтним значенням, якщо відсутня
        if 'Категорія' in df_plot.columns:
            df_plot['Категорія'] = df_plot['Категорія'].fillna('Невідомо')

        # Видалимо рядки без числових x/y
        if 'qty_last' in df_plot.columns and 'growth_%' in df_plot.columns:
            df_plot = df_plot.dropna(subset=['qty_last', 'growth_%'])
        elif 'qty_last' in df_plot.columns:
            df_plot = df_plot.dropna(subset=['qty_last'])

        if df_plot.empty:
            st.info("Після очищення даних для BCG не залишилось рядків з валідними числами.")
            return

        fig_bcg = px.scatter(
            df_plot,
            x='qty_last',
            y='growth_%',
            text='Препарат' if 'Препарат' in df_plot.columns else None,
            color='Категорія' if 'Категорія' in df_plot.columns else None,
            category_orders={'Категорія': ['Падіння (<0%)', 'Стабільно (0–3%)', 'Ріст (>3%)']},
            color_discrete_map={
                'Падіння (<0%)': '#d62728',   # red
                'Стабільно (0–3%)': '#ffbf00', # yellow
                'Ріст (>3%)': '#2ca02c',      # green
            },
            hover_data=hover,
            labels={
                'qty_last':'Обсяг (к-сть, останній місяць)',
                'growth_%':'Темп росту, %',
                'qty_prev':'Обсяг (к-сть, попередній місяць)',
                'Категорія':'Статус',
            },
        )
        fig_bcg.update_traces(textposition='top center')
        fig_bcg.update_layout(margin=dict(l=10,r=10,t=10,b=10), height=550, legend_title_text='Статус')
        st.plotly_chart(fig_bcg, use_container_width=True)
