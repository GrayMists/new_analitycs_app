# app/charts/plotly_sales.py
from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px

# Словник назв місяців українською (для підписів осі/легенд)
UKRAINIAN_MONTHS = {
    1: "Січень", 2: "Лютий", 3: "Березень", 4: "Квітень",
    5: "Травень", 6: "Червень", 7: "Липень", 8: "Серпень",
    9: "Вересень", 10: "Жовтень", 11: "Листопад", 12: "Грудень",
}


def plot_top_products_summary(df: pd.DataFrame) -> None:
    """
    Зводить продажі по продуктах і виводить:
      - таблицю загальних продажів по продуктах,
      - горизонтальний бар ТОП-5 із анотаціями.
    Рендерить напряму у Streamlit.
    """
    if df.empty:
        st.info("Немає даних для побудови зведення по продуктах.")
        return

    product_summary = (
        df.groupby('product_name')['quantity']
        .sum()
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={'quantity': 'Загальна кількість'})
    )
    top5_products = product_summary.head(5)

    df_top5_details = df[df['product_name'].isin(top5_products['product_name'])].copy()
    df_top5_details['month_name'] = pd.to_numeric(df_top5_details['month'], errors='coerce').map(UKRAINIAN_MONTHS)
    df_top5_agg = (
        df_top5_details
        .groupby(['product_name', 'month_name'])['quantity']
        .sum()
        .reset_index()
    )

    st.markdown("---")
    st.subheader("Аналіз продажів за продуктами")
    col1, col2 = st.columns([2, 3])

    with col1:
        st.markdown("**Загальні продажі**")
        st.dataframe(
            product_summary,
            column_config={
                "product_name": "Продукт",
                "Загальна кількість": st.column_config.NumberColumn("К-сть", format="%d"),
            },
            use_container_width=True,
            hide_index=True,
        )

    with col2:
        st.markdown("**ТОП-5 найбільш продаваних**")
        # Відсортований порядок для категорій (знизу-вгору)
        top_order = top5_products.sort_values(by='Загальна кількість', ascending=True)['product_name']
        fig_top = px.bar(
            df_top5_agg,
            y='product_name',
            x='quantity',
            orientation='h',
            labels={'quantity': 'Кількість', 'product_name': 'Продукт', 'month_name': 'Місяць'},
            category_orders={'product_name': top_order},
            color='month_name',
        )
        # Анотації сумарних значень біля стовпчиків
        totals_top = df_top5_agg.groupby('product_name')['quantity'].sum()
        for product in top_order:
            total_val = float(totals_top.get(product, 0))
            fig_top.add_annotation(
                y=product,
                x=total_val,
                text=f"<b>{int(total_val)}</b>",
                showarrow=False,
                xanchor='left',
                xshift=5,
                font=dict(color="black"),
            )
        fig_top.update_layout(
            title_text="Найбільш продавані",
            title_x=0.5,
            yaxis_title=None,
            xaxis_title=None,
            uniformtext_minsize=8,
            uniformtext_mode='hide',
            legend_title_text='Місяць',
            height=450,
            margin=dict(l=10, r=10, t=50, b=10),
        )
        st.plotly_chart(fig_top, use_container_width=True)


def plot_city_product_heatmap(pivot_df: pd.DataFrame) -> None:
    """
    Малює теплову карту 'Місто × Продукт' з готового зведеного DataFrame.
    Рендерить напряму у Streamlit.
    """
    if pivot_df.empty:
        st.info("Немає даних для побудови теплової карти.")
        return

    fig = px.imshow(
        pivot_df,
        text_auto=True,
        aspect="auto",
        color_continuous_scale='Viridis',
        labels=dict(x="Продукт", y="Місто", color="Кількість"),
    )
    fig.update_xaxes(side="top")
    fig.update_layout(height=600, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)


