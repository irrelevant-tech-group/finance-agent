#!/usr/bin/env python3
# telegram_bot.py - Bot de Telegram para registrar gastos variables

import os
import logging
import asyncio
from datetime import datetime
import pytz
import tempfile
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

# Importar los servicios modulares
from accounting_service import AccountingService
from resend_service import ResendService
from currency_service import CurrencyService
from invoice_ai_service import InvoiceAIService

# Cargar variables de entorno
load_dotenv()

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("expense_bot")

# Estados de la conversación para el flujo manual
DETALLE, CATEGORIA, SELECCION_MONEDA, MONTO, CONFIRMACION = range(5)

# Estados de la conversación para el flujo de factura
RECIBIR_FACTURA, PROCESANDO_FACTURA, CONFIRMACION_FACTURA = range(5, 8)

# Lista de categorías predefinidas
CATEGORIAS = ["Tech", "Workspace", "Legal", "Marketing", "Suscripciones", "Otros"]


class IrrelevalBot:
    """Bot de Telegram para registro de gastos variables."""

    def __init__(self):
        """Inicializa el bot con la configuración necesaria."""
        self.token = os.getenv('TELEGRAM_TOKEN', '8147530140:AAHraC6GkK4IkvbUj44IuZub0ZskXM2UzDs')

        # Inicializar servicios
        self.accounting_service = AccountingService()
        self.resend_service = ResendService()
        self.currency_service = CurrencyService()
        self.invoice_service = InvoiceAIService()

        # Verificar conexión con hojas de contabilidad
        if not self.accounting_service.test_connection():
            logger.error("No se pudo conectar con las hojas de contabilidad. Verifica la configuración.")

        # Inicializar la aplicación con una zona horaria explícita
        self.application = Application.builder().token(self.token).build()
        self.setup_handlers()

    def setup_handlers(self):
        """Configura los handlers para comandos y mensajes."""
        # Comandos básicos
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))

        # Conversación para registrar gastos manualmente
        conv_handler_manual = ConversationHandler(
            entry_points=[CommandHandler("gasto", self.cmd_gasto)],
            states={
                DETALLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_detalle)],
                CATEGORIA: [CallbackQueryHandler(self.process_categoria)],
                SELECCION_MONEDA: [CallbackQueryHandler(self.process_seleccion_moneda)],
                MONTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_monto)],
                CONFIRMACION: [CallbackQueryHandler(self.process_confirmacion)]
            },
            fallbacks=[CommandHandler("cancelar", self.cmd_cancelar)],
            name="manual_expense"
        )

        # Conversación para registrar gastos por factura
        conv_handler_factura = ConversationHandler(
            entry_points=[CommandHandler("factura", self.cmd_factura)],
            states={
                RECIBIR_FACTURA: [
                    MessageHandler(filters.PHOTO, self.process_factura_photo),
                    MessageHandler(filters.Document.PDF, self.process_factura_pdf)
                ],
                CONFIRMACION_FACTURA: [CallbackQueryHandler(self.process_confirmacion_factura)]
            },
            fallbacks=[CommandHandler("cancelar", self.cmd_cancelar)],
            name="invoice_expense"
        )

        self.application.add_handler(conv_handler_manual)
        self.application.add_handler(conv_handler_factura)

        # Handler para cualquier mensaje que no se capture por los anteriores
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.unknown_message))

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Maneja el comando /start."""
        user = update.effective_user
        logger.info(f"Nuevo usuario: {user.id} - {user.first_name} {user.last_name} (@{user.username})")

        await update.message.reply_text(
            f"👋 Hola {update.effective_user.first_name}!\n\n"
            "Soy el bot de gestión de gastos de Irrelevant Core. "
            "Puedo ayudarte a registrar gastos variables en las hojas de contabilidad.\n\n"
            "📝 Usa /gasto para registrar un gasto manualmente\n"
            "📄 Usa /factura para registrar un gasto a partir de una factura\n"
            "❓ Usa /help para ver más información"
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Maneja el comando /help."""
        await update.message.reply_text(
            "🔍 *Comandos disponibles:*\n\n"
            "/gasto - Registra un gasto manualmente\n"
            "/factura - Registra un gasto a partir de una foto o PDF de factura\n"
            "/cancelar - Cancela el proceso actual\n"
            "/help - Muestra este mensaje de ayuda\n\n"
            "*Uso del comando /factura:*\n"
            "1. Envía /factura\n"
            "2. Envía una foto o PDF de la factura\n"
            "3. El sistema analizará automáticamente la factura\n"
            "4. Confirma la información extraída\n\n"
            "El sistema extraerá automáticamente el detalle, categoría, monto y moneda de la factura.",
            parse_mode='Markdown'
        )

    # ----- Comandos para el flujo manual -----

    async def cmd_gasto(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Inicia el proceso de registro de un gasto manualmente."""
        await update.message.reply_text(
            "📝 Vamos a registrar un nuevo gasto variable.\n\n"
            "Por favor, describe brevemente el gasto:"
        )
        return DETALLE

    async def process_detalle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Procesa el detalle del gasto y solicita la categoría."""
        context.user_data['detalle'] = update.message.text

        # Crear teclado con categorías predefinidas
        keyboard = []
        row = []
        for i, categoria in enumerate(CATEGORIAS):
            row.append(InlineKeyboardButton(categoria, callback_data=categoria))
            # 3 botones por fila
            if (i + 1) % 3 == 0 or i == len(CATEGORIAS) - 1:
                keyboard.append(row)
                row = []

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "🏷️ Selecciona una categoría para el gasto:",
            reply_markup=reply_markup
        )
        return CATEGORIA

    async def process_categoria(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Procesa la categoría seleccionada y solicita la moneda."""
        query = update.callback_query
        await query.answer()

        context.user_data['categoria'] = query.data

        # Crear teclado para selección de moneda
        keyboard = [
            [
                InlineKeyboardButton("💰 COP (Pesos)", callback_data="COP"),
                InlineKeyboardButton("💵 USD (Dólares)", callback_data="USD")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"Categoría seleccionada: *{query.data}*\n\n"
            "💱 Por favor, selecciona la moneda en la que ingresarás el monto:",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return SELECCION_MONEDA

    async def process_seleccion_moneda(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Procesa la selección de moneda y solicita el monto."""
        query = update.callback_query
        await query.answer()

        moneda = query.data
        context.user_data['moneda_seleccionada'] = moneda

        if moneda == "COP":
            mensaje = "💰 Por favor, ingresa el monto en COP (pesos colombianos):\nEjemplo: 100000 o $100,000"
        else:  # USD
            mensaje = "💵 Por favor, ingresa el monto en USD (dólares):\nEjemplo: 25 o $25"

        await query.edit_message_text(
            f"Moneda seleccionada: *{moneda}*\n\n{mensaje}",
            parse_mode='Markdown'
        )
        return MONTO

    async def process_monto(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Procesa el monto ingresado y realiza la conversión automática."""
        monto_str = update.message.text
        moneda_seleccionada = context.user_data['moneda_seleccionada']

        # Parsear el monto
        try:
            # Limpiar y convertir a float
            if monto_str.startswith('$'):
                monto_str = monto_str[1:]
            monto_str = monto_str.replace(',', '').replace('.', '')
            monto = float(monto_str)

            # Guardar monto original
            if moneda_seleccionada == "COP":
                # El usuario ingresó en COP, convertir a USD
                monto_cop = monto
                monto_usd = self.currency_service.convert_cop_to_usd(monto_cop)

                # Formatear montos
                context.user_data['montoCOP'] = self.currency_service.format_cop_amount(monto_cop)
                context.user_data['montoUSD'] = self.currency_service.format_usd_amount(monto_usd)
            else:
                # El usuario ingresó en USD, convertir a COP
                monto_usd = monto
                monto_cop = self.currency_service.convert_usd_to_cop(monto_usd)

                # Formatear montos
                context.user_data['montoUSD'] = self.currency_service.format_usd_amount(monto_usd)
                context.user_data['montoCOP'] = self.currency_service.format_cop_amount(monto_cop)

            # Mostrar resumen y pedir confirmación
            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirmar", callback_data="confirmar"),
                    InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Mensaje con detalles de la conversión
            conversion_info = ""
            if moneda_seleccionada == "COP":
                conversion_info = f"Conversión: {context.user_data['montoCOP']} COP ≈ {context.user_data['montoUSD']} USD"
            else:
                conversion_info = f"Conversión: {context.user_data['montoUSD']} USD ≈ {context.user_data['montoCOP']} COP"

            await update.message.reply_text(
                "📋 *Resumen del gasto:*\n\n"
                f"Detalle: {context.user_data['detalle']}\n"
                f"Categoría: {context.user_data['categoria']}\n"
                f"Monto COP: {context.user_data['montoCOP']}\n"
                f"Monto USD: {context.user_data['montoUSD']}\n"
                f"{conversion_info}\n\n"
                "¿Deseas registrar este gasto?",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            return CONFIRMACION

        except ValueError:
            # Manejar error de formato
            if moneda_seleccionada == "COP":
                mensaje = "⚠️ El monto ingresado no es válido. Por favor, ingresa un número en COP.\nEjemplo: 100000 o $100,000"
            else:
                mensaje = "⚠️ El monto ingresado no es válido. Por favor, ingresa un número en USD.\nEjemplo: 25 o $25"

            await update.message.reply_text(mensaje)
            return MONTO

    async def process_confirmacion(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Procesa la confirmación y registra el gasto si es confirmado."""
        query = update.callback_query
        await query.answer()

        if query.data == "cancelar":
            await query.edit_message_text("❌ Registro de gasto cancelado.")
            return ConversationHandler.END

        # Preparar el gasto para registrarlo
        gasto = [{
            "fecha": datetime.now().strftime("%d/%m/%Y"),
            "detalle": context.user_data['detalle'],
            "categoria": context.user_data['categoria'],
            "montoCOP": context.user_data['montoCOP'],
            "montoUSD": context.user_data['montoUSD']
        }]

        # Registrar el gasto en las hojas de contabilidad
        success = self.accounting_service.register_expenses(gasto)

        if success:
            # Enviar notificación por correo
            email_sent = await self.send_expense_notification(gasto[0])

            message = "✅ *Gasto registrado exitosamente*\n\n"
            if email_sent:
                message += "✉️ Se ha enviado una notificación por correo electrónico."
            else:
                message += "⚠️ No se pudo enviar la notificación por correo."

            await query.edit_message_text(message, parse_mode='Markdown')
        else:
            await query.edit_message_text(
                "❌ Error al registrar el gasto en las hojas de contabilidad.\n"
                "Por favor, intenta nuevamente o contacta al administrador."
            )

        return ConversationHandler.END

    # ----- Comandos para el flujo de factura -----

    async def cmd_factura(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Inicia el proceso de registro de un gasto a partir de una factura."""
        await update.message.reply_text(
            "📄 Vamos a registrar un gasto a partir de una factura.\n\n"
            "Por favor, envía una foto o PDF de la factura."
        )
        return RECIBIR_FACTURA

    async def process_factura_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Procesa una factura enviada como foto."""
        # Mostrar mensaje de procesamiento
        processing_message = await update.message.reply_text(
            "🔍 Procesando la imagen... Por favor espera un momento."
        )

        temp_file_path = None

        try:
            # Obtener el archivo de mayor resolución
            photo_file = await update.message.photo[-1].get_file()

            # Crear un nombre único para el archivo temporal
            import uuid
            temp_file_path = f"temp_invoice_{uuid.uuid4()}.jpg"

            # Descargar la imagen directamente al archivo temporal
            await photo_file.download_to_drive(temp_file_path)

            # Procesar la factura con el servicio de IA
            invoice_info = self.invoice_service.process_invoice(temp_file_path)

            # Actualizar el mensaje de procesamiento
            await processing_message.edit_text(
                "✅ Imagen procesada correctamente."
            )

            # Continuar con la confirmación de la información extraída
            await self.show_invoice_confirmation(update, context, invoice_info)

            return CONFIRMACION_FACTURA

        except Exception as e:
            logger.error(f"Error al procesar la imagen: {e}")
            await processing_message.edit_text(
                "❌ Error al procesar la imagen. Por favor, intenta nuevamente o usa /gasto para registrar manualmente."
            )
            return ConversationHandler.END

        finally:
            # Intentar eliminar el archivo temporal solo si fue creado
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception as e:
                    logger.warning(f"No se pudo eliminar el archivo temporal: {e}")

    async def process_factura_pdf(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Procesa una factura enviada como PDF."""
        # Mostrar mensaje de procesamiento
        processing_message = await update.message.reply_text(
            "🔍 Procesando el PDF... Por favor espera un momento."
        )

        temp_file_path = None

        try:
            # Obtener el archivo PDF
            pdf_file = await update.message.document.get_file()

            # Crear un nombre único para el archivo temporal
            import uuid
            temp_file_path = f"temp_invoice_{uuid.uuid4()}.pdf"

            # Descargar el PDF directamente al archivo temporal
            await pdf_file.download_to_drive(temp_file_path)

            # Procesar la factura con el servicio de IA
            invoice_info = self.invoice_service.process_invoice(temp_file_path)

            # Actualizar el mensaje de procesamiento
            await processing_message.edit_text(
                "✅ PDF procesado correctamente."
            )

            # Continuar con la confirmación de la información extraída
            await self.show_invoice_confirmation(update, context, invoice_info)

            return CONFIRMACION_FACTURA

        except Exception as e:
            logger.error(f"Error al procesar el PDF: {e}")
            await processing_message.edit_text(
                "❌ Error al procesar el PDF. Por favor, intenta nuevamente o usa /gasto para registrar manualmente."
            )
            return ConversationHandler.END

        finally:
            # Intentar eliminar el archivo temporal solo si fue creado
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception as e:
                    logger.warning(f"No se pudo eliminar el archivo temporal: {e}")

    async def show_invoice_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE, invoice_info):
        """Muestra la información extraída de la factura para confirmación."""
        if not invoice_info:
            await update.message.reply_text(
                "❌ No se pudo extraer información de la factura. Por favor, intenta nuevamente o usa /gasto para registrar manualmente."
            )
            return ConversationHandler.END

        # Guardar la información en el contexto
        context.user_data['detalle'] = invoice_info['detalle']
        context.user_data['categoria'] = invoice_info['categoria']

        # Procesar el monto según la moneda detectada
        monto = float(invoice_info['monto'])
        moneda = invoice_info['moneda']

        if moneda == "COP":
            # El monto está en COP, convertir a USD
            monto_cop = monto
            monto_usd = self.currency_service.convert_cop_to_usd(monto_cop)

            # Formatear montos
            context.user_data['montoCOP'] = self.currency_service.format_cop_amount(monto_cop)
            context.user_data['montoUSD'] = self.currency_service.format_usd_amount(monto_usd)
        else:
            # El monto está en USD, convertir a COP
            monto_usd = monto
            monto_cop = self.currency_service.convert_usd_to_cop(monto_usd)

            # Formatear montos
            context.user_data['montoUSD'] = self.currency_service.format_usd_amount(monto_usd)
            context.user_data['montoCOP'] = self.currency_service.format_cop_amount(monto_cop)

        # Guardar la fecha
        context.user_data['fecha'] = invoice_info['fecha']

        # Mensaje con detalles de la conversión
        conversion_info = ""
        if moneda == "COP":
            conversion_info = f"Conversión: {context.user_data['montoCOP']} COP ≈ {context.user_data['montoUSD']} USD"
        else:
            conversion_info = f"Conversión: {context.user_data['montoUSD']} USD ≈ {context.user_data['montoCOP']} COP"

        # Mostrar resumen y pedir confirmación
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirmar", callback_data="confirmar"),
                InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "📋 *Información extraída de la factura:*\n\n"
            f"Fecha: {context.user_data['fecha']}\n"
            f"Detalle: {context.user_data['detalle']}\n"
            f"Categoría: {context.user_data['categoria']}\n"
            f"Monto COP: {context.user_data['montoCOP']}\n"
            f"Monto USD: {context.user_data['montoUSD']}\n"
            f"{conversion_info}\n\n"
            "¿Deseas registrar este gasto?",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    async def process_confirmacion_factura(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Procesa la confirmación de la factura y registra el gasto si es confirmado."""
        query = update.callback_query
        await query.answer()

        if query.data == "cancelar":
            await query.edit_message_text("❌ Registro de gasto cancelado.")
            return ConversationHandler.END

        # Preparar el gasto para registrarlo
        gasto = [{
            "fecha": context.user_data.get('fecha', datetime.now().strftime("%d/%m/%Y")),
            "detalle": context.user_data['detalle'],
            "categoria": context.user_data['categoria'],
            "montoCOP": context.user_data['montoCOP'],
            "montoUSD": context.user_data['montoUSD']
        }]

        # Registrar el gasto en las hojas de contabilidad
        success = self.accounting_service.register_expenses(gasto)

        if success:
            # Enviar notificación por correo
            email_sent = await self.send_expense_notification(gasto[0])

            message = "✅ *Gasto registrado exitosamente*\n\n"
            if email_sent:
                message += "✉️ Se ha enviado una notificación por correo electrónico."
            else:
                message += "⚠️ No se pudo enviar la notificación por correo."

            await query.edit_message_text(message, parse_mode='Markdown')
        else:
            await query.edit_message_text(
                "❌ Error al registrar el gasto en las hojas de contabilidad.\n"
                "Por favor, intenta nuevamente o contacta al administrador."
            )

        return ConversationHandler.END

    # ----- Comandos compartidos -----

    async def cmd_cancelar(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancela el proceso actual."""
        await update.message.reply_text("❌ Operación cancelada.")
        return ConversationHandler.END

    async def unknown_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Maneja mensajes desconocidos."""
        await update.message.reply_text(
            "No entiendo ese comando. Usa /help para ver la lista de comandos disponibles."
        )

    async def send_expense_notification(self, expense):
        """
        Envía una notificación por correo electrónico sobre un nuevo gasto.

        Args:
            expense (dict): Información del gasto registrado.

        Returns:
            bool: True si se envió correctamente, False en caso contrario.
        """
        try:
            # Crear una lista con un solo gasto para usar el método existente
            expenses = [expense]

            # Enviar la notificación
            result = self.resend_service.send_subscription_notification(expenses)

            return result
        except Exception as e:
            logger.error(f"Error al enviar notificación por correo: {e}")
            return False

    def run(self):
        """Ejecuta el bot."""
        logger.info("Iniciando el bot de Telegram para registro de gastos...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


# Este bloque se ejecuta cuando el script se ejecuta directamente
if __name__ == "__main__":
    try:
        # Verificar que pytz esté instalado
        pytz_zone = pytz.timezone('America/Bogota')
        logger.info(f"Zona horaria configurada: {pytz_zone}")

        # Crear y ejecutar el bot
        bot = IrrelevalBot()
        bot.run()
    except ImportError:
        logger.error("Error: Se requiere la biblioteca 'pytz'. Instálala con: pip install pytz")
    except Exception as e:
        logger.error(f"Error al iniciar el bot: {e}")
