# app/utils/__init__.py
"""
Утиліти та спільні дані для застосунку.
"""

# Імпортуємо словники та константи зі schema
from app.data.schema import PRODUCTS_DICT, UKRAINIAN_MONTHS

__all__ = [
    "PRODUCTS_DICT",
    "UKRAINIAN_MONTHS",
]