"""
Agente BLASA - Recordatorios y cumpleaños.
- Eventos puntuales: avisa el día antes, luego cada 2h hasta confirmar
- Cumpleaños: avisa el día del cumple a las 10:00
- Consulta: "qué tengo hoy/mañana"
- Gestión: listar, editar, borrar
"""
import json, logging, os, re
import requests
import gemini
from datetime import datetime, date, timedelta
import pytz

logger = logging.getLogger(__name__)
TZ = pytz.timezone('Europe/Madrid')

def get_db():
    url = os.environ.get('SUPABASE_URL', '')
    key = os.environ.get('SUPABASE_KEY', '')
    return url, key

def db_get(tabla: str, filtros: dict = {}) -> list:
    url, key = get_db()
    params = "&".join([f"{k}=eq.{v}" for k, v in filtros.items()])
    r = requests.get(
        f"{url}/rest/v1/{tabla}?{params}&order=fecha.asc",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=10
    )
    return r.json() if r.status_code == 200 else []

def db_insert(tabla: str, data: dict) -> bool:
    url, key = get_db()
    r = requests.post(
        f"{url}/rest/v1/{tabla}",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                "Content-Type": "application/json", "Prefer": "return=minimal"},
        json=data, timeout=10
    )
    return r.status_code in [200, 201]

def db_update(tabla: str, id: int, data: dict) -> bool:
    url, key = get_db()
    r = requests.patch(
        f"{url}/rest/v1/{tabla}?id=eq.{id}",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"},
        json=data, timeout=10
    )
    return r.status_code in [200, 204]

def db_delete(tabla: str, id: int) -> bool:
    url, key = get_db()
    r = requests.delete(
        f"{url}/rest/v1/{tabla}?id=eq.{id}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=10
    )
    return r.status_code in [200, 204]

# ─── PARSEAR CON IA ───────────────────────────────────────

async def parse_evento(text: str) -> dict | None:
    now = datetime.now(TZ)
    dias = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
    prompt = f"""Extrae la información de este evento o recordatorio.
Fecha actual: {now.strftime('%Y-%m-%d')} ({dias[now.weekday()]})
Texto: "{text}"

Responde SOLO con JSON sin markdown:
{{
  "descripcion": "descripción clara del evento",
  "fecha": "YYYY-MM-DD",
  "hora": "HH:MM o null si no se menciona",
  "valido": true
}}
Si no hay fecha clara: {{"valido": false}}
Interpreta: "mañana", "el lunes", "el 15 de junio", etc."""
    try:
        raw = gemini.ask(prompt).strip().replace('```json','').replace('```','').strip()
        data = json.loads(raw)
        return data if data.get('valido') else None
    except Exception as e:
        logger.error(f"Error parseando evento: {e}")
        return None

async def parse_cumpleanos(text: str) -> dict | None:
    prompt = f"""Extrae el nombre y la fecha de cumpleaños.
Texto: "{text}"

Responde SOLO con JSON sin markdown:
{{
  "nombre": "nombre de la persona",
  "fecha": "MM-DD (solo mes y dia, sin año)",
  "valido": true
}}
Si falta nombre o fecha: {{"valido": false}}
Ejemplos: "cumpleaños de María el 15 de marzo" → fecha: "03-15"
"Ana cumple el 5 de julio" → fecha: "07-05" """
    try:
        raw = gemini.ask(prompt).strip().replace('```json','').replace('```','').strip()
        data = json.loads(raw)
        return data if data.get('valido') else None
    except Exception as e:
        logger.error(f"Error parseando cumpleaños: {e}")
        return None

# ─── CONSULTAS ────────────────────────────────────────────

def get_eventos_hoy() -> list:
    today = date.today().isoformat()
    url, key = get_db()
    r = requests.get(
        f"{url}/rest/v1/blasa_eventos?fecha=eq.{today}&confirmado=eq.false",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=10
    )
    return r.json() if r.status_code == 200 else []

def get_eventos_manana() -> list:
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    url, key = get_db()
    r = requests.get(
        f"{url}/rest/v1/blasa_eventos?fecha=eq.{tomorrow}&confirmado=eq.false",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=10
    )
    return r.json() if r.status_code == 200 else []

def get_cumpleanos_hoy() -> list:
    today = date.today()
    mes_dia = today.strftime('%m-%d')
    url, key = get_db()
    r = requests.get(
        f"{url}/rest/v1/blasa_cumpleanos",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=10
    )
    todos = r.json() if r.status_code == 200 else []
    return [c for c in todos if c['fecha'].endswith(mes_dia) or c['fecha'][5:] == mes_dia]

def get_cumpleanos_manana() -> list:
    tomorrow = (date.today() + timedelta(days=1))
    mes_dia = tomorrow.strftime('%m-%d')
    url, key = get_db()
    r = requests.get(
        f"{url}/rest/v1/blasa_cumpleanos",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=10
    )
    todos = r.json() if r.status_code == 200 else []
    return [c for c in todos if c['fecha'].endswith(mes_dia) or c['fecha'][5:] == mes_dia]

