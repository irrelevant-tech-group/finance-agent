#!/usr/bin/env python3
# invoice_ai_service.py - Servicio para procesar facturas usando IA

import os
import logging
import json
import base64
import requests
from datetime import datetime
from dotenv import load_dotenv
import pytesseract
from PIL import Image
import PyPDF2
import io

# Cargar variables de entorno
load_dotenv()

# Configurar logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("subscription_notifier.invoice_ai")

class InvoiceAIService:
    """Servicio para procesar facturas usando IA."""
    
    def __init__(self):
        """Inicializa el servicio de procesamiento de facturas."""
        # API key para Anthropic/Claude
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        
        # URL del endpoint de Claude
        self.claude_url = "https://api.anthropic.com/v1/messages"
        
        # Modelo a utilizar
        self.model = "claude-3-haiku-20240307"
        
        # Categorías disponibles para clasificación
        self.available_categories = ["Tech", "Workspace", "Legal", "Marketing", "Suscripciones", "Otros"]
    
    def extract_text_from_image(self, image_path):
        """
        Extrae texto de una imagen utilizando OCR.
        
        Args:
            image_path (str): Ruta a la imagen.
            
        Returns:
            str: Texto extraído de la imagen.
        """
        try:
            # Abrir la imagen
            image = Image.open(image_path)
            
            # Extraer texto usando pytesseract
            text = pytesseract.image_to_string(image)
            
            return text
        except Exception as e:
            logger.error(f"Error al extraer texto de la imagen: {e}")
            return ""
    
    def extract_text_from_pdf(self, pdf_path):
        """
        Extrae texto de un PDF.
        
        Args:
            pdf_path (str): Ruta al archivo PDF.
            
        Returns:
            str: Texto extraído del PDF.
        """
        try:
            # Abrir el PDF
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                
                # Extraer texto de todas las páginas
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                
                return text
        except Exception as e:
            logger.error(f"Error al extraer texto del PDF: {e}")
            return ""
    
    def analyze_invoice_with_claude(self, text):
        """
        Analiza el texto de una factura usando Claude para extraer información relevante.
        
        Args:
            text (str): Texto extraído de la factura.
            
        Returns:
            dict: Información extraída de la factura.
        """
        if not self.api_key:
            logger.error("No se ha configurado la API key para Anthropic/Claude")
            return None
        
        try:
            # Crear el prompt para Claude
            prompt = f"""
            Analiza el siguiente texto de una factura y extrae la siguiente información:
            1. Fecha (si está presente, en formato DD/MM/YYYY; si no, usar la fecha actual)
            2. Concepto/Detalle (qué servicio o producto es)
            3. Monto (valor numérico sin símbolos de moneda)
            4. Moneda (determinar si es USD o COP; si no está claro, hacer una suposición basada en el monto - valores grandes como 100,000+ suelen ser COP, valores pequeños como 10-100 suelen ser USD)
            5. Categoría (asignar una de las siguientes: Tech, Workspace, Legal, Marketing, Suscripciones, Otros)

            Texto de la factura:
            ```
            {text}
            ```

            Responde solo con un JSON con los campos:
            {{
                "fecha": "DD/MM/YYYY",
                "detalle": "Descripción del gasto",
                "monto": valor_numérico,
                "moneda": "USD o COP",
                "categoria": "Una de las categorías mencionadas"
            }}
            """
            
            # Configurar los headers
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01"
            }
            
            # Configurar el cuerpo de la solicitud
            data = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 1000
            }
            
            # Hacer la solicitud a la API
            response = requests.post(self.claude_url, headers=headers, json=data)
            
            # Verificar si la solicitud fue exitosa
            if response.status_code == 200:
                response_data = response.json()
                content = response_data["content"][0]["text"]
                
                # Extraer el JSON de la respuesta
                json_str = content.strip()
                
                # Si hay bloques de código, extraer solo el JSON
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()
                
                # Parsear el JSON
                invoice_info = json.loads(json_str)
                
                # Validar los campos
                self.validate_invoice_info(invoice_info)
                
                return invoice_info
            else:
                logger.error(f"Error en la solicitud a Claude: {response.status_code}, {response.text}")
                return None
        
        except Exception as e:
            logger.error(f"Error al analizar la factura con Claude: {e}")
            return None
    
    def validate_invoice_info(self, invoice_info):
        """
        Valida y corrige la información de la factura.
        
        Args:
            invoice_info (dict): Información extraída de la factura.
            
        Returns:
            dict: Información validada y corregida.
        """
        # Verificar si todos los campos están presentes
        required_fields = ["fecha", "detalle", "monto", "moneda", "categoria"]
        for field in required_fields:
            if field not in invoice_info:
                if field == "fecha":
                    invoice_info[field] = datetime.now().strftime("%d/%m/%Y")
                elif field == "detalle":
                    invoice_info[field] = "Gasto no especificado"
                elif field == "monto":
                    invoice_info[field] = 0
                elif field == "moneda":
                    invoice_info[field] = "COP"
                elif field == "categoria":
                    invoice_info[field] = "Otros"
        
        # Verificar la fecha
        try:
            datetime.strptime(invoice_info["fecha"], "%d/%m/%Y")
        except ValueError:
            invoice_info["fecha"] = datetime.now().strftime("%d/%m/%Y")
        
        # Verificar el monto
        if not isinstance(invoice_info["monto"], (int, float)):
            try:
                # Intentar convertir a float
                invoice_info["monto"] = float(str(invoice_info["monto"]).replace(',', '').replace('$', ''))
            except ValueError:
                invoice_info["monto"] = 0
        
        # Verificar la moneda
        if invoice_info["moneda"] not in ["USD", "COP"]:
            # Si el monto es grande, probablemente es COP
            if invoice_info["monto"] > 1000:
                invoice_info["moneda"] = "COP"
            else:
                invoice_info["moneda"] = "USD"
        
        # Verificar la categoría
        if invoice_info["categoria"] not in self.available_categories:
            invoice_info["categoria"] = "Otros"
        
        return invoice_info
    
    def process_invoice(self, file_path):
        """
        Procesa una factura (imagen o PDF) y extrae la información relevante.
        
        Args:
            file_path (str): Ruta al archivo de la factura.
            
        Returns:
            dict: Información extraída de la factura.
        """
        # Determinar el tipo de archivo
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # Extraer texto según el tipo de archivo
        if file_ext in ['.jpg', '.jpeg', '.png']:
            text = self.extract_text_from_image(file_path)
        elif file_ext == '.pdf':
            text = self.extract_text_from_pdf(file_path)
        else:
            logger.error(f"Formato de archivo no soportado: {file_ext}")
            return None
        
        # Si no se pudo extraer texto, devolver None
        if not text:
            logger.error("No se pudo extraer texto del archivo")
            return None
        
        # Analizar el texto con Claude
        invoice_info = self.analyze_invoice_with_claude(text)
        
        return invoice_info


# Para uso como script independiente
if __name__ == "__main__":
    # Crear instancia del servicio
    invoice_service = InvoiceAIService()
    
    # Ruta al archivo de prueba (cambiar según sea necesario)
    test_file = "factura_ejemplo.jpg"
    
    # Procesar factura
    if os.path.exists(test_file):
        print(f"Procesando factura: {test_file}")
        result = invoice_service.process_invoice(test_file)
        if result:
            print(f"Información extraída:\n{json.dumps(result, indent=2)}")
        else:
            print("No se pudo extraer información de la factura")
    else:
        print(f"El archivo {test_file} no existe")