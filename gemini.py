"""
Cliente IA usando Groq (gratis, rápido, sin límites restrictivos).
Modelo: llama-3.3-70b-versatile
"""
import requests, logging, os

logger = logging.getLogger(__name__)
GROQ_KEY = os.environ.get('GROQ_API_KEY', '')

def ask(prompt: str) -> str:
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1024
            },
            timeout=30
        )
        data = response.json()
        if "choices" not in data:
            error_msg = data.get("error", {}).get("message", str(data))
            logger.error(f"Groq error: {data}")
            return f"❌ Error IA: {error_msg}"
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Error Groq: {e}")
        return f"❌ Error: {str(e)}"
        
