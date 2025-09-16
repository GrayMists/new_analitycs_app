# app/services/sales_analytics_service.py
from __future__ import annotations

import pandas as pd
from typing import Dict, Any, List, Tuple
from app.data import processing_sales as data_processing


class SalesAnalyticsService:
    """Сервіс для аналітичних розрахунків продажів"""
    
    def calculate_kpis(self, df_latest_decade: pd.DataFrame, df_latest_with_revenue: pd.DataFrame, 
                      df_period_top: pd.DataFrame) -> Dict[str, Any]:
        """Розраховує основні KPI"""
        # Загальна кількість (остання декада)
        if not df_latest_decade.empty:
            total_quantity = int(pd.to_numeric(df_latest_decade.get('quantity', pd.Series(dtype=float)), errors='coerce').fillna(0).sum())
        else:
            total_quantity = 0
        
        # Загальна сума (остання декада)
        if not df_latest_with_revenue.empty and 'revenue' in df_latest_with_revenue.columns:
            total_revenue_sum = float(pd.to_numeric(df_latest_with_revenue['revenue'], errors='coerce').fillna(0).sum())
        else:
            total_revenue_sum = 0.0
        
        # Показники за весь обраний період
        if 'revenue' not in df_period_top.columns:
            df_period_top['revenue'] = 0.0
        
        total_qty_period_top = float(pd.to_numeric(df_period_top.get('quantity', pd.Series(dtype=float)), errors='coerce').fillna(0).sum())
        total_rev_period_top = float(pd.to_numeric(df_period_top.get('revenue', pd.Series(dtype=float)), errors='coerce').fillna(0).sum())
        avg_check_top = (total_rev_period_top / total_qty_period_top) if total_qty_period_top > 0 else 0.0
        
        # Унікальні клієнти
        uniq_clients_top = self._calculate_unique_clients(df_period_top)
        avg_qty_per_client_top = (total_qty_period_top / uniq_clients_top) if uniq_clients_top > 0 else 0.0
        
        return {
            'total_quantity': total_quantity,
            'total_revenue_sum': total_revenue_sum,
            'avg_check_top': avg_check_top,
            'avg_qty_per_client_top': avg_qty_per_client_top,
            'uniq_clients_top': uniq_clients_top
        }
    
    def _calculate_unique_clients(self, df: pd.DataFrame) -> int:
        """Розраховує кількість унікальних клієнтів"""
        client_cols_pref = ['client', 'full_address_processed', 'pharmacy', 'client_name']
        client_col_top = next((c for c in client_cols_pref if c in df.columns), None)
        
        if {'city','street','house_number'}.issubset(df.columns):
            addr_series = (
                df['city'].fillna('').astype(str).str.strip() + '|' +
                df['street'].fillna('').astype(str).str.strip() + '|' +
                df['house_number'].fillna('').astype(str).str.strip()
            )
            return int(addr_series.nunique())
        elif 'full_address_processed' in df.columns:
            return int(df['full_address_processed'].astype(str).str.strip().nunique())
        elif 'address' in df.columns:
            return int(df['address'].astype(str).str.strip().nunique())
        elif client_col_top:
            return int(df[client_col_top].astype(str).str.strip().nunique())
        else:
            return 0
    
    def calculate_product_summary(self, df_latest_decade: pd.DataFrame, df_latest_with_revenue: pd.DataFrame) -> pd.DataFrame:
        """Розраховує зведення по продуктах"""
        # вибираємо колонку продукту (очищену, якщо доступна)
        prod_col = 'product_name_clean' if 'product_name_clean' in df_latest_decade.columns else 'product_name'
        
        # кількість
        qty_by_product = (
            df_latest_decade.groupby(prod_col, as_index=False)['quantity']
            .sum()
            .rename(columns={'quantity': 'К-сть'})
        )
        
        # сума
        if 'revenue' in df_latest_with_revenue.columns:
            rev_by_product = (
                df_latest_with_revenue.groupby(prod_col, as_index=False)['revenue']
                .sum()
                .rename(columns={'revenue': 'Сума'})
            )
        else:
            # якщо немає цін — сума = 0
            rev_by_product = qty_by_product[[prod_col]].copy()
            rev_by_product['Сума'] = 0.0
        
        # обʼєднуємо
        combined_prod = (
            pd.merge(qty_by_product, rev_by_product, on=prod_col, how='left')
            .rename(columns={prod_col: 'Препарат'})
            .fillna({'Сума': 0.0})
            .sort_values('К-сть', ascending=False)
        )
        
        return combined_prod
    
    def calculate_abc_analysis(self, df_period: pd.DataFrame, metric: str = 'revenue') -> pd.DataFrame:
        """Розраховує ABC аналіз"""
        prod_col = 'product_name_clean' if 'product_name_clean' in df_period.columns else 'product_name'
        
        if metric == 'revenue':
            abc_data = (
                df_period.groupby(prod_col, as_index=False)['revenue']
                .sum()
                .rename(columns={prod_col: 'Препарат', 'revenue': 'Значення'})
                .sort_values('Значення', ascending=False)
            )
        else:  # quantity
            abc_data = (
                df_period.groupby(prod_col, as_index=False)['quantity']
                .sum()
                .rename(columns={prod_col: 'Препарат', 'quantity': 'Значення'})
                .sort_values('Значення', ascending=False)
            )
        
        if not abc_data.empty:
            total_value = float(abc_data['Значення'].sum()) or 1.0
            abc_data['Частка, %'] = 100.0 * abc_data['Значення'] / total_value
            abc_data['Кумулятивна частка, %'] = abc_data['Частка, %'].cumsum()
            
            def _abc_class(x):
                if x <= 80: return 'A'
                if x <= 95: return 'B'
                return 'C'
            
            abc_data['Клас'] = abc_data['Кумулятивна частка, %'].apply(_abc_class)
        
        return abc_data
    
    def calculate_bcg_matrix(self, df_period: pd.DataFrame) -> pd.DataFrame:
        """Розраховує BCG матрицю"""
        if not {'month_int','quantity','product_name'}.issubset(df_period.columns):
            return pd.DataFrame()
        
        df_tmp = df_period.dropna(subset=['month_int']).copy()
        
        # Нормалізуємо назви продуктів
        if 'product_name_clean' not in df_tmp.columns and 'product_name' in df_tmp.columns:
            df_tmp['product_name_clean'] = (
                df_tmp['product_name'].astype(str)
                .str.replace(r'^\s*[\d\W_]+', '', regex=True)
                .str.strip()
            )
        
        prod_col_bcg = 'product_name_clean' if 'product_name_clean' in df_tmp.columns else 'product_name'
        
        # Беремо тільки останні декади кожного місяця
        if {'year','decade'}.issubset(df_tmp.columns):
            df_tmp = df_tmp.dropna(subset=['year','decade']).copy()
            df_tmp['year'] = pd.to_numeric(df_tmp['year'], errors='coerce')
            df_tmp['decade'] = pd.to_numeric(df_tmp['decade'], errors='coerce')
            max_dec_per = df_tmp.groupby(['year','month_int'])['decade'].transform('max')
            df_lastdec = df_tmp[df_tmp['decade'] == max_dec_per].copy()
        else:
            df_lastdec = df_tmp.copy()
        
        # Агрегуємо по продуктах
        df_lastdec['month_int'] = df_lastdec['month_int'].astype(int)
        vol_by_month = (
            df_lastdec.groupby([prod_col_bcg, 'month_int'], as_index=False)['quantity'].sum()
        )
        
        months_sorted = sorted(vol_by_month['month_int'].unique().tolist())
        if len(months_sorted) >= 2:
            m_last, m_prev = months_sorted[-1], months_sorted[-2]
            vol_last = vol_by_month[vol_by_month['month_int'] == m_last].rename(columns={'quantity':'qty_last'})
            vol_prev = vol_by_month[vol_by_month['month_int'] == m_prev].rename(columns={'quantity':'qty_prev'})
            
            bcg = pd.merge(
                vol_last[[prod_col_bcg,'qty_last']],
                vol_prev[[prod_col_bcg,'qty_prev']],
                on=prod_col_bcg,
                how='outer'
            ).fillna(0)
            
            bcg['growth_%'] = ((bcg['qty_last'] - bcg['qty_prev']) / bcg['qty_prev'].replace(0, pd.NA)) * 100
            bcg['growth_%'] = bcg['growth_%'].fillna(0)
            bcg = bcg.rename(columns={prod_col_bcg:'Препарат'})
            
            # Кольорове кодування за темпом росту
            def _bucket_growth(g):
                try:
                    g = float(g)
                except Exception:
                    g = 0.0
                if g < 0:
                    return 'Падіння (<0%)'
                elif g < 3:
                    return 'Стабільно (0–3%)'
                else:
                    return 'Ріст (>3%)'
            
            bcg['Категорія'] = bcg['growth_%'].apply(_bucket_growth)
            
            return bcg
        
        return pd.DataFrame()
    
    def calculate_growth_metrics(self, df_period: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Розраховує метрики росту між місяцями"""
        prod_col_full = 'product_name_clean' if 'product_name_clean' in df_period.columns else 'product_name'
        
        if not prod_col_full:
            return pd.DataFrame(), pd.DataFrame()
        
        # Агрегація по місяцях тільки за останні декади
        df_dyn_base = df_period.dropna(subset=['month_int']).copy()
        if {'year','decade'}.issubset(df_dyn_base.columns):
            df_dyn_base = df_dyn_base.dropna(subset=['year','decade']).copy()
            df_dyn_base['year'] = pd.to_numeric(df_dyn_base['year'], errors='coerce')
            df_dyn_base['decade'] = pd.to_numeric(df_dyn_base['decade'], errors='coerce')
            max_dec_per = df_dyn_base.groupby(['year','month_int'])['decade'].transform('max')
            df_lastdec_dyn = df_dyn_base[df_dyn_base['decade'] == max_dec_per].copy()
        else:
            df_lastdec_dyn = df_dyn_base
        
        month_prod = (
            df_lastdec_dyn
            .groupby([prod_col_full, 'month_int'], as_index=False)[['quantity', 'revenue']]
            .sum()
            .rename(columns={prod_col_full: 'Препарат'})
        )
        
        if not month_prod.empty and month_prod['month_int'].nunique() >= 2:
            months_sorted = sorted(month_prod['month_int'].dropna().astype(int).unique())
            last_month = int(months_sorted[-1])
            prev_month = int(months_sorted[-2])
            
            # Ріст за виручкою
            cur_rev = month_prod[month_prod['month_int'] == last_month][['Препарат', 'revenue']].rename(columns={'revenue': 'rev_last'})
            prev_rev = month_prod[month_prod['month_int'] == prev_month][['Препарат', 'revenue']].rename(columns={'revenue': 'rev_prev'})
            grow_rev = pd.merge(cur_rev, prev_rev, on='Препарат', how='outer').fillna(0.0)
            grow_rev['Δ₴'] = grow_rev['rev_last'] - grow_rev['rev_prev']
            grow_rev['Δ%'] = ((grow_rev['rev_last'] - grow_rev['rev_prev']) / grow_rev['rev_prev'].replace(0, pd.NA)) * 100
            grow_rev['Δ%'] = grow_rev['Δ%'].fillna(0.0)
            
            # Ріст за кількістю
            cur_qty = month_prod[month_prod['month_int'] == last_month][['Препарат', 'quantity']].rename(columns={'quantity': 'qty_last'})
            prev_qty = month_prod[month_prod['month_int'] == prev_month][['Препарат', 'quantity']].rename(columns={'quantity': 'qty_prev'})
            grow_qty = pd.merge(cur_qty, prev_qty, on='Препарат', how='outer').fillna(0.0)
            grow_qty['Δк-сть'] = grow_qty['qty_last'] - grow_qty['qty_prev']
            grow_qty['Δ%'] = ((grow_qty['qty_last'] - grow_qty['qty_prev']) / grow_qty['qty_prev'].replace(0, pd.NA)) * 100
            grow_qty['Δ%'] = grow_qty['Δ%'].fillna(0.0)
            
            return grow_rev, grow_qty
        
        return pd.DataFrame(), pd.DataFrame()
    
    def calculate_top_pharmacies(self, df_with_revenue: pd.DataFrame) -> pd.DataFrame:
        """Розраховує топ аптек"""
        if 'revenue' not in df_with_revenue.columns:
            df_with_revenue['revenue'] = 0.0
        
        # ЄДИНИЙ канонічний ключ адреси
        if {'city','street','house_number'}.issubset(df_with_revenue.columns):
            tmp = df_with_revenue.copy()
            tmp['__city__'] = tmp['city'].fillna('').astype(str).str.strip()
            tmp['__street__'] = tmp['street'].fillna('').astype(str).str.strip()
            tmp['__house__'] = tmp['house_number'].fillna('').astype(str).str.strip()
            tmp['__addr_key__'] = (
                tmp['__city__'].str.lower() + '|' + tmp['__street__'].str.lower() + '|' + tmp['__house__'].str.lower()
            )
            tmp['__city_disp__'] = tmp['__city__']
            tmp['__addr_disp__'] = (tmp['__street__'] + ' ' + tmp['__house__']).str.strip()
            
            name_cols = [c for c in ['new_client','client','pharmacy','client_name'] if c in tmp.columns]
            if name_cols:
                tmp['__client_name__'] = tmp[name_cols[0]].astype(str).fillna('').str.strip()
            else:
                tmp['__client_name__'] = ''
        else:
            # fallback
            tmp = df_with_revenue.copy()
            if 'full_address_processed' in tmp.columns:
                tmp['__addr_key__'] = tmp['full_address_processed'].astype(str).fillna('').str.strip().str.lower()
                tmp['__addr_disp__'] = tmp['full_address_processed'].astype(str).fillna('').str.strip()
            elif 'address' in tmp.columns:
                tmp['__addr_key__'] = tmp['address'].astype(str).fillna('').str.strip().str.lower()
                tmp['__addr_disp__'] = tmp['address'].astype(str).fillna('').str.strip()
            else:
                tmp['__addr_key__'] = ''
                tmp['__addr_disp__'] = ''
            tmp['__city_disp__'] = tmp.get('city', pd.Series('', index=tmp.index)).astype(str).fillna('').str.strip()
            name_cols = [c for c in ['new_client','client','pharmacy','client_name'] if c in tmp.columns]
            tmp['__client_name__'] = tmp[name_cols[0]].astype(str).fillna('').str.strip() if name_cols else ''
        
        if (tmp['__addr_key__'] == '').all():
            return pd.DataFrame()
        
        # Агрегація лише за адресним ключем
        grp = tmp.groupby('__addr_key__', as_index=False).agg(
            Сума=('revenue','sum'),
            **{'К-сть': ('quantity','sum')}
        ).sort_values('Сума', ascending=False)
        
        # Додати відображення
        disp = tmp[['__addr_key__','__city_disp__','__addr_disp__','__client_name__']].copy()
        disp = disp.groupby('__addr_key__', as_index=False).agg(
            Місто=('__city_disp__', lambda s: next((x for x in s if str(x).strip()), '')),
            Адреса=('__addr_disp__', lambda s: next((x for x in s if str(x).strip()), '')),
            Аптека=('__client_name__', lambda s: next((x for x in s if str(x).strip()), '')),
        )
        top_join = grp.merge(disp, on='__addr_key__', how='left')
        
        return top_join
