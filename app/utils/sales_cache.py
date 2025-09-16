# app/utils/sales_cache.py
from __future__ import annotations

import streamlit as st
from typing import Dict, Any, Tuple, Optional, List


class SalesCacheManager:
    """Менеджер кешування для даних продажів"""
    
    def __init__(self):
        self._init_session_cache()
    
    def _init_session_cache(self):
        """Ініціалізує кеш в session state"""
        if "_sales_session_cache" not in st.session_state:
            st.session_state["_sales_session_cache"] = {}
        if "_price_session_cache" not in st.session_state:
            st.session_state["_price_session_cache"] = {}
    
    def get_session_cache(self) -> Tuple[Dict, Dict]:
        """Отримує кеш з session state"""
        return st.session_state["_sales_session_cache"], st.session_state["_price_session_cache"]
    
    def make_sales_key(self, region_name: Optional[str], territory: str, line: str, months: List[str]) -> Tuple:
        """Створює ключ для кешування даних продажів"""
        _DEF_ALL = "(усі)"
        return (
            region_name or _DEF_ALL,
            territory or "Всі",
            line or "Всі",
            tuple(sorted(months)) if months else None,
        )
    
    def make_price_key(self, region_id: int, months: List[int]) -> Tuple:
        """Створює ключ для кешування даних цін"""
        return (region_id, tuple(sorted(months)))
    
    def get_cached_sales_data(self, key: Tuple) -> Optional[Any]:
        """Отримує кешовані дані продажів"""
        sales_cache, _ = self.get_session_cache()
        return sales_cache.get(key)
    
    def set_cached_sales_data(self, key: Tuple, data: Any):
        """Зберігає дані продажів в кеш"""
        sales_cache, _ = self.get_session_cache()
        sales_cache[key] = data
    
    def get_cached_price_data(self, key: Tuple) -> Optional[Any]:
        """Отримує кешовані дані цін"""
        _, price_cache = self.get_session_cache()
        return price_cache.get(key)
    
    def set_cached_price_data(self, key: Tuple, data: Any):
        """Зберігає дані цін в кеш"""
        _, price_cache = self.get_session_cache()
        price_cache[key] = data
    
    def invalidate_cache(self):
        """Очищає весь кеш"""
        st.session_state["_sales_session_cache"] = {}
        st.session_state["_price_session_cache"] = {}
    
    def invalidate_sales_cache(self):
        """Очищає кеш продажів"""
        st.session_state["_sales_session_cache"] = {}
    
    def invalidate_price_cache(self):
        """Очищає кеш цін"""
        st.session_state["_price_session_cache"] = {}
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Отримує статистику кешу"""
        sales_cache, price_cache = self.get_session_cache()
        return {
            "sales_cache_size": len(sales_cache),
            "price_cache_size": len(price_cache),
            "total_cache_size": len(sales_cache) + len(price_cache)
        }
