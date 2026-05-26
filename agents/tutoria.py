"""Agente Tutoría."""
import json, logging, re
import gemini as gemini_module
from integrations.sheets import (
    list_tabs, parse_grade_command, find_cell, write_grade
)

logger = logging.getLogger(__name__)

pending_grades: dict[int, dict] = {}

SYSTEM = """Eres el asistente de tutoría de Txako, profesor de primaria con 25 alumnos.
Ayuda con gestión de alumnos, observaciones e informes para familias.
Responde en español, de forma directa y práctica."""

def looks_like_grade(text: str) -> bool:
    text_lower = text.lower()
    has_number = bool(re.search(r'\d', text))
    grade_words = ['nota', 'calificacion', 'calificación', 'aprobado', 'suspenso',
                   'sobresaliente', 'notable', 'bien', 'suficiente', 'insuficiente',
                   'punto', 'puntos', 'saca', 'tiene', 'pongo', 'pon', 'cálculo',
                   'calculo', 'examen', 'prueba', 'test', 'lectura', 'dictado',
                   'matematicas', 'matemáticas', 'lengua', 'trimestre']
    has_keyword = any(k in text_lower for k in grade_words)
    # Si tiene número Y alguna palabra clave, o si tiene número y parece un nombre
    has_name = len(text.split()) >= 3
    return (has_number and has_keyword) or (has_number and has_name)

async def handle(text: str, chat_id: int, is_voice: bool = False) -> str:
    text_lower = text.lower().strip()

    # Confirmación pendiente
    if text_lower in ['si', 'sí', 'yes', 'confirmar', 'ok', 'correcto', 'vale']:
        return await confirm_grade(chat_id)

    if text_lower in ['no', 'cancelar', 'cancel']:
        return cancel_grade(chat_id)

    # Informe para familia
    if 'informe' in text_lower or 'familia' in text_lower:
        prompt = SYSTEM + f"\n\nGenera un informe de tutoría profesional y cercano para la familia. Máximo 200 palabras.\n\nTxako dice: {text}"
        return gemini_module.ask(prompt)

    # Detección de nota
    if looks_like_grade(text):
        tabs = list_tabs()
        if not tabs:
            return "❌ No puedo conectar con Google Sheets ahora mismo."

        parsed = await parse_grade_command(text, tabs)

        if not parsed:
            return (
                f"No he entendido bien la nota. Dime por ejemplo:\n"
                f"*Lucía Martínez, cálculo 22 mayo, 7*\n\n"
                f"Las pestañas disponibles son: {', '.join(tabs)}"
            )

        cell = find_cell(parsed['pestana'], parsed['alumno'], parsed['prueba'])

        if not cell:
            return (
                f"He entendido esto:\n"
                f"👤 Alumno: *{parsed['alumno']}*\n"
                f"📝 Prueba: *{parsed['prueba']}*\n"
                f"🗂 Pestaña buscada: *{parsed['pestana']}*\n\n"
                f"Pero no encuentro ese alumno o prueba en la hoja. "
                f"¿Está bien escrito el nombre y la columna existe?"
            )

        pending_grades[chat_id] = {
            'tab': cell['tab'],
            'row': cell['row'],
            'col': cell['col'],
            'alumno': cell['student_found'],
            'prueba': cell['test_found'],
            'nota': parsed['nota']
        }

        return (
            f"📋 Confirma:\n\n"
            f"👤 Alumno: *{cell['student_found']}*\n"
            f"📝 Prueba: *{cell['test_found']}*\n"
            f"🗂 Pestaña: *{cell['tab']}*\n"
            f"🔢 Nota: *{parsed['nota']}*\n\n"
            f"¿Lo guardo? Responde *sí* o *no*"
        )

    # Consulta general de tutoría
    prompt = SYSTEM + f"\n\nConsulta: {text}"
    return gemini_module.ask(prompt)


async def confirm_grade(chat_id: int) -> str:
    pending = pending_grades.get(chat_id)
    if not pending:
        return "No hay ninguna nota pendiente de confirmar."
    success = write_grade(pending['tab'], pending['row'], pending['col'], pending['nota'])
    del pending_grades[chat_id]
    if success:
        return f"✅ Guardado: *{pending['alumno']}* → {pending['prueba']} → *{pending['nota']}*"
    return "❌ Error escribiendo en la hoja."


def cancel_grade(chat_id: int) -> str:
    if chat_id in pending_grades:
        del pending_grades[chat_id]
    return "❌ Cancelado. No se ha guardado nada."
