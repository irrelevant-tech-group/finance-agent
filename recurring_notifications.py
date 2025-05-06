#!/usr/bin/env python3
# Notificador de Gastos Recurrentes desde Google Sheets
# Autor: Claude
# Fecha: Mayo 2025

import os
import schedule
import time
import logging
from datetime import datetime
from dotenv import load_dotenv
import resend  # Importación corregida
from jinja2 import Template
from googleapiclient.discovery import build
from google.oauth2 import service_account

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("subscription_notifier.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("subscription_notifier")

# Obtener configuración desde variables de entorno
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'creds.json')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID', '1WAEqqx_0OuqXM8Na4eVhKULjJPTSogETP8Dh-3gMUmk')
SHEET_NAME = os.getenv('SHEET_NAME', 'Gastos Fijos')
RESEND_API_KEY = os.getenv('RESEND_API_KEY')
NOTIFICATION_EMAIL = os.getenv('NOTIFICATION_EMAIL')
SENDER_EMAIL = os.getenv('SENDER_EMAIL', 'Notificador de Gastos <gastos@tudominio.com>')
NOTIFICATION_TIME = os.getenv('NOTIFICATION_TIME', '08:00')

def get_service():
    """Obtiene un servicio autorizado para acceder a Google Sheets."""
    try:
        creds = service_account.Credentials.from_service_account_file(
            CREDENTIALS_FILE, scopes=SCOPES)
        service = build('sheets', 'v4', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Error al conectar con Google Sheets: {e}")
        return None

def load_subscriptions_from_sheets():
    """Carga las suscripciones desde Google Sheets."""
    try:
        service = get_service()
        if not service:
            logger.error("No se pudo obtener el servicio de Google Sheets")
            return []
        
        # Obtener los datos de la hoja
        sheet = service.spreadsheets()
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{SHEET_NAME}'!A:H"  # Asumiendo que los datos están en las columnas A-H
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

def check_subscriptions_due():
    """Verifica si hay suscripciones que se causan hoy."""
    logger.info(f"Verificando suscripciones: {datetime.now().strftime('%d/%m/%Y')}")
    
    # Cargar las suscripciones desde Google Sheets
    subscriptions = load_subscriptions_from_sheets()
    
    today = datetime.now()
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
    
    if due_subs:
        send_notification(due_subs)
    else:
        logger.info("No hay suscripciones por cobrar hoy.")

def format_currency(value):
    """Formatea valores de moneda."""
    if isinstance(value, str):
        # Eliminar el símbolo $ y las comas
        value = value.replace('$', '').replace(',', '')
    try:
        return float(value)
    except ValueError:
        return 0.0

def send_notification(subscriptions):
    """Envía una notificación por correo usando Resend."""
    today = datetime.now().strftime("%d %B %Y")
    
    # Preparar datos para la plantilla
    try:
        total_usd = sum(format_currency(sub["montoUSD"]) for sub in subscriptions)
        total_cop = sum(format_currency(sub.get("montoCOP", "0")) for sub in subscriptions)
    except Exception as e:
        logger.error(f"Error al calcular totales: {e}")
        total_usd = 0
        total_cop = 0
    
    # Usar Jinja2 para crear el HTML del correo
    email_template = """
    <html>
    <head>
        <style>
            body {
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                margin: 0;
                padding: 20px;
            }
            table {
                border-collapse: collapse;
                width: 100%;
                margin-bottom: 20px;
            }
            th, td {
                border: 1px solid #dddddd;
                text-align: left;
                padding: 8px;
            }
            th {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
            }
            tr:nth-child(even) {
                background-color: #f9f9f9;
            }
            .total-row {
                font-weight: bold;
                background-color: #f0f0f0;
            }
            h2 {
                color: #4CAF50;
                border-bottom: 2px solid #4CAF50;
                padding-bottom: 5px;
            }
            .footer {
                margin-top: 30px;
                font-size: 12px;
                color: #666;
                border-top: 1px solid #eee;
                padding-top: 10px;
            }
        </style>
    </head>
    <body>
        <h2>Notificación de Gastos Recurrentes - {{ today }}</h2>
        <p>Los siguientes gastos recurrentes se causan hoy:</p>
        <table>
            <tr>
                <th>Detalle</th>
                <th>Monto USD</th>
                <th>Monto COP</th>
                <th>Categoría</th>
                <th>Pagada Con</th>
                <th>Pagada Por</th>
            </tr>
            {% for sub in subscriptions %}
            <tr>
                <td>{{ sub.detalle }}</td>
                <td>{{ sub.montoUSD }}</td>
                <td>{{ sub.get('montoCOP', 'N/A') }}</td>
                <td>{{ sub.get('categoria', 'N/A') }}</td>
                <td>{{ sub.get('pagadaCon', 'N/A') }}</td>
                <td>{{ sub.get('pagadaPor', 'N/A') }}</td>
            </tr>
            {% endfor %}
            <tr class="total-row">
                <td>TOTAL</td>
                <td>${{ "%.2f"|format(total_usd) }}</td>
                <td>${{ "%.0f"|format(total_cop) }}</td>
                <td colspan="3"></td>
            </tr>
        </table>
        <p>Este es un mensaje automático generado por el sistema de notificación de gastos recurrentes.</p>
        <div class="footer">
            Generado el {{ today }} a las {{ current_time }}
        </div>
    </body>
    </html>
    """
    
    template = Template(email_template)
    html_content = template.render(
        today=today,
        current_time=datetime.now().strftime("%H:%M:%S"),
        subscriptions=subscriptions,
        total_usd=total_usd,
        total_cop=total_cop
    )
    
    try:
        # Verificar que la API key esté configurada
        if not RESEND_API_KEY:
            logger.error("RESEND_API_KEY no está configurada en el archivo .env")
            return
        
        if not NOTIFICATION_EMAIL:
            logger.error("NOTIFICATION_EMAIL no está configurada en el archivo .env")
            return
        
        # Enviar el correo usando Resend - Código corregido
        resend.api_key = RESEND_API_KEY
        
        params = {
            "from": SENDER_EMAIL,
            "to": [NOTIFICATION_EMAIL],
            "subject": f"Gastos Recurrentes - {today}",
            "html": html_content,
        }
        
        response = resend.Emails.send(params)
        logger.info(f"Notificación enviada: {response}")
    except Exception as e:
        logger.error(f"Error al enviar la notificación: {e}")

def main():
    """Función principal que programa la tarea diaria."""
    logger.info("Servicio de notificación de gastos recurrentes iniciado.")
    
    # Verificar configuración
    if not os.path.exists(CREDENTIALS_FILE):
        logger.error(f"El archivo de credenciales {CREDENTIALS_FILE} no existe")
        return
    
    if not RESEND_API_KEY:
        logger.error("RESEND_API_KEY no está configurada en el archivo .env")
        return
    
    # Mostrar configuración actual
    logger.info(f"Hoja de cálculo: {SPREADSHEET_ID}")
    logger.info(f"Nombre de la hoja: {SHEET_NAME}")
    logger.info(f"Hora de notificación: {NOTIFICATION_TIME}")
    
    # Programar la verificación diaria a la hora configurada
    schedule.every().day.at(NOTIFICATION_TIME).do(check_subscriptions_due)
    logger.info(f"Tarea programada para ejecutarse diariamente a las {NOTIFICATION_TIME}")
    
    # También ejecutamos una vez al iniciar para probar
    check_subscriptions_due()
    
    # Bucle principal para mantener el script en ejecución
    while True:
        schedule.run_pending()
        time.sleep(60)  # Verificar cada minuto si hay tareas pendientes

if __name__ == "__main__":
    main()