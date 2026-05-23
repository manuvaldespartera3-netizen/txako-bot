"""
Agente Gastos v3.
Usa IA para extraer TODOS los campos de una vez, incluyendo notas.
Va directo al resumen si tiene todo, sin preguntar innecesariamente.
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
    url = os.environ.get('FAMILIA_SUPABASE_URL', '')
    key = os.environ.get('FAMILIA_SUPABASE_KEY', '')
    if not url or not key:
        return False
    # Reintentar hasta 3 veces si falla
    for intento in range(3):
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
            logger.error(f"Intento {intento+1} fallido: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Intento {intento+1} error: {e}")
    return False

async def parse_expense(text: str) -> dict:
    """Extrae TODOS los campos posibles del texto de una vez."""
    prompt = f"""Extrae la información de este gasto personal con todos los detalles.
Texto: "{text}"

Categorías disponibles: {', '.join(CATEGORIAS)}

Reglas importantes:
- "mío", "yo", "manuel", "para mí" → quien = "Manuel"
- "merche", "ella", "suya" → quien = "Merche"
- Si no se menciona quién → null
- cantidad siempre número decimal (60,10 → 60.1)
- Si menciona una tienda específica (Alcampo, Mercadona, etc.) úsala como concepto
- notas: cualquier detalle adicional de lo que se compró (huevos, pescado, etc.)
- Si no hay notas → null

