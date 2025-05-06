#!/usr/bin/env python3
# test.py - Script para probar la configuración y funcionamiento del notificador

import os
import logging
import argparse
from datetime import datetime
from dotenv import load_dotenv

# Importar los servicios modulares
from sheets_service import SheetsService
from resend_service import ResendService
from accounting_service import AccountingService

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("subscription_notifier_test")

def test_sheets_service():
    """Prueba la conexión con Google Sheets y la carga de datos."""
    logger.info("Probando servicio de Google Sheets...")
    
    # Crear instancia del servicio
    sheets_service = SheetsService()
    
    # Verificar archivo de credenciales
    if not os.path.exists(sheets_service.credentials_file):
        logger.error(f"❌ El archivo de credenciales {sheets_service.credentials_file} no existe")
        return False
    
    logger.info(f"✓ Archivo de credenciales encontrado: {sheets_service.credentials_file}")
    
    # Verificar conexión a Google Sheets
    service = sheets_service.get_service()
    if not service:
        logger.error("❌ No se pudo conectar con Google Sheets")
        return False
    
    logger.info("✓ Conexión exitosa con Google Sheets")
    
    # Cargar suscripciones
    subscriptions = sheets_service.load_subscriptions()
    if not subscriptions:
        logger.error("❌ No se pudieron cargar las suscripciones")
        return False
    
    logger.info(f"✓ Se cargaron {len(subscriptions)} suscripciones")
    
    # Mostrar algunas suscripciones de ejemplo
    logger.info("Ejemplos de suscripciones cargadas:")
    for i, sub in enumerate(subscriptions[:3]):  # Mostrar hasta 3 como ejemplo
        logger.info(f"  {i+1}. {sub.get('detalle', 'Sin nombre')}: ${sub.get('montoUSD', '0')} ({sub.get('estado', 'desconocido')})")
    
    # Probar obtención de suscripciones del día
    due_today = sheets_service.get_due_subscriptions()
    logger.info(f"✓ Suscripciones que se causan hoy: {len(due_today)}")
    
    return True

def test_resend_service():
    """Prueba el servicio de Resend enviando un correo de prueba."""
    logger.info("Probando servicio de Resend...")
    
    # Crear instancia del servicio
    resend_service = ResendService()
    
    # Verificar configuración
    if not resend_service.api_key:
        logger.error("❌ RESEND_API_KEY no está configurada en el archivo .env")
        return False
    
    logger.info("✓ API key de Resend configurada")
    
    if not resend_service.recipient_email:
        logger.error("❌ NOTIFICATION_EMAIL no está configurada en el archivo .env")
        return False
    
    logger.info(f"✓ Correo destinatario configurado: {resend_service.recipient_email}")
    
    # Preguntar antes de enviar el correo de prueba
    answer = input("¿Deseas enviar un correo de prueba? (s/n): ")
    if answer.lower() != 's':
        logger.info("Prueba de envío de correo omitida por el usuario")
        return True
    
    # Enviar correo de prueba
    if resend_service.send_test_email():
        logger.info("✓ Correo de prueba enviado exitosamente")
        return True
    else:
        logger.error("❌ Error al enviar el correo de prueba")
        return False

def test_accounting_service():
    """Prueba el servicio de contabilidad para registrar gastos."""
    logger.info("Probando servicio de contabilidad...")
    
    # Crear instancia del servicio
    accounting_service = AccountingService()
    
    # Verificar archivo de credenciales
    if not os.path.exists(accounting_service.credentials_file):
        logger.error(f"❌ El archivo de credenciales {accounting_service.credentials_file} no existe")
        return False
    
    logger.info(f"✓ Archivo de credenciales encontrado: {accounting_service.credentials_file}")
    
    # Probar conexión con la hoja de contabilidad
    if not accounting_service.test_connection():
        logger.error("❌ No se pudo conectar con la hoja de contabilidad")
        return False
    
    logger.info("✓ Conexión exitosa con la hoja de contabilidad")
    
    # Preguntar si quiere registrar un gasto de prueba
    answer = input("¿Deseas registrar un gasto de prueba en la hoja de contabilidad? (s/n): ")
    if answer.lower() != 's':
        logger.info("Prueba de registro de gasto omitida por el usuario")
        return True
    
    # Crear un gasto de prueba
    test_expense = [{
        "fecha": datetime.now().strftime("%d/%m/%Y"),
        "detalle": "Gasto de Prueba (Test)",
        "montoUSD": "$10",
        "montoCOP": "$43,000",
        "categoria": "Prueba"
    }]
    
    # Registrar el gasto de prueba
    if accounting_service.register_expenses(test_expense):
        logger.info("✓ Gasto de prueba registrado exitosamente")
        logger.info("  NOTA: Es recomendable eliminar manualmente este gasto de prueba de la hoja de contabilidad")
        return True
    else:
        logger.error("❌ Error al registrar el gasto de prueba")
        return False

