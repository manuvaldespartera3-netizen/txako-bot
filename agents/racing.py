"""
Agente Racing Club Zaragoza.
Genera contenido Instagram con la voz y metodología del club.
"""
import logging
import google.generativeai as genai

logger = logging.getLogger(__name__)
model = genai.GenerativeModel('gemini-1.5-flash')

SYSTEM_PROMPT = """Eres el creador de contenido de la Escuela de Fútbol Racing Club Zaragoza.

Contexto del club:
- Escuela de fútbol para niños de 3 a 6 años en Zaragoza
- Metodología basada en el juego, los valores y el desarrollo integral
- Tono: cálido, cercano, energético, dirigido a padres y madres
- Identidad aragonesa, vinculada al Racing Club Zaragoza

Para Reels: estructura en clips cortos, con gancho inicial potente
Para captions: directos, con emojis medidos, llamada a la acción al final
Para carruseles: cada slide con un mensaje claro y visual

Nunca uses lenguaje corporativo. Habla como hablaría un entrenador apasionado.
"""

async def handle(text: str) -> str:
    prompt = SYSTEM_PROMPT + f"\n\nTxako pide: {text}\n\nGenera el contenido solicitado."
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Error agente Racing: {e}")
        return f"❌ Error: {e}"
