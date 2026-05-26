"""Agente Tutoría."""
import json, logging
import gemini
from integrations.sheets import (
    list_tabs, parse_grade_command, find_cell, write_grade
)

logger = logging.getLogger(__name__)

# Notas pendientes de confirmación por chat_id
pending_grades: dict[int, dict] = {}

SYSTEM = """Eres el asistente de tutoría de Txako, profesor de primaria con 25 alumnos.
Ayuda con gestión de alumnos, observaciones e informes para familias.
Responde en español, de forma directa y práctica."""

GRADE_KEYWORDS = [
    'nota', 'calificacion', 'calificación', 'aprobado', 'suspenso',
    'sobresaliente', 'notable', 'bien', 'suficiente', 'insuficiente',
    'punto', 'puntos', 'sobre', 'saca', 'tiene', 'pongo', 'pon'
]

def looks_like_grade(text: str) -> bool:
    text_lower = text.lower()
    has_keyword = any(k in text_lower for k in GRADE_KEYWORDS)
    has_number = any(c.isdigit() for c in text)
    return has_keyword or has_number

async def handle(text: str, chat_id: int, is_voice: bool = False) -> str:
    text_lower = text.lower()

    # Confirmación pendiente
    if text_lower.strip() in ['si', 'sí', 'yes', 'confirmar', 'ok']:
        return await confirm_grade(chat_id)

    if text_lower.strip() in ['no', 'cancelar', 'cancel']:
        return cancel_grade(chat_id)

    # Informe para familia
    if 'informe' in text_lower or 'familia' in text_lower:
        prompt = SYSTEM + f"\n\nGenera un informe de tutoría profesional y cercano para enviar a la familia. Máximo 200 palabras. Listo para copiar y enviar.\n\nTxako dice: {text}"
        return gemini.ask(prompt)

    # Detección de nota
    if looks_like_grade(text):
        tabs = list_tabs()
        if not tabs:
            return "❌ No puedo conectar con Google Sheets ahora mismo."

        parsed = await parse_grade_command(text, tabs)
        if not parsed:
            return "No he entendido bien la nota. Dime por ejemplo: *Lucía Martínez, cálculo 22 mayo, 7*"

        cell = find_cell(parsed['pestana'], parsed['alumno'], parsed['prueba'])

        if not cell:
            return (
                f"No encuentro a *{parsed['alumno']}* en la pestaña *{parsed['pestana']}* "
                f"o la prueba *{parsed['prueba']}* no existe como columna. "
                f"¿Está bien escrito?"
            )

        # Guardar pendiente y pedir confirmación
        pending_grades[chat_id] = {
            'tab': cell['tab'],
            'row': cell['row'],
            'col': cell['col'],
            'alumno': cell['student_found'],
            'prueba': cell['test_found'],
            'nota': parsed['nota']
        }

        return (
            f"📋 Confirma que es correcto:\n\n"
            f"👤 Alumno: *{cell['student_found']}*\n"
            f"📝 Prueba: *{cell['test_found']}*\n"
            f"🗂 Pestaña: *{cell['tab']}*\n"
            f"🔢 Nota: *{parsed['nota']}*\n\n"
            f"¿Lo guardo? Responde *sí* o *no*"
        )

    # Consulta general
    prompt = SYSTEM + f"\n\nConsulta: {text}"
    return gemini.ask(prompt)


async def confirm_grade(chat_id: int) -> str:
    pending = pending_grades.get(chat_id)
    if not pending:
        return "No hay ninguna nota pendiente de confirmar."
    success = write_grade(pending['tab'], pending['row'], pending['col'], pending['nota'])
    del pending_grades[chat_id]
    if success:
        return f"✅ Guardado: *{pending['alumno']}* → {pending['prueba']} → *{pending['nota']}*"
    return "❌ Error escribiendo en la hoja. Revisa que el bot tiene acceso al Sheet."


def cancel_grade(chat_id: int) -> str:
    if chat_id in pending_grades:
        del pending_grades[chat_id]
    return "❌ Cancelado. No se ha guardado nada."