def test_complete_flow():
    """Prueba el flujo completo del notificador."""
    logger.info("Probando flujo completo del notificador...")
    
    # Crear instancias de los servicios
    sheets_service = SheetsService()
    resend_service = ResendService()
    accounting_service = AccountingService()
    
    # Obtener suscripciones que se causan hoy
    due_subscriptions = sheets_service.get_due_subscriptions()
    
    if not due_subscriptions:
        logger.info("No hay suscripciones que se causen hoy")
        
        # Preguntamos si quiere continuar con la prueba usando datos de ejemplo
        answer = input("No hay suscripciones para hoy. ¿Quieres crear una suscripción de ejemplo para la prueba? (s/n): ")
        if answer.lower() == 's':
            # Crear suscripción de ejemplo para la prueba
            due_subscriptions = [{
                "fecha": datetime.now().strftime("%d/%m/%Y"),
                "detalle": "Suscripción de Prueba (Flujo Completo)",
                "montoUSD": "$25",
                "montoCOP": "$100,000",
                "categoria": "Prueba",
                "pagadaCon": "Tarjeta de Prueba",
                "pagadaPor": "Usuario de Prueba",
                "estado": "Activo"
            }]
            logger.info("Se ha creado una suscripción de ejemplo para la prueba")
        else:
            logger.info("Prueba de flujo completo omitida por falta de suscripciones")
            return True
    
    # Preguntar antes de ejecutar el flujo completo
    if due_subscriptions:
        logger.info(f"Se encontraron {len(due_subscriptions)} suscripciones para procesar hoy")
        answer = input("¿Deseas ejecutar el flujo completo con estas suscripciones? (s/n): ")
        if answer.lower() != 's':
            logger.info("Prueba de flujo completo omitida por el usuario")
            return True
        
        # 1. Registrar en contabilidad
        logger.info("Paso 1: Registrando gastos en la hoja de contabilidad...")
        if accounting_service.register_expenses(due_subscriptions):
            logger.info("✓ Gastos registrados correctamente en contabilidad")
        else:
            logger.error("❌ Error al registrar gastos en contabilidad")
            return False
        
        # 2. Enviar notificación
        logger.info("Paso 2: Enviando notificación por correo...")
        if resend_service.send_subscription_notification(due_subscriptions):
            logger.info("✓ Notificación enviada exitosamente")
        else:
            logger.error("❌ Error al enviar la notificación")
            return False
        
        logger.info("✓ Flujo completo ejecutado con éxito")
        logger.info("  NOTA: Si usaste datos de prueba, es recomendable eliminar manualmente el gasto de prueba de la hoja de contabilidad")
        return True
    
    return True

def main():
    """Función principal para ejecutar las pruebas."""
    # Cargar variables de entorno
    load_dotenv()
    
    parser = argparse.ArgumentParser(description='Pruebas para el Notificador de Gastos Recurrentes')
    parser.add_argument('--sheets', action='store_true', help='Probar solo la conexión con Google Sheets')
    parser.add_argument('--resend', action='store_true', help='Probar solo el servicio de Resend')
    parser.add_argument('--accounting', action='store_true', help='Probar solo el servicio de contabilidad')
    parser.add_argument('--all', action='store_true', help='Probar todo el flujo')
    
    args = parser.parse_args()
    
    print("\n===== PRUEBA DEL NOTIFICADOR DE GASTOS RECURRENTES =====\n")
    
    all_ok = True
    
    # Si no se especifica ninguna opción, probar todo
    if not (args.sheets or args.resend or args.accounting or args.all):
        args.all = True
    
    # Probar Google Sheets
    if args.sheets or args.all:
        print("\n----- Prueba de Google Sheets -----\n")
        if not test_sheets_service():
            all_ok = False
    
    # Probar Resend
    if args.resend or args.all:
        print("\n----- Prueba de Resend -----\n")
        if not test_resend_service():
            all_ok = False
    
    # Probar servicio de contabilidad
    if args.accounting or args.all:
        print("\n----- Prueba de Servicio de Contabilidad -----\n")
        if not test_accounting_service():
            all_ok = False
    
    # Probar flujo completo
    if args.all:
        print("\n----- Prueba de Flujo Completo -----\n")
        if not test_complete_flow():
            all_ok = False
    
    print("\n===== RESULTADOS DE LAS PRUEBAS =====\n")
    if all_ok:
        print("✅ Todas las pruebas pasaron exitosamente.")
        print("El notificador está correctamente configurado y listo para usar.")
    else:
        print("❌ Algunas pruebas fallaron.")
        print("Por favor, revisa los errores y corrige la configuración.")
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    main()