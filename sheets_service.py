#!/usr/bin/env python3
# sheets_service.py - Servicio para acceder a datos de Google Sheets

import os
import logging
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2 import service_account

# Configurar logger
logger = logging.getLogger("subscription_notifier.sheets")

class SheetsService:
    def __init__(self, credentials_file=None, spreadsheet_id=None, sheet_name=None):
        """
        Inicializa el servicio de Google Sheets.
        
        Args:
            credentials_file (str): Ruta al archivo de credenciales. Si es None, se intenta obtener de las variables de entorno.
            spreadsheet_id (str): ID de la hoja de cálculo. Si es None, se intenta obtener de las variables de entorno.
            sheet_name (str): Nombre de la hoja. Si es None, se intenta obtener de las variables de entorno.
        """
        self.credentials_file = credentials_file or os.getenv('GOOGLE_CREDENTIALS_FILE', 'creds.json')
        self.spreadsheet_id = spreadsheet_id or os.getenv('SPREADSHEET_ID', '1WAEqqx_0OuqXM8Na4eVhKULjJPTSogETP8Dh-3gMUmk')
        self.sheet_name = sheet_name or os.getenv('SHEET_NAME', 'Gastos Fijos')
        self.scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        
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
    
    def load_subscriptions(self):
        """
        Carga las suscripciones desde Google Sheets.
        
        Returns:
            list: Lista de diccionarios con los datos de las suscripciones.
        """
        try:
            service = self.get_service()
            if not service:
                logger.error("No se pudo obtener el servicio de Google Sheets")
                return []
            
            # Obtener los datos de la hoja
            sheet = service.spreadsheets()
            result = sheet.values().get(
                spreadsheetId=self.spreadsheet_id,
                range=f"'{self.sheet_name}'!A:H"  # Asumiendo que los datos están en las columnas A-H
            ).execute()
            
            values = result.get('values', [])
            if not values:
                logger.warning("No se encontraron datos en la hoja de cálculo")
                return []
            
            # Obtener los encabezados (primera fila)
            headers = values[0]
            
            # Normalizar encabezados (convertir a minúsculas y espacios a guiones bajos)
            normalized_headers = [h.lower().replace(' ', '_') for h in headers]
            
            # Mapear encabezados a nombres de campo estándar
            header_mapping = {
                'fecha_primer_pago': 'fecha',
                'detalle': 'detalle',
                'monto_usd': 'montoUSD',
                'monto_cop': 'montoCOP',
                'categoría': 'categoria',
                'pagada_con': 'pagadaCon',
                'pagada_por': 'pagadaPor',
                'estado': 'estado'
            }
            
            # Crear una lista de diccionarios con los datos
            subscriptions = []
            for row in values[1:]:  # Saltar la primera fila (encabezados)
                if len(row) < len(headers):  # Asegurarse de que la fila tiene suficientes columnas
                    row.extend([''] * (len(headers) - len(row)))  # Rellenar con valores vacíos si faltan
                
                # Crear diccionario con los nombres de campo normalizados
                subscription = {}
                for field_name, field_value in zip(normalized_headers, row):
                    if field_name in header_mapping:
                        mapped_name = header_mapping[field_name]
                        subscription[mapped_name] = field_value
                    else:
                        # Para campos que no están en el mapeo, usar el nombre original
                        subscription[field_name] = field_value
                
                # Asegurarse de que todos los campos necesarios existan
                required_fields = ['fecha', 'detalle', 'montoUSD', 'estado']
                if all(field in subscription for field in required_fields):
                    subscriptions.append(subscription)
                else:
                    missing = [field for field in required_fields if field not in subscription]
                    logger.warning(f"Fila ignorada por falta de campos: {missing}. Valores: {row}")
            
            logger.info(f"Se cargaron {len(subscriptions)} suscripciones desde Google Sheets")
            return subscriptions
        
        except Exception as e:
            logger.error(f"Error al cargar datos desde Google Sheets: {e}")
            return []
    
    def get_due_subscriptions(self, today=None):
        """
        Obtiene las suscripciones que se causan hoy o en la fecha especificada.
        
        Args:
            today (datetime.datetime): Fecha para verificar las suscripciones. Si es None, se usa la fecha actual.
            
        Returns:
            list: Lista de suscripciones a notificar.
        """
        if today is None:
            today = datetime.now()
        
        logger.info(f"Verificando suscripciones para la fecha: {today.strftime('%d/%m/%Y')}")
        
        # Cargar las suscripciones desde Google Sheets
        subscriptions = self.load_subscriptions()
        
        due_subs = []
        
        for sub in subscriptions:
            # Convertir la fecha de string a objeto datetime
            try:
                # Asegurarse de que el formato de fecha sea el correcto (dd/mm/yyyy)
                original_date = datetime.strptime(sub["fecha"], "%d/%m/%Y")
                
                # Verificar si hoy es el día mensual correspondiente a la fecha original
                # Y si la suscripción está activa (basado únicamente en el estado de la columna H)
                if (original_date.day == today.day and 
                    sub["estado"].lower() == "activo"):
                    due_subs.append(sub)
                    logger.info(f"Suscripción por causar hoy: {sub['detalle']}")
            except ValueError as e:
                logger.error(f"Error de formato de fecha para {sub.get('detalle', 'desconocido')}: {e}")
        
        if not due_subs:
            logger.info("No hay suscripciones por cobrar hoy.")
        
        return due_subs


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
    sheets_service = SheetsService()
    
    # Probar carga de suscripciones
    subscriptions = sheets_service.load_subscriptions()
    print(f"Se cargaron {len(subscriptions)} suscripciones:")
    for sub in subscriptions[:5]:  # Mostrar solo las primeras 5 para no saturar la salida
        print(f"- {sub.get('detalle', 'Sin detalle')}: {sub.get('montoUSD', '0')} USD ({sub.get('estado', 'Sin estado')})")
    
    # Probar obtención de suscripciones del día
    due_today = sheets_service.get_due_subscriptions()
    print(f"\nSuscripciones que se causan hoy: {len(due_today)}")
    for sub in due_today:
        print(f"- {sub.get('detalle', 'Sin detalle')}: {sub.get('montoUSD', '0')} USD")