Responde SOLO con JSON sin markdown:
{{
  "concepto": "nombre de la tienda o descripción corta",
  "cantidad": numero_decimal_o_null,
  "quien": "Manuel" o "Merche" o null,
  "categoria": "una de las categorías o null",
  "notas": "detalles adicionales o null"
}}"""
    try:
        raw = gemini.ask(prompt).strip().replace('```json','').replace('```','').strip()
        return json.loads(raw)
    except:
        return {'concepto':None,'cantidad':None,'quien':None,'categoria':None,'notas':None}

async def handle(text: str, chat_id: int) -> str:
    # Si hay un gasto pendiente, procesamos la respuesta
    if chat_id in pending_expenses:
        return await handle_pending(text, text.lower().strip(), chat_id)
    
    # Nuevo gasto — parsear todo de una vez
    parsed = await parse_expense(text)
    pending_expenses[chat_id] = parsed
    
    missing = get_missing_fields(parsed)
    if not missing:
        # Tenemos todo — ir directo al resumen
        return build_summary(parsed)
    else:
        return await ask_missing(chat_id)

async def handle_pending(text: str, text_lower: str, chat_id: int) -> str:
    expense = pending_expenses[chat_id]

    # Cancelar
    if text_lower in ['no','cancelar','cancel','nada']:
        del pending_expenses[chat_id]
        return "Gasto cancelado."

    # Confirmar
    if text_lower in ['sí','si','yes','ok','correcto','guardar','dale','venga']:
        if not get_missing_fields(expense):
            return await save_expense(chat_id, expense)

    # Corrección por número: "1 Alcampo", "5 huevos y pescado"
    m = re.match(r'^([1-5])\s+(.+)$', text.strip())
    if m:
        campo = int(m.group(1))
        valor = m.group(2).strip()
        if campo == 1:
            expense['concepto'] = valor
        elif campo == 2:
            num = re.search(r'[\d.,]+', valor)
            if num:
                expense['cantidad'] = float(num.group().replace(',','.'))
        elif campo == 3:
            matched = next((c for c in CATEGORIAS if c in valor.lower()), None)
            expense['categoria'] = matched or valor.lower()
        elif campo == 4:
            expense['quien'] = 'Manuel' if any(k in valor.lower() for k in ['manuel','mío','mio','yo']) else 'Merche'
        elif campo == 5:
            expense['notas'] = valor
        pending_expenses[chat_id] = expense
        return build_summary(expense)

    # Si tiene todos los campos, mostrar resumen
    if not get_missing_fields(expense):
        return build_summary(expense)

    # Rellenar campo que falta
    missing = get_missing_fields(expense)
    field = missing[0]
    if field == 'quien':
        if any(k in text_lower for k in ['mío','mio','yo','manuel','mi']):
            expense['quien'] = 'Manuel'
        elif any(k in text_lower for k in ['merche','ella']):
            expense['quien'] = 'Merche'
        else:
            return "Es de Manuel o de Merche?"
    elif field == 'cantidad':
        num = re.search(r'[\d.,]+', text.replace(',','.'))
        if not num:
            return "Cuanto fue? Escribe el numero, ej: 4.50"
        expense['cantidad'] = float(num.group().replace(',','.'))
    elif field == 'concepto':
        expense['concepto'] = text.strip()
    elif field == 'categoria':
        matched = next((c for c in CATEGORIAS if c in text_lower), None)
        expense['categoria'] = matched or text_lower.strip()

    pending_expenses[chat_id] = expense
    return await ask_missing(chat_id)

async def ask_missing(chat_id: int) -> str:
    expense = pending_expenses[chat_id]
    missing = get_missing_fields(expense)
    if not missing:
        return build_summary(expense)
    field = missing[0]
    if field == 'cantidad': return "Cuanto fue el gasto?"
    if field == 'concepto': return "En que consistio?"
    if field == 'categoria': return "Que categoria?\n" + ', '.join(CATEGORIAS)
    if field == 'quien': return "Es de Manuel o de Merche?"

def build_summary(expense: dict) -> str:
    notas = expense.get('notas') or '-'
    return (f"Resumen — di 'si' para guardar o corrige con el numero:\n\n"
            f"1. Concepto: {expense.get('concepto','-')}\n"
            f"2. Importe: {expense.get('cantidad','-')} euros\n"
            f"3. Categoria: {expense.get('categoria','-')}\n"
            f"4. Quien: {expense.get('quien','-')}\n"
            f"5. Notas: {notas}\n\n"
            f"Ej: '1 Alcampo' o '5 huevos y pescado'")

async def save_expense(chat_id: int, expense: dict) -> str:
    del pending_expenses[chat_id]
    from datetime import datetime
    today = datetime.now().strftime('%Y-%m-%d')
    # Capitalizar primera letra de texto
    def cap(s): return s.capitalize() if s else s
    
    success = save_to_supabase({
        'concepto': cap(expense.get('concepto','')),
        'cantidad': abs(float(expense.get('cantidad', 0))),  # siempre positivo
        'quien': expense.get('quien',''),
        'categoria': cap(expense.get('categoria','')),
        'fecha': today,
        'nota': cap(expense.get('notas','') or ''),
    })
    if success:
        return f"Guardado: {expense.get('concepto')} — {expense.get('cantidad')} euros · {expense.get('categoria')} · {expense.get('quien')}. Ya esta en la app."
    return "Error guardando. Intentalo de nuevo."

def get_missing_fields(expense: dict) -> list:
    return [f for f in ['cantidad','concepto','categoria','quien'] if not expense.get(f)]

def resumen_hoy() -> str:
    """Devuelve los gastos del dia de hoy desde Supabase."""
    from datetime import date
    import requests, os
    url = os.environ.get('FAMILIA_SUPABASE_URL', '')
    key = os.environ.get('FAMILIA_SUPABASE_KEY', '')
    hoy = date.today().isoformat()
    try:
        r = requests.get(
            f"{url}/rest/v1/gastos?fecha=eq.{hoy}&order=created_at.desc",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=10
        )
        gastos = r.json() if r.status_code == 200 else []
        if not gastos:
            return f"Hoy {date.today().strftime('%d/%m')} no hay gastos registrados."
        total = sum(float(g.get('cantidad', 0)) for g in gastos)
        lineas = [f"Gastos de hoy {date.today().strftime('%d/%m')}:\n"]
        for g in gastos:
            lineas.append(f"- {g.get('concepto','?')} {g.get('cantidad','?')}€ · {g.get('quien','?')}")
        lineas.append(f"\nTOTAL: {round(total,2)}€")
        return "\n".join(lineas)
    except Exception as e:
        return f"Error consultando gastos: {e}"
