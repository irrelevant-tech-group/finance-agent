#!/usr/bin/env python3
# telegram_bot.py - Bot de Telegram para registrar gastos variables

import os
import logging
import asyncio
from datetime import datetime
import pytz
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)

# Importar los servicios modulares
from accounting_service import AccountingService
from resend_service import ResendService

# Cargar variables de entorno
load_dotenv()

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("expense_bot")

# Estados de la conversación
DETALLE, CATEGORIA, MONTO_COP, MONTO_USD, CONFIRMACION = range(5)

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
        
        # Conversación para registrar gastos
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("gasto", self.cmd_gasto)],
            states={
                DETALLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_detalle)],
                CATEGORIA: [CallbackQueryHandler(self.process_categoria)],
                MONTO_COP: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_monto_cop)],
                MONTO_USD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_monto_usd)],
                CONFIRMACION: [CallbackQueryHandler(self.process_confirmacion)]
            },
            fallbacks=[CommandHandler("cancelar", self.cmd_cancelar)]
        )
        self.application.add_handler(conv_handler)
        
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
            "Usa /gasto para registrar un nuevo gasto\n"
            "Usa /help para ver la lista de comandos disponibles"
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Maneja el comando /help."""
        await update.message.reply_text(
            "🔍 *Comandos disponibles:*\n\n"
            "/gasto - Registra un nuevo gasto variable\n"
            "/cancelar - Cancela el proceso actual\n"
            "/help - Muestra este mensaje de ayuda\n\n"
            "Para registrar un gasto, simplemente envía /gasto y sigue las instrucciones.",
            parse_mode='Markdown'
        )
    
    async def cmd_gasto(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Inicia el proceso de registro de un gasto."""
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
        """Procesa la categoría seleccionada y solicita el monto en COP."""
        query = update.callback_query
        await query.answer()
        
        context.user_data['categoria'] = query.data
        
        await query.edit_message_text(
            f"Categoría seleccionada: *{query.data}*\n\n"
            "💰 Por favor, ingresa el monto en COP (pesos colombianos):\n"
            "Ejemplo: 100000 o $100,000",
            parse_mode='Markdown'
        )
        return MONTO_COP
    
    async def process_monto_cop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Procesa el monto en COP y solicita el monto en USD."""
        # Guardar el monto en COP tal como lo ingresó el usuario
        monto_cop = update.message.text
        
        # Si no tiene el formato de moneda ($X,XXX), formatearlo
        if not monto_cop.startswith('$'):
            try:
                # Intentar convertir a float para validar
                valor = float(monto_cop.replace(',', ''))
                # Formatear como moneda
                monto_cop = f"${valor:,.0f}".replace(',', '.')
            except ValueError:
                await update.message.reply_text(
                    "⚠️ El monto ingresado no es válido. Por favor, ingresa un número.\n"
                    "Ejemplo: 100000 o $100,000"
                )
                return MONTO_COP
        
        context.user_data['montoCOP'] = monto_cop
        
        await update.message.reply_text(
            f"Monto COP: *{monto_cop}*\n\n"
            "💵 Por favor, ingresa el monto en USD (dólares):\n"
            "Ejemplo: 25 o $25\n\n"
            "Si no aplica, envía '0' o '$0'",
            parse_mode='Markdown'
        )
        return MONTO_USD
    
    async def process_monto_usd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Procesa el monto en USD y solicita confirmación."""
        # Guardar el monto en USD tal como lo ingresó el usuario
        monto_usd = update.message.text
        
        # Si no tiene el formato de moneda ($X), formatearlo
        if not monto_usd.startswith('$'):
            try:
                # Intentar convertir a float para validar
                valor = float(monto_usd.replace(',', ''))
                # Formatear como moneda
                monto_usd = f"${valor:,.0f}"
            except ValueError:
                await update.message.reply_text(
                    "⚠️ El monto ingresado no es válido. Por favor, ingresa un número.\n"
                    "Ejemplo: 25 o $25"
                )
                return MONTO_USD
        
        context.user_data['montoUSD'] = monto_usd
        
        # Mostrar resumen y pedir confirmación
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirmar", callback_data="confirmar"),
                InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📋 *Resumen del gasto:*\n\n"
            f"Detalle: {context.user_data['detalle']}\n"
            f"Categoría: {context.user_data['categoria']}\n"
            f"Monto COP: {context.user_data['montoCOP']}\n"
            f"Monto USD: {context.user_data['montoUSD']}\n\n"
            "¿Deseas registrar este gasto?",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return CONFIRMACION
    
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
