"""
Agente Tutoría.
Gestiona: notas en Sheets (por voz), alumnos, observaciones, informes.
"""
import logging
import google.generativeai as genai
from integrations.sheets import (
    list_tabs, parse_grade_command, find_cell, write_grade
)
import config, db

logger = logging.getLogger(__name__)
model = genai.GenerativeModel('gemini-1.5-flash')

# Estado temporal para confirmaciones de notas pendientes
pending_grades: dict = {}  # {chat_id: {alumno, prueba, nota, tab, row, col}}

SYSTEM_PROMPT = """Eres el asistente de tutoría de Txako, profesor de primaria.
Ayudas con gestión de alumnos, notas, observaciones e informes para familias.
Responde siempre en español, de forma directa y práctica.
Sé concreto: si generas un informe, que esté listo para copiar y enviar.
"""

async def handle(text: str, chat_id: int, is_voice: bool = False) -> str:
    """
    Punto de entrada del agente de tutoría.
    Detecta si es una nota, una consulta de alumno, un informe, etc.
    """
    text_lower = text.lower()

    # ── Detectar intención de meter nota ──────────────────
    note_keywords = [
        'nota', 'calificacion', 'calificación', 'sacó', 'saco', 'tiene un',
        'ha sacado', 'poner', 'anotar', 'apuntar', 'prueba', 'examen',
        'test', 'evaluación', 'evaluacion'
    ]
    is_grade_intent = is_voice or any(k in text_lower for k in note_keywords)

    if is_grade_intent:
        return await handle_grade(text, chat_id)

    # ── Informe para familia ───────────────────────────────
    if 'informe' in text_lower or 'familia' in text_lower:
        return await generate_report(text)

    # ── Consulta general de tutoría ───────────────────────
    return await general_tutoria(text)


async def handle_grade(text: str, chat_id: int) -> str:
    """Parsea nota, busca celda y pide confirmación antes de escribir."""
    tabs = list_tabs()
    if not tabs:
        return "❌ No puedo acceder a la hoja de Google Sheets. Comprueba la configuración."

    parsed = await parse_grade_command(text, tabs)
    if not parsed:
        return (
            "No entendí la nota. Dímela así:\n\n"
            "_\"Carlos García, prueba de salto, 7\"_\n"
            "_\"Lucía Martínez cálculo mental seis y medio\"_"
        )

    alumno = parsed['alumno']
    prueba = parsed['prueba']
    nota   = parsed['nota']
    tab    = parsed.get('pestana', tabs[0])

    # Buscar celda exacta
    cell = find_cell(tab, alumno, prueba)

    if not cell:
        return (
            f"⚠️ No encontré la combinación:\n"
            f"• Alumno: *{alumno}*\n"
            f"• Prueba: *{prueba}*\n"
            f"• Pestaña: *{tab}*\n\n"
            f"Comprueba que el nombre y la prueba existen en la hoja.\n"
            f"Pestañas disponibles: {', '.join(tabs)}"
        )

    # Guardar pendiente para confirmación
    pending_grades[chat_id] = {
        'alumno': cell['student_found'],
        'prueba': cell['test_found'],
        'nota': nota,
        'tab': cell['tab'],
        'row': cell['row'],
        'col': cell['col'],
    }

    return (
        f"📝 *Confirma antes de guardar:*\n\n"
        f"• Alumno: *{cell['student_found']}*\n"
        f"• Prueba: *{cell['test_found']}*\n"
        f"• Nota: *{nota}*\n"
        f"• Pestaña: *{cell['tab']}*\n\n"
        f"¿Correcto? Responde *sí* para guardar o *no* para cancelar."
    )

async def confirm_grade(chat_id: int) -> str:
    """Escribe la nota confirmada en Sheets."""
    pending = pending_grades.get(chat_id)
    if not pending:
        return "No hay ninguna nota pendiente de confirmar."
    
    success = write_grade(pending['tab'], pending['row'], pending['col'], pending['nota'])
    del pending_grades[chat_id]

    if success:
        return f"✅ Guardado: *{pending['alumno']}* → {pending['prueba']} → **{pending['nota']}**"
    else:
        return "❌ Error escribiendo en la hoja. Inténtalo de nuevo."

def cancel_grade(chat_id: int) -> str:
    if chat_id in pending_grades:
        del pending_grades[chat_id]
    return "❌ Cancelado. No se guardó nada."

async def generate_report(text: str) -> str:
    """Genera informe para familia."""
    prompt = (
        SYSTEM_PROMPT
        + f"\n\nTxako dice: {text}\n\n"
        "Genera un informe de tutoría profesional y cercano para enviar a la familia. "
        "Máximo 200 palabras. Listo para copiar y enviar por WhatsApp o email."
    )
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ Error generando informe: {e}"

async def general_tutoria(text: str) -> str:
    """Respuesta general de tutoría."""
    prompt = SYSTEM_PROMPT + f"\n\nConsulta de Txako: {text}"
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"❌ Error: {e}"
