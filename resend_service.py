#!/usr/bin/env python3
# resend_service.py - Servicio para enviar correos usando Resend

import os
import logging
from datetime import datetime
import resend
from jinja2 import Template

# Configurar logger
logger = logging.getLogger("subscription_notifier.resend")

class ResendService:
    def __init__(self, api_key=None, sender_email=None, recipient_email=None):
        """
        Inicializa el servicio de Resend.
        
        Args:
            api_key (str): API key de Resend. Si es None, se intenta obtener de las variables de entorno.
            sender_email (str): Correo del remitente. Si es None, se intenta obtener de las variables de entorno.
            recipient_email (str): Correo del destinatario. Si es None, se intenta obtener de las variables de entorno.
        """
        self.api_key = api_key or os.getenv('RESEND_API_KEY')
        self.sender_email = sender_email or os.getenv('SENDER_EMAIL', 'Notificador de Gastos <gastos@tudominio.com>')
        self.recipient_email = recipient_email or os.getenv('NOTIFICATION_EMAIL')
        
        # Verificar que se hayan configurado las variables necesarias
        if not self.api_key:
            logger.warning("No se ha configurado RESEND_API_KEY")
        
        if not self.recipient_email:
            logger.warning("No se ha configurado NOTIFICATION_EMAIL")
    
    def format_currency(self, value):
        """
        Formatea valores de moneda.
        
        Args:
            value (str|float): Valor a formatear.
            
        Returns:
            float: Valor formateado.
        """
        if isinstance(value, str):
            # Eliminar el símbolo $ y las comas
            value = value.replace('$', '').replace(',', '')
        try:
            return float(value)
        except ValueError:
            return 0.0
    
    def send_subscription_notification(self, subscriptions):
        """
        Envía una notificación por correo con los gastos recurrentes.
        
        Args:
            subscriptions (list): Lista de suscripciones a notificar.
            
        Returns:
            bool: True si se envió correctamente, False en caso contrario.
        """
        if not subscriptions:
            logger.info("No hay suscripciones para notificar")
            return False
        
        today = datetime.now().strftime("%d %B %Y")
        
        # Preparar datos para la plantilla
        try:
            total_usd = sum(self.format_currency(sub["montoUSD"]) for sub in subscriptions)
            total_cop = sum(self.format_currency(sub.get("montoCOP", "0")) for sub in subscriptions)
        except Exception as e:
            logger.error(f"Error al calcular totales: {e}")
            total_usd = 0
            total_cop = 0
        
        # Plantilla HTML para el correo
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
            if not self.api_key:
                logger.error("RESEND_API_KEY no está configurada")
                return False
            
            if not self.recipient_email:
                logger.error("NOTIFICATION_EMAIL no está configurada")
                return False
            
            # Enviar el correo usando Resend
            resend.api_key = self.api_key
            
            params = {
                "from": self.sender_email,
                "to": [self.recipient_email],
                "subject": f"Gastos Recurrentes - {today}",
                "html": html_content,
            }
            
            response = resend.Emails.send(params)
            logger.info(f"Notificación enviada: {response}")
            return True
            
        except Exception as e:
            logger.error(f"Error al enviar la notificación: {e}")
            return False
    
    def send_test_email(self):
        """
        Envía un correo de prueba para verificar la configuración.
        
        Returns:
            bool: True si se envió correctamente, False en caso contrario.
        """
        today = datetime.now().strftime("%d %B %Y")
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # Contenido HTML del correo de prueba
        html_content = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    margin: 0;
                    padding: 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                }}
                h2 {{
                    color: #4CAF50;
                    border-bottom: 2px solid #4CAF50;
                    padding-bottom: 10px;
                }}
                .footer {{
                    margin-top: 30px;
                    font-size: 12px;
                    color: #666;
                    border-top: 1px solid #eee;
                    padding-top: 10px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>Prueba de Configuración de Resend</h2>
                <p>Este es un correo de prueba para validar la configuración de Resend en el Notificador de Gastos Recurrentes.</p>
                <p>Si estás recibiendo este correo, significa que la configuración es correcta y el dominio está verificado.</p>
                <p><strong>Detalles técnicos:</strong></p>
                <ul>
                    <li>Remitente: {self.sender_email}</li>
                    <li>Destinatario: {self.recipient_email}</li>
                    <li>API Key configurada: {'Sí' if self.api_key else 'No'}</li>
                </ul>
                <div class="footer">
                    Generado el {today} a las {current_time}
                </div>
            </div>
        </body>
        </html>
        """
        
        try:
            # Verificar que la API key esté configurada
            if not self.api_key:
                logger.error("RESEND_API_KEY no está configurada")
                return False
            
            if not self.recipient_email:
                logger.error("NOTIFICATION_EMAIL no está configurada")
                return False
            
            # Enviar el correo usando Resend
            resend.api_key = self.api_key
            
            params = {
                "from": self.sender_email,
                "to": [self.recipient_email],
                "subject": f"Prueba de Resend - {today}",
                "html": html_content,
            }
            
            response = resend.Emails.send(params)
            logger.info(f"Correo de prueba enviado: {response}")
            return True
            
        except Exception as e:
            logger.error(f"Error al enviar el correo de prueba: {e}")
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
    resend_service = ResendService()
    
    # Enviar correo de prueba
    if resend_service.send_test_email():
        print("Correo de prueba enviado correctamente!")
    else:
        print("Error al enviar el correo de prueba")