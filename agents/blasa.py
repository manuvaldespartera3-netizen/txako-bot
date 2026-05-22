"""
Agente BLASA - Recordatorios, eventos y cumpleaños.
- Eventos puntuales: avisa el día anterior a las 21:00, luego cada 2h entre 8:00-22:00
- Cumpleaños: avisa el día del cumple a las 10:00
- Consultas: hoy, mañana, esta semana
- Gestión: hecho ID, cancela ID, borra ID
"""
import json, logging, os, re, requests
import gemini
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

def get_tz():
    import pytz
    return pytz.timezone('Europe/Madrid')

def get_db():
    return os.environ.get('SUPABASE_URL',''), os.environ.get('SUPABASE_KEY','')

def db_get(tabla: str, query: str = '') -> list:
    url, key = get_db()
    r = requests.get(
        f"{url}/rest/v1/{tabla}?{query}",
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

# ─── PARSERS ─────────────────────────────────────────────

async def parse_evento(text: str) -> dict | None:
    now = datetime.now(get_tz())
    dias = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
    proximos = {}
    for i in range(1, 8):
        d = now + timedelta(days=i)
        proximos[dias[d.weekday()]] = d.strftime('%Y-%m-%d')
    proximos_str = "\n".join([f"- {k} = {v}" for k, v in proximos.items()])

    prompt = f"""Extrae la información de este recordatorio o evento.
HOY es: {now.strftime('%Y-%m-%d')} ({dias[now.weekday()]})
MAÑANA es: {(now + timedelta(days=1)).strftime('%Y-%m-%d')}
Próximos días:
{proximos_str}

Texto: "{text}"

Responde SOLO con JSON sin markdown:
{{"descripcion": "tarea clara y corta", "fecha": "YYYY-MM-DD", "hora": "HH:MM o null", "valido": true}}
Si no hay fecha: {{"valido": false}}"""
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
Meses: enero=01, febrero=02, marzo=03, abril=04, mayo=05, junio=06,
julio=07, agosto=08, septiembre=09, octubre=10, noviembre=11, diciembre=12

Responde SOLO con JSON sin markdown:
{{"nombre": "nombre", "mes": "01-12", "dia": "01-31", "valido": true}}
Si falta nombre o fecha: {{"valido": false}}"""
    try:
        raw = gemini.ask(prompt).strip().replace('```json','').replace('```','').strip()
        data = json.loads(raw)
        if not data.get('valido'):
            return None
        mes = str(data['mes']).zfill(2)
        dia = str(data['dia']).zfill(2)
        return {'nombre': data['nombre'], 'fecha': f"{mes}-{dia}", 'valido': True}
    except Exception as e:
        logger.error(f"Error parseando cumpleaños: {e}")
        return None

# ─── CONSULTAS ────────────────────────────────────────────

def get_eventos_rango(desde: date, hasta: date, solo_pendientes: bool = True) -> list:
    url, key = get_db()
    query = f"fecha=gte.{desde.isoformat()}&fecha=lte.{hasta.isoformat()}&order=fecha.asc,hora.asc"
    if solo_pendientes:
        query += "&confirmado=eq.false"
    r = requests.get(
        f"{url}/rest/v1/blasa_eventos?{query}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=10
    )
    return r.json() if r.status_code == 200 else []

def get_cumpleanos_rango(desde: date, hasta: date) -> list:
    todos = db_get('blasa_cumpleanos', 'order=fecha.asc')
    result = []
    for c in todos:
        try:
            mes_dia = c['fecha'][5:] if len(c['fecha']) > 5 else c['fecha']
            mes = int(mes_dia[:2])
            dia = int(mes_dia[3:])
            for año in [desde.year, desde.year + 1]:
                cumple = date(año, mes, dia)
                if desde <= cumple <= hasta:
                    result.append({**c, 'fecha_cumple': cumple})
        except:
            pass
    return sorted(result, key=lambda x: x['fecha_cumple'])

def formatear_eventos(eventos: list, cumples: list, titulo: str) -> str:
    if not eventos and not cumples:
        return f"{titulo}: no tienes nada."
    lineas = [f"{titulo}:\n"]
    for c in cumples:
        lineas.append(f"Cumpleanos de {c['nombre']}")
    for e in eventos:
        hora_str = f" a las {e['hora'][:5]}" if e.get('hora') else ""
        estado = " (completado)" if e.get('confirmado') else ""
        lineas.append(f"- [{e['id']}] {e['descripcion']}{hora_str}{estado}")
    return "\n".join(lineas)

def consulta_hoy() -> str:
    hoy = date.today()
    eventos = get_eventos_rango(hoy, hoy)
    cumples = get_cumpleanos_rango(hoy, hoy)
    return formatear_eventos(eventos, cumples, f"Hoy {hoy.strftime('%d/%m')}")

def consulta_manana() -> str:
    manana = date.today() + timedelta(days=1)
    eventos = get_eventos_rango(manana, manana)
    cumples = get_cumpleanos_rango(manana, manana)
    return formatear_eventos(eventos, cumples, f"Manana {manana.strftime('%d/%m')}")

def consulta_semana() -> str:
    hoy = date.today()
    fin = hoy + timedelta(days=7)
    eventos = get_eventos_rango(hoy, fin)
    cumples = get_cumpleanos_rango(hoy, fin)
    return formatear_eventos(eventos, cumples, f"Proximos 7 dias ({hoy.strftime('%d/%m')} - {fin.strftime('%d/%m')})")

def listar_cumpleanos() -> str:
    hoy = date.today()
    fin = hoy + timedelta(days=365)
    proximos = get_cumpleanos_rango(hoy, fin)
    todos = db_get('blasa_cumpleanos', 'order=fecha.asc')
    if not todos:
        return "No tienes cumpleanos guardados."
    lineas = [f"Cumpleanos guardados ({len(todos)}):\n"]
    prox_ids = {p['id']: p['dias_faltan'] for p in proximos} if proximos else {}
    for c in todos:
        mes_dia = c['fecha'][5:].replace('-', '/')
        p = next((p for p in proximos if p['id'] == c['id']), None)
        sufijo = f" (en {(p['fecha_cumple'] - hoy).days} dias)" if p else ""
        lineas.append(f"- [{c['id']}] {c['nombre']}: {mes_dia}{sufijo}")
    return "\n".join(lineas)

# ─── SCHEDULER ────────────────────────────────────────────

async def check_y_enviar(bot, blasa_chat_id: int):
    if not blasa_chat_id:
        return
    now = datetime.now(get_tz())
    hora = now.hour
    minuto = now.minute

    # Solo entre 8:00 y 22:00
    if hora < 8 or hora >= 22:
        return

    hoy = date.today()
    manana = hoy + timedelta(days=1)
    url, key = get_db()

    # Cumpleaños hoy a las 10:00
    if hora == 10 and minuto < 6:
        for c in get_cumpleanos_rango(hoy, hoy):
            await bot.send_message(
                chat_id=blasa_chat_id,
                text="Hoy es el cumpleanos de " + c['nombre'] + "! No te olvides de felicitarle."
            )

    # Aviso dia anterior a las 21:00
    if hora == 21 and minuto < 6:
        r = requests.get(
            f"{url}/rest/v1/blasa_eventos?fecha=eq.{manana.isoformat()}&avisado_dia_antes=eq.false&confirmado=eq.false",
            headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=10
        )
        for e in (r.json() if r.status_code == 200 else []):
            hora_str = f" a las {e['hora'][:5]}" if e.get('hora') else ""
            await bot.send_message(
                chat_id=blasa_chat_id,
                text="Manana tienes: " + e['descripcion'] + hora_str
            )
            db_update('blasa_eventos', e['id'], {'avisado_dia_antes': True})

    # Eventos de hoy — cada 2h entre 8:00 y 22:00
    r2 = requests.get(
        f"{url}/rest/v1/blasa_eventos?fecha=eq.{hoy.isoformat()}&confirmado=eq.false",
        headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=10
    )
    for e in (r2.json() if r2.status_code == 200 else []):
        ultimo = e.get('ultimo_aviso')
        debe_avisar = not ultimo
        if ultimo:
            ultimo_dt = datetime.fromisoformat(ultimo.replace('Z', '+00:00'))
            if (now - ultimo_dt).total_seconds() >= 7200:
                debe_avisar = True
        if debe_avisar:
            hora_str = f" a las {e['hora'][:5]}" if e.get('hora') else ""
            await bot.send_message(
                chat_id=blasa_chat_id,
                text="Recuerda: " + e['descripcion'] + hora_str + "\n\nDi 'hecho " + str(e['id']) + "' para completarlo o 'cancela " + str(e['id']) + "' para eliminarlo."
            )
            db_update('blasa_eventos', e['id'], {'ultimo_aviso': now.isoformat()})

# ─── HANDLER PRINCIPAL ────────────────────────────────────

async def handle(text: str, chat_id: int) -> str:
    text_lower = text.lower().strip()

    # Completar evento: "hecho 3" o "completado 3"
    m = re.match(r'(hecho|completado|listo|done)\s+(\d+)', text_lower)
    if m:
        eid = int(m.group(2))
        if db_update('blasa_eventos', eid, {'confirmado': True}):
            return "Evento " + str(eid) + " marcado como completado."
        return "No encontre el evento " + str(eid) + "."

    # Cancelar/borrar evento: "cancela 3" o "borra 3"
    m = re.match(r'(cancela|borra|elimina|borrar|cancelar|eliminar)\s+(\d+)', text_lower)
    if m:
        eid = int(m.group(2))
        if db_delete('blasa_eventos', eid) or db_delete('blasa_cumpleanos', eid):
            return "Borrado el elemento con ID " + str(eid) + "."
        return "No encontre nada con ID " + str(eid) + "."

    # Consultas
    if any(k in text_lower for k in ['qué tengo hoy','que tengo hoy','agenda hoy','agenda de hoy','eventos hoy']):
        return consulta_hoy()
    if any(k in text_lower for k in ['qué tengo mañana','que tengo mañana','agenda mañana','agenda de mañana','eventos mañana','eventos manana']):
        return consulta_manana()
    if any(k in text_lower for k in ['esta semana','la semana','próximos días','proximos dias','semana']):
        return consulta_semana()
    if any(k in text_lower for k in ['mis cumpleaños','mis cumpleanos','ver cumpleaños','listar cumple']):
        return listar_cumpleanos()

    # Añadir cumpleaños
    cumple_kw = ['cumpleaños de','cumpleanos de','cumple de','cumple el','apunta el cumple','nació','nacio']
    if any(k in text_lower for k in cumple_kw):
        return await anadir_cumpleanos(text)

    # Añadir evento (todo lo demás)
    return await anadir_evento(text)

async def anadir_cumpleanos(text: str) -> str:
    datos = await parse_cumpleanos(text)
    if not datos:
        return "No entendi. Dimelo asi:\n'Cumpleanos de Maria el 15 de marzo'"
    fecha_guardada = f"2000-{datos['fecha']}"
    if db_insert('blasa_cumpleanos', {'nombre': datos['nombre'].capitalize(), 'fecha': fecha_guardada}):
        return "Cumpleanos de " + datos['nombre'].capitalize() + " guardado: " + datos['fecha'].replace('-','/')
    return "Error guardando el cumpleanos."

async def anadir_evento(text: str) -> str:
    datos = await parse_evento(text)
    if not datos:
        return "No entendi la fecha. Dimelo asi:\n'Comprar trofeos manana' o 'Reunion el martes a las 10'"
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
        return ("Evento guardado:\n" + datos['descripcion'].capitalize() +
                "\n" + fecha_dt.strftime('%d/%m/%Y') + hora_str +
                "\n\nTe avisare el dia antes a las 21:00 y el mismo dia cada 2h (entre 8:00 y 22:00).")
    return "Error guardando el evento."