def get_proximos_cumpleanos() -> list:
    """Devuelve cumpleaños de los próximos 30 días."""
    url, key = get_db()
    r = requests.get(
        f"{url}/rest/v1/blasa_cumpleanos",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=10
    )
    todos = r.json() if r.status_code == 200 else []
    hoy = date.today()
    proximos = []
    for c in todos:
        try:
            mes_dia = c['fecha'][5:] if len(c['fecha']) > 5 else c['fecha']
            cumple_este_año = date(hoy.year, int(mes_dia[:2]), int(mes_dia[3:]))
            if cumple_este_año < hoy:
                cumple_este_año = date(hoy.year + 1, int(mes_dia[:2]), int(mes_dia[3:]))
            dias_faltan = (cumple_este_año - hoy).days
            if 0 <= dias_faltan <= 30:
                proximos.append({**c, 'dias_faltan': dias_faltan, 'fecha_cumple': cumple_este_año})
        except:
            pass
    return sorted(proximos, key=lambda x: x['dias_faltan'])

# ─── SCHEDULER CHECKS ─────────────────────────────────────

async def check_y_enviar(bot, blasa_chat_id: int):
    """Llamado cada hora por el scheduler. Envía avisos a BLASA."""
    now = datetime.now(TZ)
    today = date.today()
    tomorrow = today + timedelta(days=1)

    # Cumpleaños hoy a las 10:00
    if now.hour == 10 and now.minute < 5:
        for c in get_cumpleanos_hoy():
            await bot.send_message(
                chat_id=blasa_chat_id,
                text=f"Hoy es el cumpleanos de {c['nombre']}! No te olvides de felicitarle."
            )

    # Eventos dia anterior — avisar por la mañana
    if now.hour == 9 and now.minute < 5:
        url, key = get_db()
        r = requests.get(
            f"{url}/rest/v1/blasa_eventos?fecha=eq.{tomorrow.isoformat()}&avisado_dia_antes=eq.false&confirmado=eq.false",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=10
        )
        eventos = r.json() if r.status_code == 200 else []
        for e in eventos:
            hora_str = f" a las {e['hora'][:5]}" if e.get('hora') else ""
            await bot.send_message(
                chat_id=blasa_chat_id,
                text=f"Manana tienes: {e['descripcion']}{hora_str}"
            )
            db_update('blasa_eventos', e['id'], {'avisado_dia_antes': True})

    # Eventos de hoy — avisar cada 2h si no confirmados
    r2 = requests.get(
        f"{url}/rest/v1/blasa_eventos?fecha=eq.{today.isoformat()}&confirmado=eq.false",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=10
    ) if 'url' in dir() else None

    url2, key2 = get_db()
    r2 = requests.get(
        f"{url2}/rest/v1/blasa_eventos?fecha=eq.{today.isoformat()}&confirmado=eq.false",
        headers={"apikey": key2, "Authorization": f"Bearer {key2}"},
        timeout=10
    )
    eventos_hoy = r2.json() if r2.status_code == 200 else []
    for e in eventos_hoy:
        ultimo = e.get('ultimo_aviso')
        if ultimo:
            ultimo_dt = datetime.fromisoformat(ultimo.replace('Z', '+00:00'))
            if (now - ultimo_dt).total_seconds() < 7200:  # menos de 2h
                continue
        hora_str = f" a las {e['hora'][:5]}" if e.get('hora') else ""
        await bot.send_message(
            chat_id=blasa_chat_id,
            text=f"Recuerda: {e['descripcion']}{hora_str}\n\nDi 'hecho {e['id']}' cuando lo hayas hecho."
        )
        db_update('blasa_eventos', e['id'], {'ultimo_aviso': now.isoformat()})

# ─── HANDLER PRINCIPAL ────────────────────────────────────

async def handle(text: str, chat_id: int) -> str:
    text_lower = text.lower().strip()

    # Confirmar evento hecho
    m = re.match(r'hecho\s+(\d+)', text_lower)
    if m:
        evento_id = int(m.group(1))
        if db_update('blasa_eventos', evento_id, {'confirmado': True}):
            return "Perfecto, evento marcado como hecho."
        return "No encontre ese evento."

    # Consulta de hoy
    if any(k in text_lower for k in ['qué tengo hoy', 'que tengo hoy', 'hoy', 'agenda hoy']):
        return consulta_hoy()

    # Consulta de mañana
    if any(k in text_lower for k in ['mañana', 'manana', 'agenda mañana']):
        return consulta_manana()

    # Borrar evento o cumpleaños
    if any(k in text_lower for k in ['borra', 'elimina', 'borrar', 'eliminar']):
        return await borrar(text)

    # Añadir cumpleaños — va antes de listar
    if any(k in text_lower for k in ['cumpleaños de', 'cumpleanos de', 'cumple el', 'cumple de', 'nació', 'nacio']):
        return await anadir_cumpleanos(text)

    # Listar cumpleaños
    if any(k in text_lower for k in ['listar', 'ver todos', 'mis cumpleaños', 'mis cumpleanos', 'cumpleaños guardados']):
        return listar_cumpleanos()

    # Añadir evento
    return await anadir_evento(text)

