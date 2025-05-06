#!/usr/bin/env python3
# main.py - Script principal para el Notificador de Gastos Recurrentes
# Autor: Claude
# Fecha: Mayo 2025

import os
import schedule
import time
import logging
from datetime import datetime
from dotenv import load_dotenv

# Importar los servicios modulares
from sheets_service import SheetsService
from resend_service import ResendService
from accounting_service import AccountingService

# Cargar variables de entorno
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
NOTIFICATION_TIME = os.getenv('NOTIFICATION_TIME', '08:00')

def check_subscriptions_due():
    """Verifica si hay suscripciones que se causan hoy, envía notificaciones y registra en contabilidad."""
    logger.info(f"Ejecutando verificación de suscripciones: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    
    # Crear instancias de los servicios
    sheets_service = SheetsService()
    resend_service = ResendService()
    accounting_service = AccountingService()
    
    # Obtener suscripciones que se causan hoy
    due_subscriptions = sheets_service.get_due_subscriptions()
    
    if due_subscriptions:
        # 1. Registrar en la hoja de contabilidad
        if accounting_service.register_expenses(due_subscriptions):
            logger.info(f"Gastos registrados correctamente en la hoja de contabilidad")
        else:
            logger.error("Error al registrar gastos en la hoja de contabilidad")
        
        # 2. Enviar notificación por correo
        if resend_service.send_subscription_notification(due_subscriptions):
            logger.info(f"Notificación enviada para {len(due_subscriptions)} suscripciones")
        else:
            logger.error("Error al enviar la notificación")
    else:
        logger.info("No hay suscripciones por cobrar hoy")

def main():
    """Función principal que programa la tarea diaria."""
    logger.info("Servicio de notificación de gastos recurrentes iniciado")
    
    # Mostrar configuración actual
    sheets_service = SheetsService()
    resend_service = ResendService()
    accounting_service = AccountingService()
    
    logger.info(f"Archivo de credenciales: {sheets_service.credentials_file}")
    logger.info(f"Hoja de cálculo (suscripciones): {sheets_service.spreadsheet_id}")
    logger.info(f"Nombre de la hoja (suscripciones): {sheets_service.sheet_name}")
    logger.info(f"Hoja de cálculo (contabilidad): {accounting_service.spreadsheet_id}")
    logger.info(f"Nombre de la hoja (contabilidad): {accounting_service.sheet_name}")
    logger.info(f"Hora de notificación: {NOTIFICATION_TIME}")
    logger.info(f"Correo remitente: {resend_service.sender_email}")
    logger.info(f"Correo destinatario: {resend_service.recipient_email}")
    
    # Verificar configuración
    if not os.path.exists(sheets_service.credentials_file):
        logger.error(f"El archivo de credenciales {sheets_service.credentials_file} no existe")
        return
    
    if not resend_service.api_key:
        logger.error("RESEND_API_KEY no está configurada en el archivo .env")
        return
    
    if not resend_service.recipient_email:
        logger.error("NOTIFICATION_EMAIL no está configurada en el archivo .env")
        return
    
    # Verificar conexión con la hoja de contabilidad
    if not accounting_service.test_connection():
        logger.error("No se pudo conectar con la hoja de contabilidad")
        return
    
    # Programar la verificación diaria a la hora configurada
    schedule.every().day.at(NOTIFICATION_TIME).do(check_subscriptions_due)
    logger.info(f"Tarea programada para ejecutarse diariamente a las {NOTIFICATION_TIME}")
    
    # También ejecutamos una vez al iniciar para probar
    logger.info("Ejecutando verificación inicial de prueba")
    check_subscriptions_due()
    
    # Bucle principal para mantener el script en ejecución
    logger.info("Iniciando bucle principal del servicio")
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Verificar cada minuto si hay tareas pendientes
    except KeyboardInterrupt:
        logger.info("Servicio detenido por el usuario")
    except Exception as e:
        logger.error(f"Error inesperado en el bucle principal: {e}")

if __name__ == "__main__":
    main()