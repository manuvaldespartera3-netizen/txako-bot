"""
Agente Recordatorios.
Crea, lista y gestiona recordatorios con lenguaje natural.
"""
import json, logging
from datetime import datetime
import pytz
import google.generativeai as genai
import config, db

logger = logging.getLogger(__name__)
model = genai.GenerativeModel('gemini-1.5-flash-latest')
TZ = pytz.timezone('Europe/Madrid')

async def parse_reminder(text: str) -> dict | None:
    now = datetime.now(TZ)
    dias = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
    prompt = f"""Extrae la información del recordatorio.
Ahora mismo es: {now.strftime('%Y-%m-%d %H:%M')} ({dias[now.weekday()]}, hora de Madrid)

Texto: "{text}"

Responde SOLO con JSON sin markdown:
{{"descripcion": "tarea clara y corta", "fecha_hora": "YYYY-MM-DD HH:MM", "valido": true}}
Si no hay fecha/hora: {{"valido": false}}
"""
    try:
        response = model.generate_content(prompt)
        raw = response.text.strip().replace('```json','').replace('```','').strip()
        data = json.loads(raw)
        return data if data.get('valido') else None
    except Exception as e:
        logger.error(f"Error parseando recordatorio: {e}")
        return None

async def handle(text: str, chat_id: int) -> str:
    # Ver recordatorios pendientes
    if any(k in text.lower() for k in ['ver', 'lista', 'qué tengo', 'pendientes', 'mis recordatorios']):
        return list_reminders(chat_id)

    # Crear recordatorio
    data = await parse_reminder(text)
    if data:
        try:
            fecha_hora = datetime.strptime(data['fecha_hora'], '%Y-%m-%d %H:%M')
            fecha_hora = TZ.localize(fecha_hora)
            if db.save_reminder(chat_id, data['descripcion'], fecha_hora.isoformat()):
                return (
                    f"✅ *Recordatorio creado*\n\n"
                    f"📝 {data['descripcion']}\n"
                    f"⏰ {fecha_hora.strftime('%d/%m/%Y a las %H:%M')}"
                )
        except ValueError:
            pass

    return (
        "No detecté una fecha clara. Dímelo así:\n\n"
        "_\"mañana a las 9 reunión con los padres\"_\n"
        "_\"el viernes a las 17 entregar notas\"_"
    )

def list_reminders(chat_id: int) -> str:
    futuros = db.get_future_reminders(chat_id)
    if not futuros:
        return "No tienes recordatorios pendientes. ✨"
    texto = f"⏰ *Pendientes ({len(futuros)})*\n\n"
    for r in futuros:
        fecha = datetime.fromisoformat(r['fecha_hora'])
        if fecha.tzinfo is None:
            fecha = TZ.localize(fecha)
        texto += f"• {fecha.strftime('%d/%m %H:%M')} — {r['descripcion']}\n"
    return texto
