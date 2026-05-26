"""Agente Tutoría."""
import logging, re
import gemini as gemini_module
from integrations.sheets import (
    list_tabs, parse_grade_command, parse_batch_grades,
    find_cell, find_cell_all_tabs, write_grade, write_grades_batch,
    create_test_column
)

logger = logging.getLogger(__name__)

pending_grades: dict[int, dict] = {}
pending_batch: dict[int, dict] = {}
pending_new_col: dict[int, dict] = {}

SYSTEM = """Eres el asistente de tutoría de Txako, profesor de primaria con 25 alumnos.
Ayuda con gestión de alumnos, observaciones e informes para familias.
Responde en español, de forma directa y práctica."""

def looks_like_grade(text: str) -> bool:
    text_lower = text.lower()
    has_number = bool(re.search(r'\d', text))
    grade_words = ['cálculo', 'calculo', 'examen', 'prueba', 'test',
                   'lectura', 'dictado', 'matematicas', 'matemáticas',
                   'lengua', 'trimestre', 'nota', 'calificacion']
    has_keyword = any(k in text_lower for k in grade_words)
    has_name = len(text.split()) >= 3
    return (has_number and has_keyword) or (has_number and has_name)

def looks_like_batch(text: str) -> bool:
    """Detecta formato batch: prueba + varios alumnos con notas."""
    has_separator = ';' in text or (text.count(',') >= 3)
    has_number = bool(re.search(r'\d', text))
    return has_separator and has_number

async def handle(text: str, chat_id: int, is_voice: bool = False) -> str:
    text_lower = text.lower().strip()

    # ── Respuesta a confirmación de nota individual ────────
    if chat_id in pending_grades:
        if text_lower in ['si', 'sí', 'yes', 'confirmar', 'ok', 'correcto', 'vale']:
            return await confirm_grade(chat_id)
        elif text_lower in ['no', 'cancelar', 'cancel']:
            return cancel_grade(chat_id)

    # ── Respuesta a confirmación de batch ─────────────────
    if chat_id in pending_batch:
        if text_lower in ['si', 'sí', 'yes', 'confirmar', 'ok', 'correcto', 'vale']:
            return await confirm_batch(chat_id)
        elif text_lower in ['no', 'cancelar', 'cancel']:
            del pending_batch[chat_id]
            return "❌ Cancelado."

    # ── Respuesta a crear columna nueva ───────────────────
    if chat_id in pending_new_col:
        if text_lower in ['si', 'sí', 'yes', 'ok', 'vale', 'crear', 'crea']:
            return await create_col_and_continue(chat_id)
        elif text_lower in ['no', 'cancelar', 'cancel']:
            del pending_new_col[chat_id]
            return "❌ Cancelado. No se ha creado ninguna columna."

    # ── Informe para familia ───────────────────────────────
    if 'informe' in text_lower or 'familia' in text_lower:
        prompt = SYSTEM + f"\n\nGenera un informe de tutoría profesional y cercano para la familia. Máximo 200 palabras.\n\nTxako dice: {text}"
        return gemini_module.ask(prompt)

    # ── Batch: varios alumnos a la vez ────────────────────
    if looks_like_batch(text):
        return await handle_batch(text, chat_id)

    # ── Nota individual ───────────────────────────────────
    if looks_like_grade(text):
        return await handle_single_grade(text, chat_id)

    # ── Consulta general ──────────────────────────────────
    prompt = SYSTEM + f"\n\nConsulta: {text}"
    return gemini_module.ask(prompt)


