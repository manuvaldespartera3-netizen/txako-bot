"""
Cliente Gemini usando requests directamente.
Sin librerías de Google que cambien y rompan.
"""
import requests, logging, os

logger = logging.getLogger(__name__)
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '')
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

def ask(prompt: str) -> str:
    """Llama a Gemini y devuelve el texto de respuesta."""
    try:
        response = requests.post(
            API_URL,
            params={"key": GEMINI_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30
        )
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Error Gemini: {e} | Response: {response.text if 'response' in dir() else ''}")
        return f"❌ Error de IA: {str(e)}"