def plot_sales_dynamics(df: pd.DataFrame) -> None:
    """
    Адаптивна динаміка продажів та доходу.
      - >1 місяця: два лінійні графіки (quantity, revenue) поруч.
      - 1 місяць: два стовпчастих графіки за декадами (quantity, revenue) поруч.
    Рендерить напряму у Streamlit.
    """
    if df.empty:
        st.info("Немає даних для побудови динаміки продажів.")
        return

    st.subheader("Динаміка продажів та доходу")

    df_chart = df.copy()
    has_revenue = 'revenue' in df_chart.columns and not df_chart['revenue'].isnull().all()
    # кількість різних (year, month)
    unique_months_count = df_chart.groupby(['year', 'month']).ngroups

    if unique_months_count > 1:
        # беремо запис з максимальним decade у кожному місяці
        max_decade_per_month = df_chart.groupby(['year', 'month'])['decade'].transform('max')
        df_monthly_totals = df_chart[df_chart['decade'] == max_decade_per_month].copy()

        agg_funcs = {'quantity': 'sum'}
        if has_revenue:
            agg_funcs['revenue'] = 'sum'

        monthly_data = (
            df_monthly_totals
            .groupby(['year', 'month'])
            .agg(agg_funcs)
            .reset_index()
            .sort_values(by=['year', 'month'])
        )
        monthly_data['month_label'] = pd.to_numeric(monthly_data['month'], errors='coerce').map(UKRAINIAN_MONTHS)
        monthly_data['x_axis_label'] = monthly_data['month_label'] + ' ' + monthly_data['year'].astype(int).astype(str)

        col1, col2 = st.columns(2)
        with col1:
            fig_qty = px.line(
                monthly_data,
                x='x_axis_label',
                y='quantity',
                markers=True,
                title="Динаміка продажів, уп.",
                labels={'x_axis_label': '', 'quantity': 'Кількість'},
            )
            fig_qty.update_layout(yaxis_title=None, xaxis_title=None, showlegend=False, height=420,
                                  margin=dict(l=10, r=10, t=50, b=10))
            fig_qty.update_xaxes(type='category')
            st.plotly_chart(fig_qty, use_container_width=True)

        with col2:
            if has_revenue:
                fig_rev = px.line(
                    monthly_data,
                    x='x_axis_label',
                    y='revenue',
                    markers=True,
                    title="Динаміка доходу, грн",
                    labels={'x_axis_label': '', 'revenue': 'Дохід'},
                )
                fig_rev.update_layout(yaxis_title=None, xaxis_title=None, showlegend=False, height=420,
                                      margin=dict(l=10, r=10, t=50, b=10))
                fig_rev.update_xaxes(type='category')
                st.plotly_chart(fig_rev, use_container_width=True)
            else:
                st.info("Дані про дохід відсутні.")

    else:
        # один місяць — показуємо за декадами
        sales_by_decade = (
            df_chart.groupby('decade')['quantity']
            .sum()
            .reset_index()
            .sort_values('decade')
        )
        sales_by_decade['actual_quantity'] = sales_by_decade['quantity'].diff().fillna(sales_by_decade['quantity'])
        sales_by_decade['x_axis_label'] = sales_by_decade['decade'].astype(int).astype(str) + "-а декада"

        col1, col2 = st.columns(2)
        with col1:
            fig_qty = px.bar(
                sales_by_decade,
                x='x_axis_label',
                y='actual_quantity',
                text='actual_quantity',
                title="Продажі за декадами, уп.",
                labels={'x_axis_label': '', 'actual_quantity': 'Кількість'},
            )
            fig_qty.update_traces(texttemplate='%{text:.0f}', textposition='outside', textfont_color='black')
            fig_qty.update_layout(uniformtext_minsize=8, showlegend=False, yaxis_title=None, xaxis_title=None,
                                  height=420, margin=dict(l=10, r=10, t=50, b=10))
            st.plotly_chart(fig_qty, use_container_width=True)

        with col2:
            if has_revenue:
                revenue_by_decade = (
                    df_chart.groupby('decade')['revenue']
                    .sum()
                    .reset_index()
                    .sort_values('decade')
                )
                revenue_by_decade['actual_revenue'] = revenue_by_decade['revenue'].diff().fillna(revenue_by_decade['revenue'])
                revenue_by_decade['x_axis_label'] = revenue_by_decade['decade'].astype(int).astype(str) + "-а декада"

                fig_rev = px.bar(
                    revenue_by_decade,
                    x='x_axis_label',
                    y='actual_revenue',
                    text='actual_revenue',
                    title="Дохід за декадами, грн",
                    labels={'x_axis_label': '', 'actual_revenue': 'Дохід'},
                )
                fig_rev.update_traces(texttemplate='%{text:,.0f}', textposition='outside', textfont_color='black')
                fig_rev.update_layout(uniformtext_minsize=8, showlegend=False, yaxis_title=None, xaxis_title=None,
                                      height=420, margin=dict(l=10, r=10, t=50, b=10))
                st.plotly_chart(fig_rev, use_container_width=True)
            else:
                st.info("Дані про дохід відсутні.")