"""
Agente Gastos.
Parsea gastos en lenguaje natural, valida todos los campos
y escribe directamente en el Supabase de la familiaapp.
"""
import json, logging, os
import google.generativeai as genai

logger = logging.getLogger(__name__)
model = genai.GenerativeModel('gemini-1.5-flash-latest')

CATEGORIAS = [
    'supermercado', 'restaurante', 'transporte', 'gasolina',
    'salud', 'farmacia', 'cuidado personal', 'ropa', 'hogar',
    'ocio', 'deporte', 'extras', 'cervezas', 'educación',
    'suscripciones', 'regalo', 'viaje', 'otros'
]

pending_expenses: dict[int, dict] = {}

def get_familia_db():
    """Crea cliente Supabase de familiaapp bajo demanda."""
    from supabase import create_client
    url = os.environ.get('FAMILIA_SUPABASE_URL', '')
    key = os.environ.get('FAMILIA_SUPABASE_KEY', '')
    if not url or not key:
        return None
    return create_client(url, key)

async def parse_expense(text: str) -> dict:
    prompt = f"""Extrae la información de este gasto personal.
Texto: "{text}"
Categorías posibles: {', '.join(CATEGORIAS)}

Responde SOLO con JSON sin markdown:
{{
  "concepto": "descripción corta del gasto o null",
  "cantidad": numero_decimal_o_null,
  "quien": "Txako" o "Merche" o null,
  "categoria": "categoría de la lista o null"
}}

Reglas:
- "mío", "yo", "txako", "para mí" → quien = "Txako"
- "merche", "ella" → quien = "Merche"
- Si no se menciona quién → null
- cantidad siempre número (4.5, no "cuatro cincuenta")
- Si no hay info suficiente para un campo → null
"""
    try:
        response = model.generate_content(prompt)
        raw = response.text.strip().replace('```json','').replace('```','').strip()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Error parseando gasto: {e}")
        return {'concepto': None, 'cantidad': None, 'quien': None, 'categoria': None}

async def handle(text: str, chat_id: int) -> str:
    text_lower = text.lower().strip()

    if chat_id in pending_expenses:
        return await handle_pending(text, text_lower, chat_id)

    parsed = await parse_expense(text)
    pending_expenses[chat_id] = parsed
    return await ask_missing(chat_id)

async def handle_pending(text: str, text_lower: str, chat_id: int) -> str:
    expense = pending_expenses[chat_id]

    if text_lower in ['no', 'cancelar', 'cancel', '❌', 'nada']:
        del pending_expenses[chat_id]
        return "❌ Gasto cancelado. No se guardó nada."

    if text_lower in ['sí', 'si', 'yes', 'ok', 'correcto', '✅', 'guardar', 'dale']:
        if all_fields_filled(expense):
            return await save_expense(chat_id, expense)
        return await ask_missing(chat_id)

    missing = get_missing_fields(expense)
    if not missing:
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
        cantidad = extract_number(text)
        if cantidad is None:
            return "No entendí el importe. Dímelo en números, por ejemplo: *4.50*"
        expense['cantidad'] = cantidad

    elif next_field == 'concepto':
        if len(text.strip()) < 2:
            return "¿En qué consistió el gasto? (Ej: *pan y leche*, *gasolina*)"
        expense['concepto'] = text.strip()

    elif next_field == 'categoria':
        matched = match_categoria(text_lower)
        if matched:
            expense['categoria'] = matched
        else:
            cats = ', '.join(CATEGORIAS[:8]) + '...'
            return f"No reconocí esa categoría. Elige una:\n_{cats}_\n\nO escríbela tú."

    pending_expenses[chat_id] = expense
    return await ask_missing(chat_id)

async def ask_missing(chat_id: int) -> str:
    expense = pending_expenses[chat_id]
    missing = get_missing_fields(expense)

    if not missing:
        return build_summary(expense)

    next_field = missing[0]
    if next_field == 'cantidad':
        return "💶 ¿Cuánto fue el gasto?"
    elif next_field == 'concepto':
        return "📝 ¿En qué consistió? (Ej: *gasolina*, *pan y leche*)"
    elif next_field == 'categoria':
        cats = '\n'.join([f"• {c}" for c in CATEGORIAS])
        return f"🏷️ ¿Qué categoría?\n\n{cats}"
    elif next_field == 'quien':
        return "👤 ¿Es gasto de *Txako* o de *Merche*?"

def build_summary(expense: dict) -> str:
    return (
        f"💰 *Resumen del gasto:*\n\n"
        f"• Concepto: *{expense['concepto']}*\n"
        f"• Importe: *{expense['cantidad']}€*\n"
        f"• Categoría: *{expense['categoria']}*\n"
        f"• Quién: *{expense['quien']}*\n\n"
        f"¿Lo guardo? (*sí* / *no*)"
    )

async def save_expense(chat_id: int, expense: dict) -> str:
    del pending_expenses[chat_id]
    db = get_familia_db()
    if not db:
        return "⚠️ No está configurada la conexión con la familiaapp.\nComprueba FAMILIA_SUPABASE_URL y FAMILIA_SUPABASE_KEY en Railway."
    try:
        db.table('gastos').insert({
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

def get_missing_fields(expense: dict) -> list[str]:
    order = ['cantidad', 'concepto', 'categoria', 'quien']
    return [f for f in order if not expense.get(f)]

def all_fields_filled(expense: dict) -> bool:
    return not get_missing_fields(expense)

def extract_number(text: str) -> float | None:
    import re
    text = text.replace(',', '.').replace('€', '').replace('euros', '').strip()
    match = re.search(r'\d+\.?\d*', text)
    if match:
        return float(match.group())
    return None

def match_categoria(text: str) -> str | None:
    for cat in CATEGORIAS:
        if cat in text or text in cat:
            return cat
    aliases = {
        'mercadona': 'supermercado', 'lidl': 'supermercado', 'carrefour': 'supermercado',
        'bar': 'restaurante', 'cafetería': 'restaurante', 'cafeteria': 'restaurante',
        'bus': 'transporte', 'tren': 'transporte', 'taxi': 'transporte',
        'médico': 'salud', 'medico': 'salud', 'dentista': 'salud',
        'peluquería': 'cuidado personal', 'peluqueria': 'cuidado personal',
        'cerveza': 'cervezas', 'copa': 'ocio', 'cine': 'ocio',
    }
    for alias, cat in aliases.items():
        if alias in text:
            return cat
    return None
