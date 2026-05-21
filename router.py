"""
Router: recibe el texto del usuario y decide a qué dominio pertenece.
"""
import json, logging
import gemini
import config

logger = logging.getLogger(__name__)

ROUTER_PROMPT = """Eres el clasificador de mensajes del asistente personal de Txako.
Clasifica el mensaje en UNO de estos dominios:
- "ef": Educación Física, juegos, actividades, sesiones, gimnasio, deporte en clase
- "tutoria": Alumnos, notas, calificaciones, observaciones, informes, familias, Sheets
- "recordatorios": Recordar algo, avisar, que no se olvide, agenda, fechas, horas
- "racing": Instagram, contenido escuela de fútbol, captions, guiones, Reels, Racing Club
- "gastos": Gastos, compras, euros, dinero, pagos, supermercado, precio, coste, cervezas
- "general": Cualquier otra cosa

Responde SOLO con JSON sin markdown:
{"dominio": "ef"}
"""

async def classify(text: str) -> str:
    prompt = ROUTER_PROMPT + f'\n\nMensaje: "{text}"'
    try:
        raw = gemini.ask(prompt)
        raw = raw.strip().replace("```json","").replace("```","").strip()
        data = json.loads(raw)
        domain = data.get("dominio", "general")
        if domain not in config.DOMAINS:
            domain = "general"
        return domain
    except Exception as e:
        logger.error(f"Error clasificando: {e}")
        return "general"
