"""Agente Tutoría."""
import json, logging
import gemini

logger = logging.getLogger(__name__)
pending_grades: dict[int, dict] = {}

SYSTEM = """Eres el asistente de tutoría de Txako, profesor de primaria con 25 alumnos.
Ayuda con gestión de alumnos, observaciones e informes para familias.
Responde en español, de forma directa y práctica."""

async def handle(text: str, chat_id: int, is_voice: bool = False) -> str:
    text_lower = text.lower()
    if 'informe' in text_lower or 'familia' in text_lower:
        prompt = SYSTEM + f"\n\nGenera un informe de tutoría profesional y cercano para enviar a la familia. Máximo 200 palabras. Listo para copiar y enviar.\n\nTxako dice: {text}"
        return gemini.ask(prompt)
    prompt = SYSTEM + f"\n\nConsulta: {text}"
    return gemini.ask(prompt)

async def confirm_grade(chat_id: int) -> str:
    from integrations.sheets import write_grade
    pending = pending_grades.get(chat_id)
    if not pending:
        return "No hay ninguna nota pendiente."
    success = write_grade(pending['tab'], pending['row'], pending['col'], pending['nota'])
    del pending_grades[chat_id]
    if success:
        return f"✅ Guardado: *{pending['alumno']}* → {pending['prueba']} → **{pending['nota']}**"
    return "❌ Error escribiendo en la hoja."

def cancel_grade(chat_id: int) -> str:
    if chat_id in pending_grades:
        del pending_grades[chat_id]
    return "❌ Cancelado."
