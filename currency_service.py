#!/usr/bin/env python3
# currency_service.py - Servicio para conversión automática COP ↔ USD

import os
import logging
import requests

logger = logging.getLogger("currency_service")
logger.setLevel(logging.INFO)

class CurrencyService:
    """
    Servicio para obtener la tasa de conversión y convertir montos
    entre COP y USD usando FreeCurrencyAPI.
    """
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv('FREE_CURRENCY_API_KEY')
        self.base_url = 'https://api.freecurrencyapi.com/v1/latest'

        if not self.api_key:
            logger.error("No se encontró FREE_CURRENCY_API_KEY en el entorno")

    def convert(self, amount: float, from_currency: str, to_currency: str) -> float:
        """
        Convierte `amount` de `from_currency` a `to_currency`.
        Devuelve un float o None en caso de error.
        """
        params = {
            'apikey': self.api_key,
            'base_currency': from_currency,
            'currencies': to_currency
        }
        try:
            resp = requests.get(self.base_url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            rate = data.get('data', {}).get(to_currency)
            if rate is None:
                logger.error(f"Tasa no disponible para {from_currency}->{to_currency}")
                return None
            return amount * rate
        except Exception as e:
            logger.error(f"Error al llamar FreeCurrencyAPI: {e}")
            return None
