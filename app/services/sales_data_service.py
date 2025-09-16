# app/services/sales_data_service.py
from __future__ import annotations

import streamlit as st
import pandas as pd
from typing import Optional, Dict, Any, List
from app.io import loader_sales as data_loader
from app.io.supabase_client import init_supabase_client
from app.data import processing_sales as data_processing


class SalesDataService:
    """Сервіс для обробки даних продажів"""
    
    def __init__(self):
        self.client = init_supabase_client()
    
    @st.cache_data(show_spinner=False, ttl=1800)
    def fetch_sales_data(
        _self, 
        region_name: Optional[str], 
        territory: str, 
        line: str, 
        months: List[str]
    ) -> pd.DataFrame:
        """Завантажує дані продажів з кешуванням"""
        return data_loader.fetch_all_sales_data(
            region_name=region_name,
            territory=territory,
            line=line,
            months=months,
        )
    
    @st.cache_data(show_spinner=False, ttl=1800)
    def fetch_price_data(_self, region_id: int, months: List[int]) -> pd.DataFrame:
        """Завантажує дані цін з кешуванням"""
        return data_loader.fetch_price_data(region_id=region_id, months=months)
    
    @st.cache_data(show_spinner=False, ttl=1800)
    def fetch_regions(_self) -> List[Dict[str, Any]]:
        """Завантажує список регіонів"""
        if not _self.client:
            return []
        try:
            rows = _self.client.table("region").select("id,name").order("name").execute().data or []
            return [
                {"id": r.get("id"), "name": r.get("name")}
                for r in rows
                if r.get("id") and r.get("name")
            ]
        except Exception:
            return []
    
    @st.cache_data(show_spinner=False, ttl=1800)
    def fetch_territories(_self, region_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Завантажує список територій"""
        if not _self.client:
            return []
        try:
            q = _self.client.table("territory").select("name,technical_name,region_id").order("name")
            if region_id:
                q = q.eq("region_id", region_id)
            rows = q.execute().data or []
            territories = []
            for r in rows:
                n = (r.get("name") or "").strip()
                t = (r.get("technical_name") or "").strip()
                if n and t:
                    territories.append({"name": n, "technical_name": t, "region_id": r.get("region_id")})
            return territories
        except Exception:
            return []
    
    def ensure_numeric_cols(self, df: pd.DataFrame) -> pd.DataFrame:
        """Приводить year, month, decade, quantity до числових типів"""
        out = df.copy()
        for col in ("year", "month", "decade"):
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")
        if "quantity" in out.columns:
            out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce").fillna(0)
        return out
    
    def prepare_work_data(self, df_loaded: pd.DataFrame) -> pd.DataFrame:
        """Підготовляє дані для роботи"""
        df_work = df_loaded.copy()
        
        # гарантуємо month_int
        if 'month_int' not in df_work.columns:
            df_work['month_int'] = pd.to_numeric(df_work.get('month'), errors='coerce').astype('Int64')
        
        # уніфікуємо типи
        for col in ("year", "decade"):
            if col in df_work.columns:
                df_work[col] = pd.to_numeric(df_work[col], errors='coerce').astype('Int64')
        
        # нормалізація назв продуктів
        if 'product_name' in df_work.columns:
            df_work['product_name_clean'] = (
                df_work['product_name']
                .astype(str)
                .str.replace(r'^\s*[\d\W_]+', '', regex=True)
                .str.strip()
            )
        
        return df_work
    
    def add_revenue_data(self, df_work: pd.DataFrame, price_df: pd.DataFrame) -> pd.DataFrame:
        """Додає дані про доходи до DataFrame"""
        df_with_revenue = df_work.copy()
        if not price_df.empty:
            df_with_revenue = pd.merge(
                df_with_revenue,
                price_df,
                left_on=['product_name', 'month_int'],
                right_on=['product_name', 'month_int'],
                how='left'
            )
            df_with_revenue['revenue'] = df_with_revenue['quantity'] * df_with_revenue['price']
        else:
            df_with_revenue['revenue'] = 0.0
        return df_with_revenue
    
    def get_latest_decade_data(self, df_work: pd.DataFrame) -> tuple[pd.DataFrame, Optional[int], Optional[int], Optional[int]]:
        """Отримує дані останньої декади останнього місяця"""
        df_latest_decade = df_work.copy()
        last_decade = None
        cur_year = None
        cur_month = None
        
        if {'year','month_int','decade'}.issubset(df_work.columns):
            df_dec = df_work.dropna(subset=['year','month_int','decade']).copy()
            if not df_dec.empty:
                max_dec_per = df_dec.groupby(['year','month_int'])['decade'].transform('max')
                latest_per_month = df_dec[df_dec['decade'] == max_dec_per].copy()
                latest_pair = (
                    latest_per_month[['year','month_int']]
                    .drop_duplicates()
                    .sort_values(['year','month_int'])
                    .iloc[-1]
                )
                cur_year = int(latest_pair['year'])
                cur_month = int(latest_pair['month_int'])
                last_decade = int(
                    latest_per_month[
                        (latest_per_month['year'] == cur_year) & (latest_per_month['month_int'] == cur_month)
                    ]['decade'].max()
                )
                df_latest_decade = latest_per_month[
                    (latest_per_month['year'] == cur_year) & (latest_per_month['month_int'] == cur_month)
                ].copy()
        
        return df_latest_decade, last_decade, cur_year, cur_month
