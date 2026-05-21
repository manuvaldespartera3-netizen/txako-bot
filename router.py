"""
Router: recibe el texto del usuario y decide a qué dominio pertenece.
Usa Gemini para clasificar con contexto real.
"""
import json, logging
import google.generativeai as genai
import config

logger = logging.getLogger(__name__)
genai.configure(api_key=config.GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash-latest')

ROUTER_PROMPT = """Eres el clasificador de mensajes del asistente personal de Txako.
Txako es:
- Director de Escuela de Fútbol Racing Club Zaragoza (niños 3-6 años)
- Profesor de Educación Física en primaria
- Tutor de una clase de 25 alumnos

Clasifica el mensaje en UNO de estos dominios:
- "ef": Educación Física, juegos, actividades, materiales deportivos, planificación de sesiones, adaptaciones de clase
- "tutoria": Alumnos, notas, calificaciones, observaciones, informes para familias, Google Sheets
- "recordatorios": Recordar algo, avisar, que no se olvide, agenda, fechas
- "racing": Instagram, contenido para la escuela de fútbol, captions, guiones, Reels
- "gastos": Gastos, compras, euros, dinero, pagos, facturas, supermercado, precio, coste
- "general": Cualquier otra cosa

Responde SOLO con JSON sin markdown:
{"dominio": "ef", "confianza": "alta", "razon": "breve explicación"}
"""

async def classify(text: str) -> str:
    """Devuelve el dominio: 'ef' | 'tutoria' | 'recordatorios' | 'racing' | 'general'"""
    try:
        response = model.generate_content(ROUTER_PROMPT + f'\n\nMensaje: "{text}"')
        raw = response.text.strip().replace('```json','').replace('```','').strip()
        data = json.loads(raw)
        domain = data.get('dominio', 'general')
        if domain not in config.DOMAINS:
            domain = 'general'
        logger.info(f"Clasificado → {domain} (confianza: {data.get('confianza','?')})")
        return domain
    except Exception as e:
        logger.error(f"Error clasificando: {e}")
        return 'general'