def consulta_hoy() -> str:
    eventos = get_eventos_hoy()
    cumples = get_cumpleanos_hoy()
    today = date.today()

    if not eventos and not cumples:
        return f"Hoy {today.strftime('%d/%m')} no tienes nada pendiente."

    lineas = [f"Agenda de hoy {today.strftime('%d/%m')}:\n"]
    if cumples:
        for c in cumples:
            lineas.append(f"Cumpleanos de {c['nombre']}")
    if eventos:
        for e in eventos:
            hora_str = f" a las {e['hora'][:5]}" if e.get('hora') else ""
            lineas.append(f"- {e['descripcion']}{hora_str} (ID: {e['id']})")
    return "\n".join(lineas)

def consulta_manana() -> str:
    eventos = get_eventos_manana()
    cumples = get_cumpleanos_manana()
    tomorrow = date.today() + timedelta(days=1)

    if not eventos and not cumples:
        return f"Manana {tomorrow.strftime('%d/%m')} no tienes nada."

    lineas = [f"Agenda de manana {tomorrow.strftime('%d/%m')}:\n"]
    if cumples:
        for c in cumples:
            lineas.append(f"Cumpleanos de {c['nombre']}")
    if eventos:
        for e in eventos:
            hora_str = f" a las {e['hora'][:5]}" if e.get('hora') else ""
            lineas.append(f"- {e['descripcion']}{hora_str}")
    return "\n".join(lineas)

def listar_cumpleanos() -> str:
    proximos = get_proximos_cumpleanos()
    url, key = get_db()
    r = requests.get(
        f"{url}/rest/v1/blasa_cumpleanos?order=fecha.asc",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=10
    )
    todos = r.json() if r.status_code == 200 else []
    if not todos:
        return "No tienes cumpleanos guardados."
    lineas = [f"Cumpleanos guardados ({len(todos)}):\n"]
    for c in todos:
        fecha_display = c['fecha'][5:].replace('-', '/')
        en_proximos = next((p for p in proximos if p['id'] == c['id']), None)
        sufijo = f" (en {en_proximos['dias_faltan']} dias)" if en_proximos else ""
        lineas.append(f"- {c['nombre']}: {fecha_display}{sufijo} (ID: {c['id']})")
    return "\n".join(lineas)

async def borrar(text: str) -> str:
    m = re.search(r'\d+', text)
    if not m:
        return "Dime el ID a borrar. Usa 'ver cumpleanos' o 'qué tengo hoy' para ver los IDs."
    id_borrar = int(m.group())
    # Intentar borrar de ambas tablas
    if db_delete('blasa_cumpleanos', id_borrar) or db_delete('blasa_eventos', id_borrar):
        return f"Borrado correctamente (ID {id_borrar})."
    return f"No encontre nada con ID {id_borrar}."

async def anadir_cumpleanos(text: str) -> str:
    datos = await parse_cumpleanos(text)
    if not datos:
        return "No entendi. Dimelo asi:\n'Cumpleanos de Maria el 15 de marzo'"
    fecha = datos['fecha']
    if len(fecha) == 5:  # MM-DD
        fecha_guardada = f"2000-{fecha}"  # año genérico
    else:
        fecha_guardada = fecha
    if db_insert('blasa_cumpleanos', {'nombre': datos['nombre'].capitalize(), 'fecha': fecha_guardada}):
        mes_dia = fecha[-5:].replace('-', '/')
        return f"Cumpleanos de {datos['nombre'].capitalize()} guardado: {mes_dia}"
    return "Error guardando el cumpleanos."

async def anadir_evento(text: str) -> str:
    datos = await parse_evento(text)
    if not datos:
        return "No entendi la fecha. Dimelo asi:\n'Reunion con el director el martes a las 10'"
    evento = {
        'descripcion': datos['descripcion'].capitalize(),
        'fecha': datos['fecha'],
        'hora': datos.get('hora'),
        'confirmado': False,
        'avisado_dia_antes': False,
    }
    if db_insert('blasa_eventos', evento):
        fecha_dt = datetime.strptime(datos['fecha'], '%Y-%m-%d')
        hora_str = f" a las {datos['hora'][:5]}" if datos.get('hora') else ""
        return (
            f"Evento guardado:\n"
            f"{datos['descripcion'].capitalize()}\n"
            f"{fecha_dt.strftime('%d/%m/%Y')}{hora_str}\n\n"
            f"Te avisare el dia antes y el mismo dia cada 2h hasta que confirmes."
        )
    return "Error guardando el evento."
