#!/usr/bin/env python3
# currency_service.py - Servicio para obtener tasas de cambio y convertir monedas

import os
import logging
from googleapiclient.discovery import build
from google.oauth2 import service_account
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar logger
logger = logging.getLogger("subscription_notifier.currency")

class CurrencyService:
    """Servicio para manejar conversiones de moneda."""
    
    def __init__(self, credentials_file=None, spreadsheet_id=None):
        """
        Inicializa el servicio de conversión de moneda.
        
        Args:
            credentials_file (str): Ruta al archivo de credenciales. Si es None, se intenta obtener de las variables de entorno.
            spreadsheet_id (str): ID de la hoja de cálculo con las tasas de cambio. Si es None, se intenta obtener de las variables de entorno.
        """
        self.credentials_file = credentials_file or os.getenv('GOOGLE_CREDENTIALS_FILE', 'creds.json')
        self.spreadsheet_id = spreadsheet_id or os.getenv('CURRENCY_SPREADSHEET_ID', '1HtvBLDTSzAdxmZ5islKZCGF0PNjC60RFOOxXpYKHh_8')
        self.scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        
        # Tasas de cambio predeterminadas en caso de error
        self.usd_to_cop_rate = 4300.0  # 1 USD = 4300 COP (valor predeterminado)
        self.cop_to_usd_rate = 1/4300.0  # 1 COP = 0.00023 USD (valor predeterminado)
        
        # Cargar tasas de cambio actuales
        self.load_exchange_rates()
    
    def get_service(self):
        """
        Obtiene un servicio autorizado para acceder a Google Sheets.
        
        Returns:
            googleapiclient.discovery.Resource: Servicio de Google Sheets, o None si ocurre un error.
        """
        try:
            creds = service_account.Credentials.from_service_account_file(
                self.credentials_file, scopes=self.scopes)
            service = build('sheets', 'v4', credentials=creds)
            return service
        except Exception as e:
            logger.error(f"Error al conectar con Google Sheets: {e}")
            return None
    
    def load_exchange_rates(self):
        """
        Carga las tasas de cambio actuales desde la hoja de cálculo.
        
        Returns:
            bool: True si se cargaron correctamente, False en caso contrario.
        """
        try:
            service = self.get_service()
            if not service:
                logger.error("No se pudo obtener el servicio de Google Sheets")
                return False
            
            # Obtener las tasas de cambio de la hoja
            result = service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range="A1:A2"  # A1: USD to COP, A2: COP to USD
            ).execute()
            
            values = result.get('values', [])
            if not values or len(values) < 2:
                logger.warning("No se encontraron tasas de cambio en la hoja. Usando valores predeterminados.")
                return False
            
            # Actualizar tasas de cambio
            try:
                self.usd_to_cop_rate = float(values[0][0])
                self.cop_to_usd_rate = float(values[1][0])
                logger.info(f"Tasas de cambio actualizadas: 1 USD = {self.usd_to_cop_rate} COP, 1 COP = {self.cop_to_usd_rate} USD")
                return True
            except (ValueError, IndexError) as e:
                logger.error(f"Error al procesar tasas de cambio: {e}. Usando valores predeterminados.")
                return False
            
        except Exception as e:
            logger.error(f"Error al cargar tasas de cambio: {e}")
            return False
    
    def convert_usd_to_cop(self, amount_usd):
        """
        Convierte un monto de USD a COP.
        
        Args:
            amount_usd (float): Monto en USD a convertir.
            
        Returns:
            float: Monto equivalente en COP.
        """
        return amount_usd * self.usd_to_cop_rate
    
    def convert_cop_to_usd(self, amount_cop):
        """
        Convierte un monto de COP a USD.
        
        Args:
            amount_cop (float): Monto en COP a convertir.
            
        Returns:
            float: Monto equivalente en USD.
        """
        return amount_cop * self.cop_to_usd_rate
    
    def format_cop_amount(self, amount):
        """
        Formatea un monto en COP con el formato adecuado.
        
        Args:
            amount (float): Monto a formatear.
            
        Returns:
            str: Monto formateado.
        """
        return f"${amount:,.0f}".replace(',', '.')
    
    def format_usd_amount(self, amount):
        """
        Formatea un monto en USD con el formato adecuado.
        
        Args:
            amount (float): Monto a formatear.
            
        Returns:
            str: Monto formateado.
        """
        return f"${amount:,.2f}"
    
    def parse_amount(self, amount_str):
        """
        Parsea un string que representa un monto de dinero a un float.
        
        Args:
            amount_str (str): String que representa un monto.
            
        Returns:
            float: Valor numérico del monto.
        """
        if isinstance(amount_str, str):
            # Eliminar el símbolo $ y las comas o puntos
            cleaned = amount_str.replace('$', '').replace('.', '').replace(',', '.')
            try:
                return float(cleaned)
            except ValueError:
                return 0.0
        elif isinstance(amount_str, (int, float)):
            return float(amount_str)
        else:
            return 0.0


# Para uso como script independiente
if __name__ == "__main__":
    # Configurar logging básico para pruebas
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )
    
    # Crear instancia del servicio
    currency_service = CurrencyService()
    
    # Probar conversiones
    usd_amount = 100.0
    cop_amount = 430000.0
    
    cop_result = currency_service.convert_usd_to_cop(usd_amount)
    usd_result = currency_service.convert_cop_to_usd(cop_amount)
    
    print(f"{usd_amount} USD = {currency_service.format_cop_amount(cop_result)} COP")
    print(f"{cop_amount} COP = {currency_service.format_usd_amount(usd_result)} USD")