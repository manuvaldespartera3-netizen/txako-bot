"""
Agente Gastos.
Parsea gastos en lenguaje natural, valida todos los campos
y escribe directamente en el Supabase de la familiaapp.

Tabla gastos: concepto, cantidad, quien, categoria, created_at
"""
import json, logging
import google.generativeai as genai
from supabase import create_client, Client
import config

logger = logging.getLogger(__name__)
model = genai.GenerativeModel('gemini-2.0-flash-exp')

# ─── CLIENTE SUPABASE DE LA FAMILIAAPP ───────────────────
# OJO: es un proyecto Supabase DISTINTO al del bot
import os
_familia_url = os.environ.get('FAMILIA_SUPABASE_URL')
_familia_key = os.environ.get('FAMILIA_SUPABASE_KEY')
familia_db: Client | None = None
if _familia_url and _familia_key:
    familia_db = create_client(_familia_url, _familia_key)

# ─── CATEGORÍAS VÁLIDAS ───────────────────────────────────
CATEGORIAS = [
    'supermercado', 'restaurante', 'transporte', 'gasolina',
    'salud', 'farmacia', 'cuidado personal', 'ropa', 'hogar',
    'ocio', 'deporte', 'extras', 'cervezas', 'educación',
    'suscripciones', 'regalo', 'viaje', 'otros'
]

# ─── ESTADO TEMPORAL POR CHAT ─────────────────────────────
# Guarda el gasto en construcción hasta que estén todos los campos
pending_expenses: dict[int, dict] = {}

# ─── PARSER CON IA ────────────────────────────────────────

async def parse_expense(text: str) -> dict:
    """
    Extrae campos del gasto. Los que no encuentre los deja como None.
    """
    prompt = f"""Extrae la información de este gasto personal.
Texto: "{text}"

Categorías posibles: {', '.join(CATEGORIAS)}

Responde SOLO con JSON sin markdown:
{{
  "concepto": "descripción corta del gasto o null",
  "cantidad": número_decimal_o_null,
  "quien": "Txako" o "Merche" o null,
  "categoria": "categoría de la lista o null"
}}

Reglas:
- "mío", "yo", "para mí", "txako" → quien = "Txako"
- "merche", "ella", "su" → quien = "Merche"
- Si no se menciona quién, quien = null
- La cantidad siempre es un número (4.5, no "cuatro cincuenta")
- Si no hay suficiente info para un campo, ponlo como null
"""
    try:
        response = model.generate_content(prompt)
        raw = response.text.strip().replace('```json','').replace('```','').strip()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Error parseando gasto: {e}")
        return {'concepto': None, 'cantidad': None, 'quien': None, 'categoria': None}

# ─── HANDLER PRINCIPAL ────────────────────────────────────

async def handle(text: str, chat_id: int) -> str:
    """
    Punto de entrada. Gestiona el flujo completo:
    parsear → preguntar lo que falta → confirmar → guardar.
    """
    text_lower = text.lower().strip()

    # ── ¿Hay un gasto pendiente de completar? ─────────────
    if chat_id in pending_expenses:
        return await handle_pending(text, text_lower, chat_id)

    # ── Nuevo gasto ───────────────────────────────────────
    parsed = await parse_expense(text)
    pending_expenses[chat_id] = parsed
    return await ask_missing(chat_id)


async def handle_pending(text: str, text_lower: str, chat_id: int) -> str:
    """Completa los campos que faltan o procesa la confirmación final."""
    expense = pending_expenses[chat_id]

    # ── Cancelar ──────────────────────────────────────────
    if text_lower in ['no', 'cancelar', 'cancel', '❌', 'nada']:
        del pending_expenses[chat_id]
        return "❌ Gasto cancelado. No se guardó nada."

    # ── Confirmación final ────────────────────────────────
    if text_lower in ['sí', 'si', 'yes', 'ok', 'correcto', '✅', 'guardar', 'dale']:
        if all_fields_filled(expense):
            return await save_expense(chat_id, expense)
        # Si llegamos aquí con campos vacíos, seguir preguntando
        return await ask_missing(chat_id)

    # ── Rellenar campo que falta ──────────────────────────
    # Intentar encajar la respuesta con el campo que falta
    missing = get_missing_fields(expense)

    if not missing:
        # Todo relleno, mostrar resumen
        return build_summary(expense)

    next_field = missing[0]

    if next_field == 'quien':
        if any(k in text_lower for k in ['mío', 'mio', 'yo', 'txako', 'para mí', 'para mi', 'mi']):
            expense['quien'] = 'Txako'
        elif any(k in text_lower for k in ['merche', 'ella', 'suya', 'su']):
            expense['quien'] = 'Merche'
        else:
            return "No entendí. ¿Es de *Txako* o de *Merche*?"

    elif next_field == 'cantidad':
        # Intentar extraer número del texto
        cantidad = extract_number(text)
        if cantidad is None:
            return "No entendí el importe. Dímelo en números, por ejemplo: *4.50*"
        expense['cantidad'] = cantidad

    elif next_field == 'concepto':
        if len(text.strip()) < 2:
            return "¿En qué consistió el gasto? (Ej: *pan y leche*, *gasolina*, *cena con Merche*)"
        expense['concepto'] = text.strip()

    elif next_field == 'categoria':
        # Intentar matchear con categorías conocidas
        matched = match_categoria(text_lower)
        if matched:
            expense['categoria'] = matched
        else:
            cats = ', '.join(CATEGORIAS[:8]) + '...'
            return f"No reconocí esa categoría. Elige una:\n_{cats}_\n\nO escríbela tú."

    pending_expenses[chat_id] = expense
    return await ask_missing(chat_id)


