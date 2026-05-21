"""Agente Gastos."""
import json, logging, os, re
import gemini

logger = logging.getLogger(__name__)

CATEGORIAS = ['supermercado','restaurante','transporte','gasolina','salud','farmacia',
              'cuidado personal','ropa','hogar','ocio','deporte','extras','cervezas',
              'educación','suscripciones','regalo','viaje','otros']

pending_expenses: dict[int, dict] = {}

def get_familia_db():
    from supabase import create_client
    url = os.environ.get('FAMILIA_SUPABASE_URL','')
    key = os.environ.get('FAMILIA_SUPABASE_KEY','')
    if not url or not key:
        return None
    return create_client(url, key)

async def parse_expense(text: str) -> dict:
    prompt = f"""Extrae la información de este gasto.
Texto: "{text}"
Categorías: {', '.join(CATEGORIAS)}
Responde SOLO con JSON sin markdown:
{{"concepto": "descripción o null", "cantidad": numero_o_null, "quien": "Txako" o "Merche" o null, "categoria": "categoria o null"}}
- mío/yo/txako → "Txako", merche/ella → "Merche", si no se menciona → null
- cantidad siempre número decimal"""
    try:
        raw = gemini.ask(prompt).strip().replace('```json','').replace('```','').strip()
        return json.loads(raw)
    except:
        return {'concepto':None,'cantidad':None,'quien':None,'categoria':None}

async def handle(text: str, chat_id: int) -> str:
    if chat_id in pending_expenses:
        return await handle_pending(text, text.lower().strip(), chat_id)
    parsed = await parse_expense(text)
    pending_expenses[chat_id] = parsed
    return await ask_missing(chat_id)

async def handle_pending(text: str, text_lower: str, chat_id: int) -> str:
    expense = pending_expenses[chat_id]
    if text_lower in ['no','cancelar','cancel','❌','nada']:
        del pending_expenses[chat_id]
        return "❌ Gasto cancelado."
    if text_lower in ['sí','si','yes','ok','correcto','✅','guardar','dale']:
        if not get_missing_fields(expense):
            return await save_expense(chat_id, expense)
    missing = get_missing_fields(expense)
    if not missing:
        return build_summary(expense)
    field = missing[0]
    if field == 'quien':
        if any(k in text_lower for k in ['mío','mio','yo','txako','para mí','mi']):
            expense['quien'] = 'Txako'
        elif any(k in text_lower for k in ['merche','ella']):
            expense['quien'] = 'Merche'
        else:
            return "¿Es de *Txako* o de *Merche*?"
    elif field == 'cantidad':
        m = re.search(r'\d+[.,]?\d*', text.replace(',','.'))
        if not m:
            return "¿Cuánto fue? Escríbelo en números, ej: *4.50*"
        expense['cantidad'] = float(m.group().replace(',','.'))
    elif field == 'concepto':
        expense['concepto'] = text.strip()
    elif field == 'categoria':
        matched = next((c for c in CATEGORIAS if c in text_lower), None)
        if not matched:
            aliases = {'mercadona':'supermercado','lidl':'supermercado','bar':'restaurante',
                      'bus':'transporte','médico':'salud','cerveza':'cervezas','cine':'ocio'}
            matched = next((v for k,v in aliases.items() if k in text_lower), None)
        if matched:
            expense['categoria'] = matched
        else:
            return f"No reconocí la categoría. Elige una:\n" + '\n'.join([f"• {c}" for c in CATEGORIAS])
    pending_expenses[chat_id] = expense
    return await ask_missing(chat_id)

async def ask_missing(chat_id: int) -> str:
    expense = pending_expenses[chat_id]
    missing = get_missing_fields(expense)
    if not missing:
        return build_summary(expense)
    field = missing[0]
    if field == 'cantidad': return "💶 ¿Cuánto fue el gasto?"
    if field == 'concepto': return "📝 ¿En qué consistió?"
    if field == 'categoria': return "🏷️ ¿Qué categoría?\n" + '\n'.join([f"• {c}" for c in CATEGORIAS])
    if field == 'quien': return "👤 ¿Es de *Txako* o de *Merche*?"

def build_summary(expense: dict) -> str:
    return (f"💰 *Resumen:*\n\n• Concepto: *{expense['concepto']}*\n"
            f"• Importe: *{expense['cantidad']}€*\n• Categoría: *{expense['categoria']}*\n"
            f"• Quién: *{expense['quien']}*\n\n¿Lo guardo? (*sí* / *no*)")

async def save_expense(chat_id: int, expense: dict) -> str:
    del pending_expenses[chat_id]
    db = get_familia_db()
    if not db:
        return "⚠️ Sin conexión a la app de familia."
    try:
        db.table('gastos').insert({
            'concepto': expense['concepto'], 'cantidad': expense['cantidad'],
            'quien': expense['quien'], 'categoria': expense['categoria'],
        }).execute()
        return f"✅ *Guardado*\n*{expense['concepto']}* — {expense['cantidad']}€\n{expense['categoria']} · {expense['quien']}\n\nYa aparece en la app."
    except Exception as e:
        return f"❌ Error: {str(e)}"

def get_missing_fields(expense: dict) -> list:
    return [f for f in ['cantidad','concepto','categoria','quien'] if not expense.get(f)]
