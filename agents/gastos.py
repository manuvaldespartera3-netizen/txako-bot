"""
Agente Gastos.
Usa requests directamente para escribir en Supabase, sin librería cliente.
"""
import json, logging, os, re
import requests
import gemini

logger = logging.getLogger(__name__)

CATEGORIAS = ['supermercado','restaurante','transporte','gasolina','salud','farmacia',
              'cuidado personal','ropa','hogar','ocio','deporte','extras','cervezas',
              'educación','suscripciones','regalo','viaje','otros']

pending_expenses: dict[int, dict] = {}

def save_to_supabase(data: dict) -> bool:
    """Escribe directamente en Supabase via REST API sin librería cliente."""
    url = os.environ.get('FAMILIA_SUPABASE_URL', '')
    key = os.environ.get('FAMILIA_SUPABASE_KEY', '')
    if not url or not key:
        logger.error("Faltan variables FAMILIA_SUPABASE_URL o FAMILIA_SUPABASE_KEY")
        return False
    try:
        response = requests.post(
            f"{url}/rest/v1/gastos",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal"
            },
            json=data,
            timeout=10
        )
        if response.status_code in [200, 201]:
            return True
        logger.error(f"Supabase error {response.status_code}: {response.text}")
        return False
    except Exception as e:
        logger.error(f"Error guardando en Supabase: {e}")
        return False

async def parse_expense(text: str) -> dict:
    prompt = f"""Extrae la información de este gasto.
Texto: "{text}"
Categorías: {', '.join(CATEGORIAS)}
Responde SOLO con JSON sin markdown:
{{"concepto": "descripción o null", "cantidad": numero_o_null, "quien": "Manuel" o "Merche" o null, "categoria": "categoria o null"}}
- mío/yo/manuel → "Manuel", merche/ella → "Merche", si no se menciona → null
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

    # Cancelar
    if text_lower in ['no','cancelar','cancel','❌','nada']:
        del pending_expenses[chat_id]
        return "❌ Gasto cancelado."

    # Confirmar y guardar
    if text_lower in ['sí','si','yes','ok','correcto','✅','guardar','dale']:
        if not get_missing_fields(expense):
            return await save_expense(chat_id, expense)

    # En modo resumen — corrección por número de campo
    if not get_missing_fields(expense):
        import re as _re
        # Formato "N texto" donde N es el número del campo
        m = _re.match(r'^([1-5])\s+(.+)$', text.strip())
        if m:
            campo = int(m.group(1))
            valor = m.group(2).strip()
            if campo == 1:
                expense['concepto'] = valor
            elif campo == 2:
                num = _re.search(r'[\d.,]+', valor)
                if num:
                    expense['cantidad'] = float(num.group().replace(',','.'))
            elif campo == 3:
                matched = next((c for c in CATEGORIAS if c in valor.lower()), valor.lower())
                expense['categoria'] = matched
            elif campo == 4:
                if any(k in valor.lower() for k in ['manuel','mío','mio','yo','mi']):
                    expense['quien'] = 'Manuel'
                else:
                    expense['quien'] = 'Merche'
            elif campo == 5:
                expense['notas'] = valor
            pending_expenses[chat_id] = expense
            return build_summary(expense)
        return build_summary(expense)

    # Rellenar campos que faltan
    missing = get_missing_fields(expense)
    field = missing[0]
    if field == 'quien':
        if any(k in text_lower for k in ['mío','mio','yo','manuel','para mí','mi']):
            expense['quien'] = 'Manuel'
        elif any(k in text_lower for k in ['merche','ella']):
            expense['quien'] = 'Merche'
        else:
            return "¿Es de Manuel o de Merche?"
    elif field == 'cantidad':
        m = re.search(r'\d+[.,]?\d*', text.replace(',','.'))
        if not m:
            return "¿Cuánto fue? Escríbelo en números, ej: 4.50"
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
            return "No reconocí la categoría. Elige una:\n" + '\n'.join([f"• {c}" for c in CATEGORIAS])
    pending_expenses[chat_id] = expense
    return await ask_missing(chat_id)

async def ask_missing(chat_id: int) -> str:
    expense = pending_expenses[chat_id]
    missing = get_missing_fields(expense)
    if not missing:
        return build_summary(expense)
    field = missing[0]
    if field == 'cantidad': return "¿Cuánto fue el gasto?"
    if field == 'concepto': return "¿En qué consistió?"
    if field == 'categoria': return "¿Qué categoría?\n" + '\n'.join([f"• {c}" for c in CATEGORIAS])
    if field == 'quien': return "¿Es de Manuel o de Merche?"

def build_summary(expense: dict) -> str:
    notas = expense.get('notas', '') or '—'
    return (f"Resumen — confirma o corrige:\n\n"
            f"1. Concepto: {expense['concepto']}\n"
            f"2. Importe: {expense['cantidad']} euros\n"
            f"3. Categoria: {expense['categoria']}\n"
            f"4. Quien: {expense['quien']}\n"
            f"5. Notas: {notas}\n\n"
            f"Para corregir di: \'1 pan y leche\' o \'5 huevos y pescado\'\n"
            f"Para guardar di: si")

async def save_expense(chat_id: int, expense: dict) -> str:
    del pending_expenses[chat_id]
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    success = save_to_supabase({
        'concepto': expense['concepto'],
        'cantidad': expense['cantidad'],
        'quien': expense['quien'],
        'categoria': expense['categoria'],
        'fecha': today,
        'notas': expense.get('notas', ''),
    })
    if success:
        return f"Guardado: {expense['concepto']} — {expense['cantidad']} euros · {expense['categoria']} · {expense['quien']}. Ya aparece en la app."
    return "Error guardando. Comprueba las variables FAMILIA_SUPABASE_URL y FAMILIA_SUPABASE_KEY en Railway."

def get_missing_fields(expense: dict) -> list:
    return [f for f in ['cantidad','concepto','categoria','quien'] if not expense.get(f)]