async def ask_missing(chat_id: int) -> str:
    """Pregunta el siguiente campo que falta, o muestra resumen si están todos."""
    expense = pending_expenses[chat_id]
    missing = get_missing_fields(expense)

    if not missing:
        return build_summary(expense)

    next_field = missing[0]

    if next_field == 'cantidad':
        return "💶 ¿Cuánto fue el gasto?"

    elif next_field == 'concepto':
        return "📝 ¿En qué consistió? (Ej: *gasolina*, *cena*, *pan y leche*)"

    elif next_field == 'categoria':
        cats = '\n'.join([f"• {c}" for c in CATEGORIAS])
        return f"🏷️ ¿Qué categoría?\n\n{cats}"

    elif next_field == 'quien':
        return "👤 ¿Es gasto de *Txako* o de *Merche*?"


def build_summary(expense: dict) -> str:
    """Muestra resumen del gasto para confirmación final."""
    return (
        f"💰 *Resumen del gasto:*\n\n"
        f"• Concepto: *{expense['concepto']}*\n"
        f"• Importe: *{expense['cantidad']}€*\n"
        f"• Categoría: *{expense['categoria']}*\n"
        f"• Quién: *{expense['quien']}*\n\n"
        f"¿Lo guardo? (*sí* / *no*)"
    )

# ─── GUARDAR EN SUPABASE ──────────────────────────────────

async def save_expense(chat_id: int, expense: dict) -> str:
    """Escribe el gasto en la tabla gastos de la familiaapp."""
    del pending_expenses[chat_id]

    if not familia_db:
        return (
            "⚠️ No está configurada la conexión con la familiaapp.\n"
            "Añade *FAMILIA_SUPABASE_URL* y *FAMILIA_SUPABASE_KEY* en Railway."
        )

    try:
        familia_db.table('gastos').insert({
            'concepto': expense['concepto'],
            'cantidad': expense['cantidad'],
            'quien': expense['quien'],
            'categoria': expense['categoria'],
        }).execute()

        return (
            f"✅ *Gasto guardado*\n\n"
            f"*{expense['concepto']}* — {expense['cantidad']}€\n"
            f"{expense['categoria']} · {expense['quien']}\n\n"
            f"Ya aparece en la app."
        )
    except Exception as e:
        logger.error(f"Error guardando gasto: {e}")
        return f"❌ Error guardando en la app: {str(e)}"

# ─── UTILIDADES ───────────────────────────────────────────

def get_missing_fields(expense: dict) -> list[str]:
    """Devuelve lista de campos que faltan, en orden de prioridad."""
    order = ['cantidad', 'concepto', 'categoria', 'quien']
    return [f for f in order if not expense.get(f)]

def all_fields_filled(expense: dict) -> bool:
    return not get_missing_fields(expense)

def extract_number(text: str) -> float | None:
    """Extrae un número de un texto, incluyendo comas decimales."""
    import re
    text = text.replace(',', '.').replace('€', '').replace('euros', '').strip()
    match = re.search(r'\d+\.?\d*', text)
    if match:
        return float(match.group())
    return None

def match_categoria(text: str) -> str | None:
    """Busca la categoría más cercana en el texto."""
    for cat in CATEGORIAS:
        if cat in text or text in cat:
            return cat
    # Alias comunes
    aliases = {
        'mercadona': 'supermercado', 'lidl': 'supermercado', 'carrefour': 'supermercado',
        'bar': 'restaurante', 'cafetería': 'restaurante', 'cafeteria': 'restaurante',
        'bus': 'transporte', 'tren': 'transporte', 'taxi': 'transporte', 'uber': 'transporte',
        'médico': 'salud', 'medico': 'salud', 'dentista': 'salud',
        'peluquería': 'cuidado personal', 'peluqueria': 'cuidado personal',
        'cerveza': 'cervezas', 'copa': 'ocio', 'cine': 'ocio',
    }
    for alias, cat in aliases.items():
        if alias in text:
            return cat
    return None