async def handle_single_grade(text: str, chat_id: int) -> str:
    tabs = list_tabs()
    if not tabs:
        return "❌ No puedo conectar con Google Sheets ahora mismo."

    parsed = parse_grade_command(text, tabs)
    if not parsed:
        return (
            f"No he entendido bien la nota. Dime por ejemplo:\n"
            f"*Lucía Martínez, cálculo 22 mayo, 7*\n\n"
            f"Las pestañas disponibles son: {', '.join(tabs)}"
        )

    # Buscar en todas las pestañas
    cell = find_cell_all_tabs(parsed['alumno'], parsed['prueba'])

    if not cell:
        # Buscar solo el alumno para ver si existe
        cell_alumno = find_cell_all_tabs(parsed['alumno'], tabs[0] if tabs else 'DATOS')
        alumno_existe = cell_alumno is not None

        if alumno_existe:
            # El alumno existe pero la columna no — ofrecer crearla
            pending_new_col[chat_id] = {
                'alumno': parsed['alumno'],
                'prueba': parsed['prueba'],
                'nota': parsed['nota'],
                'tab': cell_alumno['tab'] if cell_alumno else tabs[0]
            }
            return (
                f"👤 Alumno encontrado en *{cell_alumno['tab'] if cell_alumno else tabs[0]}*\n"
                f"📝 Pero la columna *{parsed['prueba']}* no existe.\n\n"
                f"¿Quieres que la cree? Responde *sí* o *no*"
            )
        else:
            return (
                f"He entendido:\n"
                f"👤 Alumno: *{parsed['alumno']}*\n"
                f"📝 Prueba: *{parsed['prueba']}*\n"
                f"🔢 Nota: *{parsed['nota']}*\n\n"
                f"No encuentro a *{parsed['alumno']}* en la hoja. "
                f"¿Está bien escrito el nombre?"
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
        f"👤 *{cell['student_found']}*\n"
        f"📝 *{cell['test_found']}*\n"
        f"🗂 Pestaña: *{cell['tab']}*\n"
        f"🔢 Nota: *{parsed['nota']}*\n\n"
        f"¿Lo guardo? *sí* o *no*"
    )


async def handle_batch(text: str, chat_id: int) -> str:
    result = parse_batch_grades(text)
    if not result:
        return "No he entendido el formato. Dime así:\n*Cálculo 26 mayo. Alicia 5,5; Sofía 7; Rodrigo 9*"

    prueba, tab, grades = result
    tabs = list_tabs()
    if tabs and tab not in tabs:
        tab = tabs[0]

    resumen = f"📋 Voy a guardar estas notas en *{tab}*:\n📝 Prueba: *{prueba}*\n\n"
    for g in grades:
        resumen += f"• {g['student']}: *{g['grade']}*\n"
    resumen += f"\n¿Lo guardo todo? *sí* o *no*"

    pending_batch[chat_id] = {'tab': tab, 'prueba': prueba, 'grades': grades}
    return resumen


async def confirm_grade(chat_id: int) -> str:
    pending = pending_grades.get(chat_id)
    if not pending:
        return "No hay ninguna nota pendiente."
    success = write_grade(pending['tab'], pending['row'], pending['col'], pending['nota'])
    del pending_grades[chat_id]
    if success:
        return f"✅ Guardado: *{pending['alumno']}* → {pending['prueba']} → *{pending['nota']}*"
    return "❌ Error escribiendo en la hoja."


async def confirm_batch(chat_id: int) -> str:
    pending = pending_batch.get(chat_id)
    if not pending:
        return "No hay notas pendientes."
    ok, fallos = write_grades_batch(pending['tab'], pending['grades'])
    del pending_batch[chat_id]
    msg = f"✅ Guardadas {ok} notas en *{pending['tab']}*."
    if fallos:
        msg += f"\n⚠️ {fallos} no encontradas — revisa nombres."
    return msg


async def create_col_and_continue(chat_id: int) -> str:
    pending = pending_new_col.get(chat_id)
    if not pending:
        return "No hay nada pendiente."
    col = create_test_column(pending['tab'], pending['prueba'])
    del pending_new_col[chat_id]
    if not col:
        return "❌ Error creando la columna."

    # Ahora buscar la celda y guardar la nota
    cell = find_cell_all_tabs(pending['alumno'], pending['prueba'])
    if not cell:
        return f"✅ Columna *{pending['prueba']}* creada. Ahora dime la nota de nuevo."

    success = write_grade(cell['tab'], cell['row'], col, pending['nota'])
    if success:
        return f"✅ Columna creada y nota guardada:\n*{cell['student_found']}* → {pending['prueba']} → *{pending['nota']}*"
    return f"✅ Columna *{pending['prueba']}* creada pero error guardando la nota."


def cancel_grade(chat_id: int) -> str:
    if chat_id in pending_grades:
        del pending_grades[chat_id]
    return "❌ Cancelado."
