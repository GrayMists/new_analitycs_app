# app/utils/geocoding_service.py
from __future__ import annotations

import os
import streamlit as st
import pandas as pd
from typing import Optional, Dict, Any

# Optional online geocoding (wrapped in try/except)
try:
    from geopy.geocoders import Nominatim
    from geopy.extra.rate_limiter import RateLimiter
except Exception:  # geopy is optional
    Nominatim = None
    RateLimiter = None


class GeocodingService:
    """Сервіс для геокодування адрес"""
    
    def __init__(self):
        self.nominatim = Nominatim
        self.rate_limiter = RateLimiter
    
    @st.cache_data(show_spinner=False, ttl=3600)
    def load_coords_catalog(self, path: str) -> pd.DataFrame:
        """Завантажує каталог координат"""
        try:
            if os.path.exists(path):
                df = pd.read_csv(path)
                # normalize expected columns
                needed = {'addr_key','lat','lon','city','street','house_number'}
                for col in needed:
                    if col not in df.columns:
                        df[col] = None
                return df
        except Exception:
            pass
        return pd.DataFrame(columns=['addr_key','lat','lon','city','street','house_number'])
    
    def save_coords_catalog(self, df: pd.DataFrame, path: str) -> None:
        """Зберігає каталог координат"""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            # Avoid writing cached copy; write a fresh copy
            df.to_csv(path, index=False)
        except Exception as e:
            st.warning(f"Не вдалося зберегти довідник координат: {e}")
    
    def canonical_addr_key(self, city: str, street: str, house: str) -> str:
        """Створює канонічний ключ адреси"""
        city = str(city or '').strip().lower()
        street = str(street or '').strip().lower()
        house = str(house or '').strip().lower()
        return f"{city}|{street}|{house}"
    
    def attach_coords_from_catalog(self, df_addr: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
        """Додає координати з каталогу до DataFrame"""
        out = df_addr.copy()
        out['addr_key'] = out.apply(
            lambda r: self.canonical_addr_key(
                r.get('__city__',''), 
                r.get('__street__',''), 
                r.get('__house__','')
            ), 
            axis=1
        )
        
        if not catalog.empty:
            merged = out.merge(catalog[['addr_key','lat','lon']], on='addr_key', how='left')
        else:
            merged = out
            merged['lat'] = None
            merged['lon'] = None
        
        return merged
    
    def online_geocode_missing(self, df_addr: pd.DataFrame, user_agent: str = 'sales-analytics-app') -> pd.DataFrame:
        """Геокодує відсутні координати через Nominatim"""
        if self.nominatim is None or self.rate_limiter is None:
            st.info("Бібліотека geopy не встановлена — онлайн-геокодування вимкнено.")
            return df_addr
        
        geolocator = self.nominatim(user_agent=user_agent, timeout=10)
        geocode = self.rate_limiter(geolocator.geocode, min_delay_seconds=1)
        df = df_addr.copy()
        
        # Build full address string: City, Street House, Ukraine
        def _addr_str(row):
            city = str(row.get('__city__','')).strip()
            street = str(row.get('__street__','')).strip()
            house = str(row.get('__house__','')).strip()
            pieces = [p for p in [city, f"{street} {house}".strip()] if p]
            base = ', '.join(pieces)
            # You can change country if needed
            return f"{base}, Ukraine" if base else None
        
        need = df[df['lat'].isna() | df['lon'].isna()].copy()
        results = []
        
        for _, r in need.iterrows():
            q = _addr_str(r)
            lat = None
            lon = None
            if q:
                try:
                    loc = geocode(q)
                    if loc:
                        lat = loc.latitude
                        lon = loc.longitude
                except Exception:
                    pass
            results.append({'addr_key': r['addr_key'], 'lat': lat, 'lon': lon})
        
        if results:
            res_df = pd.DataFrame(results)
            df = df.merge(res_df, on='addr_key', how='left', suffixes=('','_new'))
            df['lat'] = df['lat'].fillna(df['lat_new'])
            df['lon'] = df['lon'].fillna(df['lon_new'])
            df.drop(columns=[c for c in ['lat_new','lon_new'] if c in df.columns], inplace=True)
        
        return df
