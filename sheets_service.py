#!/usr/bin/env python3
# accounting_service.py - Servicio para registrar gastos en la hoja de contabilidad

import os
import logging
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2 import service_account

# Configurar logger
logger = logging.getLogger("subscription_notifier.accounting")

class AccountingService:
    def __init__(self, credentials_file=None, spreadsheet_id=None, expenses_sheet_name=None, movements_sheet_name=None):
        """
        Inicializa el servicio de contabilidad para registrar gastos.
        
        Args:
            credentials_file (str): Ruta al archivo de credenciales. Si es None, se intenta obtener de las variables de entorno.
            spreadsheet_id (str): ID de la hoja de cálculo. Si es None, se intenta obtener de las variables de entorno.
            expenses_sheet_name (str): Nombre de la hoja de gastos. Si es None, se intenta obtener de las variables de entorno.
            movements_sheet_name (str): Nombre de la hoja de movimientos. Si es None, se intenta obtener de las variables de entorno.
        """
        self.credentials_file = credentials_file or os.getenv('GOOGLE_CREDENTIALS_FILE', 'creds.json')
        self.spreadsheet_id = spreadsheet_id or os.getenv('ACCOUNTING_SPREADSHEET_ID', '1e1UQWdcRDDawPjIuHIS0yxQlxtczEdiTPFBltpfymmA')
        self.expenses_sheet_name = expenses_sheet_name or os.getenv('ACCOUNTING_EXPENSES_SHEET_NAME', 'Gastos')
        self.movements_sheet_name = movements_sheet_name or os.getenv('ACCOUNTING_MOVEMENTS_SHEET_NAME', 'Movimientos caja')
        self.scopes = ['https://www.googleapis.com/auth/spreadsheets']  # Necesitamos permisos de escritura
        
        # Verificar que el archivo de credenciales exista
        if not os.path.exists(self.credentials_file):
            logger.warning(f"El archivo de credenciales {self.credentials_file} no existe")
    
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
    
    def format_date_for_accounting(self, date_obj):
        """
        Formatea una fecha para la hoja de contabilidad (MM/DD/YYYY).
        
        Args:
            date_obj (datetime): Objeto datetime a formatear.
            
        Returns:
            str: Fecha formateada en el formato MM/DD/YYYY.
        """
        return date_obj.strftime("%m/%d/%Y")
    
    def extract_numeric_value(self, value_str):
        """
        Extrae el valor numérico de un string de moneda.
        
        Args:
            value_str (str): String de moneda (ej: "$100.000").
            
        Returns:
            float: Valor numérico.
        """
        if isinstance(value_str, str):
            # Eliminar el símbolo $ y puntos de miles
            return float(value_str.replace('$', '').replace('.', '').replace(',', '.'))
        elif isinstance(value_str, (int, float)):
            return float(value_str)
        else:
            return 0.0
    
    def register_expenses(self, subscriptions):
        """
        Registra los gastos recurrentes en la hoja de gastos y movimientos de caja.
        
        Args:
            subscriptions (list): Lista de suscripciones a registrar.
            
        Returns:
            bool: True si ambos registros fueron exitosos, False en caso contrario.
        """
        if not subscriptions:
            logger.info("No hay gastos para registrar")
            return True
        
        # Registrar en la hoja de gastos
        expenses_result = self.register_in_expenses_sheet(subscriptions)
        
        # Registrar en la hoja de movimientos de caja
        movements_result = self.register_in_movements_sheet(subscriptions)
        
        return expenses_result and movements_result
    
    def register_in_expenses_sheet(self, subscriptions):
        """
        Registra los gastos recurrentes en la hoja de gastos.
        
        Args:
            subscriptions (list): Lista de suscripciones a registrar.
            
        Returns:
            bool: True si se registraron correctamente, False en caso contrario.
        """
        try:
            service = self.get_service()
            if not service:
                logger.error("No se pudo obtener el servicio de Google Sheets")
                return False
            
            # Fecha actual para el registro
            today = datetime.now()
            formatted_date = self.format_date_for_accounting(today)
            
            # Preparar los valores a insertar
            values = []
            for sub in subscriptions:
                # Extraer valores numéricos para Google Sheets
                monto_cop = self.extract_numeric_value(sub.get('montoCOP', '0'))
                monto_usd = self.extract_numeric_value(sub.get('montoUSD', '0'))
                
                # Crear una fila para cada suscripción
                # [Fecha, Detalle, Categoría, Monto COP (número), Monto USD (número)]
                row = [
                    formatted_date,  # Fecha en formato MM/DD/YYYY
                    sub.get('detalle', 'Sin detalles'),  # Detalle
                    sub.get('categoria', 'Sin categoría'),  # Categoría
                    monto_cop,  # Monto COP como número
                    monto_usd    # Monto USD como número
                ]
                values.append(row)
            
            # Obtener la siguiente fila disponible
            result = service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{self.expenses_sheet_name}'!A:A"
            ).execute()
            
            existing_rows = result.get('values', [])
            next_row = len(existing_rows) + 1
            
            # Insertar los valores en la hoja
            body = {
                'values': values
            }
            
            result = service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{self.expenses_sheet_name}'!A{next_row}",
                valueInputOption='RAW',
                body=body
            ).execute()
            
            rows_updated = result.get('updatedRows', 0)
            logger.info(f"Se registraron {rows_updated} gastos en la hoja de gastos")
            
            return True
            
        except Exception as e:
            logger.error(f"Error al registrar gastos en la hoja de gastos: {e}")
            return False
    
    def register_in_movements_sheet(self, subscriptions):
        """
        Registra los gastos recurrentes en la hoja de movimientos de caja con valores negativos.
        
        Args:
            subscriptions (list): Lista de suscripciones a registrar.
            
        Returns:
            bool: True si se registraron correctamente, False en caso contrario.
        """
        try:
            service = self.get_service()
            if not service:
                logger.error("No se pudo obtener el servicio de Google Sheets")
                return False
            
            # Verificar si la hoja de movimientos existe
            sheet_exists = self.check_sheet_exists(self.movements_sheet_name)
            if not sheet_exists:
                logger.error(f"La hoja '{self.movements_sheet_name}' no existe en el documento")
                return False
            
            # Fecha actual para el registro
            today = datetime.now()
            formatted_date = self.format_date_for_accounting(today)
            
            # Preparar los valores a insertar
            values = []
            for sub in subscriptions:
                # Obtener el monto en COP y convertirlo a negativo (como número)
                monto_cop = -abs(self.extract_numeric_value(sub.get('montoCOP', '0')))
                
                # Crear una fila para cada suscripción
                # [Fecha, Detalle, Monto COP (negativo)]
                row = [
                    formatted_date,  # Fecha en formato MM/DD/YYYY
                    f"Gasto recurrente: {sub.get('detalle', 'Sin detalles')}",  # Detalle
                    monto_cop  # Monto COP como número negativo
                ]
                values.append(row)
            
            # Obtener la siguiente fila disponible
            result = service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{self.movements_sheet_name}'!A:A"
            ).execute()
            
            existing_rows = result.get('values', [])
            next_row = len(existing_rows) + 1
            
            # Insertar los valores en la hoja
            body = {
                'values': values
            }
            
            result = service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{self.movements_sheet_name}'!A{next_row}",
                valueInputOption='RAW',
                body=body
            ).execute()
            
            rows_updated = result.get('updatedRows', 0)
            logger.info(f"Se registraron {rows_updated} movimientos en la hoja de movimientos de caja")
            
            return True
            
        except Exception as e:
            logger.error(f"Error al registrar movimientos en la hoja de movimientos de caja: {e}")
            return False
    
    def check_sheet_exists(self, sheet_name):
        """
        Verifica si una hoja existe en el documento.
        
        Args:
            sheet_name (str): Nombre de la hoja a verificar.
            
        Returns:
            bool: True si la hoja existe, False en caso contrario.
        """
        try:
            service = self.get_service()
            if not service:
                return False
                
            # Obtener todas las hojas del documento
            result = service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id,
                fields='sheets.properties.title'
            ).execute()
            
            # Verificar si la hoja existe
            for sheet in result.get('sheets', []):
                if sheet.get('properties', {}).get('title') == sheet_name:
                    logger.info(f"Hoja '{sheet_name}' encontrada")
                    return True
            
            logger.error(f"Hoja '{sheet_name}' no encontrada. Hojas disponibles:")
            for sheet in result.get('sheets', []):
                logger.error(f"- {sheet.get('properties', {}).get('title')}")
            
            return False
        
        except Exception as e:
            logger.error(f"Error al verificar si la hoja '{sheet_name}' existe: {e}")
            return False
    
    def test_connection(self):
        """
        Prueba la conexión con las hojas de contabilidad.
        
        Returns:
            bool: True si la conexión es exitosa, False en caso contrario.
        """
        service = self.get_service()
        if not service:
            logger.error("No se pudo obtener el servicio de Google Sheets")
            return False
        
        try:
            # Mostrar todas las hojas disponibles para facilitar la depuración
            result = service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id,
                fields='sheets.properties.title'
            ).execute()
            
            sheets = [sheet.get('properties', {}).get('title') for sheet in result.get('sheets', [])]
            logger.info(f"Hojas disponibles en el documento: {', '.join(sheets)}")
            
            # Verificar si las hojas existen
            expenses_sheet_found = self.check_sheet_exists(self.expenses_sheet_name)
            movements_sheet_found = self.check_sheet_exists(self.movements_sheet_name)
            
            if expenses_sheet_found and movements_sheet_found:
                logger.info(f"Conexión exitosa con ambas hojas de contabilidad")
                return True
            elif expenses_sheet_found:
                logger.error(f"La hoja '{self.movements_sheet_name}' no existe en el documento")
                return False
            elif movements_sheet_found:
                logger.error(f"La hoja '{self.expenses_sheet_name}' no existe en el documento")
                return False
            else:
                logger.error(f"Las hojas '{self.expenses_sheet_name}' y '{self.movements_sheet_name}' no existen en el documento")
                return False
                
        except Exception as e:
            logger.error(f"Error al conectar con las hojas de contabilidad: {e}")
            return False


# Para uso como script independiente
if __name__ == "__main__":
    # Configurar logging básico para pruebas
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )
    
    # Cargar variables de entorno
    from dotenv import load_dotenv
    load_dotenv()
    
    # Crear instancia del servicio
    accounting_service = AccountingService()
    
    # Probar conexión
    if accounting_service.test_connection():
        print("✅ Conexión exitosa con las hojas de contabilidad")
        
        # Prueba de registro (ejemplo)
        test_subscription = [{
            "fecha": datetime.now().strftime("%d/%m/%Y"),
            "detalle": "Suscripción de Prueba",
            "montoUSD": "$25",
            "montoCOP": "$100,000",
            "categoria": "Prueba"
        }]
        
        # Preguntar antes de registrar
        answer = input("¿Deseas registrar un gasto de prueba en ambas hojas? (s/n): ")
        if answer.lower() == 's':
            if accounting_service.register_expenses(test_subscription):
                print("✅ Registro de prueba exitoso en ambas hojas")
            else:
                print("❌ Error al registrar el gasto de prueba")
    else:
        print("❌ Error al conectar con las hojas de contabilidad")