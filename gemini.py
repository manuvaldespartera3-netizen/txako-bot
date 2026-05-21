"""
Cliente Gemini usando requests directamente.
"""
import requests, logging, os

logger = logging.getLogger(__name__)
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '')
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

def ask(prompt: str) -> str:
    try:
        response = requests.post(
            API_URL,
            params={"key": GEMINI_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=30
        )
        data = response.json()
        
        # Log completo para debug
        if "candidates" not in data:
            error_msg = data.get("error", {}).get("message", str(data))
            logger.error(f"Gemini error completo: {data}")
            return f"❌ Error Gemini: {error_msg}"
        
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Error Gemini excepción: {e}")
        return f"❌ Error: {str(e)}"
