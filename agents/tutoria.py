"""Agente Tutoría."""
import logging, re
import gemini as gemini_module
from integrations.sheets import (
    list_tabs, parse_grade_command, parse_batch_grades,
    find_cell, find_student_in_tab, write_grade, write_grades_batch,
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
    """
    Detecta batch cuando hay múltiples fragmentos nombre+número.
    Funciona con puntos (Whisper), punto y coma, o dos puntos.
    """
    # Separar por punto, punto y coma, dos puntos
    fragmentos = [f.strip() for f in re.split(r'[.;:\n]', text) if f.strip()]
    if len(fragmentos) < 3:
        return False
    # Contar fragmentos que terminan en número (son pares nombre+nota)
    pares = 0
    for frag in fragmentos:
        tokens = frag.split()
        if tokens:
            ultimo = tokens[-1].replace(',', '.')
            try:
                float(ultimo)
                pares += 1
            except Exception:
                pass
    # Si hay 2 o más pares nombre+nota, es un batch
    return pares >= 2

async def handle(text: str, chat_id: int, is_voice: bool = False) -> str:
    text_lower = text.lower().strip()

    # ── Confirmación nota individual ──────────────────────
    if chat_id in pending_grades:
        if text_lower in ['si', 'sí', 'yes', 'confirmar', 'ok', 'correcto', 'vale']:
            return await confirm_grade(chat_id)
        elif text_lower in ['no', 'cancelar', 'cancel']:
            return cancel_grade(chat_id)

    # ── Confirmación batch ────────────────────────────────
    if chat_id in pending_batch:
        if text_lower in ['si', 'sí', 'yes', 'confirmar', 'ok', 'correcto', 'vale']:
            return await confirm_batch(chat_id)
        elif text_lower in ['no', 'cancelar', 'cancel']:
            del pending_batch[chat_id]
            return "❌ Cancelado."

    # ── Confirmación crear columna nueva ──────────────────
    if chat_id in pending_new_col:
        if text_lower in ['si', 'sí', 'yes', 'ok', 'vale', 'crear', 'crea']:
            return await create_col_and_continue(chat_id)
        elif text_lower in ['no', 'cancelar', 'cancel']:
            del pending_new_col[chat_id]
            return "❌ Cancelado."

    # ── Informe para familia ──────────────────────────────
    if 'informe' in text_lower or 'familia' in text_lower:
        prompt = SYSTEM + f"\n\nGenera un informe de tutoría profesional y cercano para la familia. Máximo 200 palabras.\n\nTxako dice: {text}"
        return gemini_module.ask(prompt)

    # ── Batch: varios alumnos ─────────────────────────────
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
            f"Pestañas disponibles:\n"
            + "\n".join([f"{i+1}. {t}" for i, t in enumerate(tabs)])
        )

    cell = find_cell(parsed['pestana'], parsed['alumno'], parsed['prueba'])

    if not cell:
        alumno_info = find_student_in_tab(parsed['pestana'], parsed['alumno'])
        if alumno_info:
            pending_new_col[chat_id] = {
                'alumno': parsed['alumno'],
                'prueba': parsed['prueba'],
                'nota': parsed['nota'],
                'tab': parsed['pestana'],
                'row': alumno_info['row'],
                'student_found': alumno_info['student_found']
            }
            return (
                f"👤 Alumno: *{alumno_info['student_found']}*\n"
                f"🗂 Pestaña: *{parsed['pestana']}*\n"
                f"📝 La columna *{parsed['prueba']}* no existe todavía.\n\n"
                f"¿La creo? *sí* o *no*\n\n"
                f"_(Pestañas: "
                + ", ".join([f"{i+1}={t}" for i, t in enumerate(tabs)])
                + ")_"
            )
        else:
            return (
                f"No encuentro a *{parsed['alumno']}* en la pestaña *{parsed['pestana']}*.\n\n"
                f"Pestañas disponibles:\n"
                + "\n".join([f"{i+1}. {t}" for i, t in enumerate(tabs)])
                + f"\n\nSi está en otra pestaña añade el número al inicio:\n"
                f"*2 {parsed['alumno']}, {parsed['prueba']}, {parsed['nota']}*"
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
    tabs = list_tabs()
    if not tabs:
        return "❌ No puedo conectar con Google Sheets ahora mismo."

    result = parse_batch_grades(text, tabs)
    if not result:
        return (
            "No he entendido el formato. Habla así:\n"
            "*Cálculo 26 mayo. Alicia 5,5. Sofía 7. Rodrigo 9*"
        )

    prueba, tab, grades = result

    from integrations.sheets import get_spreadsheet, find_test_col
    try:
        sh = get_spreadsheet()
        ws = sh.worksheet(tab)
        headers = ws.row_values(1)
        col_idx, col_found = find_test_col(headers, prueba)
    except Exception:
        col_idx = None
        col_found = None

    resumen = f"📋 *{prueba}* en pestaña *{tab}*\n\n"
    for g in grades:
        resumen += f"• {g['student']}: *{g['grade']}*\n"

    if col_idx is None:
        resumen += f"\n⚠️ La columna *{prueba}* no existe. Se creará."

    resumen += f"\n\n¿Lo guardo? *sí* o *no*\n"
    resumen += "_(Pestañas: " + ", ".join([f"{i+1}={t}" for i, t in enumerate(tabs)]) + ")_"

    pending_batch[chat_id] = {
        'tab': tab,
        'prueba': prueba,
        'grades': grades,
        'col_idx': col_idx
    }
    return resumen


async def confirm_grade(chat_id: int) -> str:
    pending = pending_grades.get(chat_id)
    if not pending:
        return "No hay ninguna nota pendiente."
    success = write_grade(pending['tab'], pending['row'], pending['col'], pending['nota'])
    del pending_grades[chat_id]
    if success:
        return f"✅ *{pending['alumno']}* → {pending['prueba']} → *{pending['nota']}*"
    return "❌ Error escribiendo en la hoja."


async def confirm_batch(chat_id: int) -> str:
    pending = pending_batch.get(chat_id)
    if not pending:
        return "No hay notas pendientes."

    tab = pending['tab']
    prueba = pending['prueba']
    grades = pending['grades']
    col_idx = pending.get('col_idx')

    if col_idx is None:
        col_idx = create_test_column(tab, prueba)
        if not col_idx:
            del pending_batch[chat_id]
            return "❌ Error creando la columna."
    else:
        col_idx = col_idx + 1

    ok, fallos, no_encontrados = write_grades_batch(tab, col_idx, grades)
    del pending_batch[chat_id]

    msg = f"✅ {ok} notas guardadas en *{tab}* → *{prueba}*"
    if fallos:
        msg += f"\n⚠️ No encontrados: {', '.join(no_encontrados)}"
    return msg


async def create_col_and_continue(chat_id: int) -> str:
    pending = pending_new_col.get(chat_id)
    if not pending:
        return "No hay nada pendiente."
    col = create_test_column(pending['tab'], pending['prueba'])
    del pending_new_col[chat_id]
    if not col:
        return "❌ Error creando la columna."
    success = write_grade(pending['tab'], pending['row'], col, pending['nota'])
    if success:
        return (
            f"✅ Columna *{pending['prueba']}* creada y nota guardada:\n"
            f"*{pending['student_found']}* → {pending['prueba']} → *{pending['nota']}*"
        )
    return f"✅ Columna *{pending['prueba']}* creada pero error guardando la nota."


def cancel_grade(chat_id: int) -> str:
    if chat_id in pending_grades:
        del pending_grades[chat_id]
    return "❌ Cancelado."
