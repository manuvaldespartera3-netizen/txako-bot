"""
Bot Maestro — Txako
"""
import asyncio, logging
from datetime import datetime
import pytz

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import gemini

import config, db, router
from agents import tutoria, ef, recordatorios, racing, gastos, calculin, blasa, viajes
from agents.tutoria import pending_grades
from agents.gastos import pending_expenses
from agents.viajes import pending_viajes
from agents.tiempo import obtener_tiempo, formato_mensaje, get_ciudad, set_ciudad

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
TZ = pytz.timezone('Europe/Madrid')

async def send_to_channel(bot, domain: str, text: str, fallback_chat_id: int = None):
    chat_id = config.CANALES.get(domain, 0)
    if not chat_id:
        target = fallback_chat_id or config.MY_CHAT_ID
        logger.info(f"Canal '{domain}' no configurado. Enviando a {target}.")
        await bot.send_message(chat_id=target, text=text)
        return
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            await bot.send_message(chat_id=chat_id, text=chunk, parse_mode='Markdown')
        except Exception:
            try:
                await bot.send_message(chat_id=chat_id, text=chunk)
            except Exception as e:
                logger.error(f"Error enviando mensaje: {e}")

async def transcribe_voice(bot, file_id: str) -> str | None:
    import requests, os
    try:
        file = await bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        groq_key = os.environ.get('GROQ_API_KEY', '')
        response = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {groq_key}"},
            files={"file": ("audio.ogg", bytes(file_bytes), "audio/ogg")},
            data={"model": "whisper-large-v3", "language": "es"},
            timeout=30
        )
        data = response.json()
        return data.get("text", "").strip()
    except Exception as e:
        logger.error(f"Error transcribiendo voz: {e}")
        return None

PALABRAS_TIEMPO = [
    "tiempo", "llueve", "lluvia", "temperatura", "calor", "frío", "frio",
    "nublado", "sol", "viento", "clima", "paraguas", "nieva", "nieve",
    "tormenta", "hace hoy", "weather", "grados"
]

def detectar_pregunta_tiempo(texto: str):
    import re
    texto_lower = texto.lower()
    if not any(p in texto_lower for p in PALABRAS_TIEMPO):
        return False, None
    match = re.search(
        r"\ben\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)",
        texto
    )
    if match:
        return True, match.group(1)
    return True, None

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != config.MY_CHAT_ID:
        return
    channels = db.get_channel_ids()
    configured = [d for d in config.DOMAINS if d in channels]
    missing = [d for d in config.DOMAINS if d not in channels]
    msg = "🤖 *Bot Maestro activo*\n\n"
    if configured:
        msg += f"✅ Canales configurados: {', '.join(configured)}\n"
    if missing:
        msg += f"⚠️ Sin configurar: {', '.join(missing)}\n\nPara configurar: `/setup ef`"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Uso: `/setup dominio`\nDominios: ef, tutoria, recordatorios, racing, gastos, general", parse_mode='Markdown')
        return
    domain = None
    for arg in context.args:
        candidate = arg.lower().strip()
        if candidate in config.DOMAINS:
            domain = candidate
            break
    if not domain:
        await update.message.reply_text(f"Dominio inválido. Usa uno de: {', '.join(config.DOMAINS)}")
        return
    chat_id = update.effective_chat.id
    db.save_channel(domain, chat_id)
    emoji = {'ef':'🏃','tutoria':'📋','recordatorios':'⏰','racing':'📸','general':'🧠','viajes':'✈️'}.get(domain,'💬')
    await update.message.reply_text(f"{emoji} *Canal {domain.upper()} configurado*", parse_mode='Markdown')
    logger.info(f"Canal configurado: {domain} → {chat_id}")

async def cmd_hoy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from agents.gastos import resumen_hoy
    response = resumen_hoy()
    await send_to_channel(context.bot, 'gastos', response, update.effective_chat.id)

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    from agents.gastos import pending_expenses
    from agents.tutoria import pending_grades
    from agents.viajes import pending_viajes
    limpiados = []
    if chat_id in pending_expenses:
        del pending_expenses[chat_id]
        limpiados.append("gasto")
    if chat_id in pending_grades:
        del pending_grades[chat_id]
        limpiados.append("nota")
    if chat_id in pending_viajes:
        del pending_viajes[chat_id]
        limpiados.append("viaje")
    if limpiados:
        await update.message.reply_text(f"Reset hecho. Limpiado: {', '.join(limpiados)}.")
    else:
        await update.message.reply_text("No habia nada pendiente.")

async def cmd_canales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channels = db.get_channel_ids()
    emoji_map = {'ef':'🏃','tutoria':'📋','recordatorios':'⏰','racing':'📸','gastos':'💰','calculin':'🧮','blasa':'🔔','general':'🧠','viajes':'✈️'}
    msg = "📡 *Estado de canales*\n\n"
    for domain in config.DOMAINS:
        emoji = emoji_map.get(domain,'💬')
        if domain in channels:
            msg += f"{emoji} {domain}: ✅ configurado\n"
        else:
            msg += f"{emoji} {domain}: ❌ sin configurar\n"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def cmd_tiempo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ciudad = " ".join(context.args).strip() if context.args else get_ciudad()
    msg = formato_mensaje(ciudad)
    await update.message.reply_text(msg, parse_mode='Markdown')

async def cmd_ciudad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        nueva = " ".join(context.args).strip()
        datos = obtener_tiempo(nueva)
        if datos:
            set_ciudad(datos["ciudad"])
            await update.message.reply_text(f"✅ Ciudad actualizada a *{datos['ciudad']}*", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ No encontré *{nueva}*.", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"📍 Ciudad actual: *{get_ciudad()}*\nPara cambiarla: `/ciudad NombreCiudad`", parse_mode='Markdown')

async def enviar_tiempo_programado(bot, hora_label: str):
    msg = formato_mensaje(get_ciudad(), hora_label)
    await bot.send_message(chat_id=config.MY_CHAT_ID, text=msg, parse_mode='Markdown')

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if update.effective_chat.id != config.MY_CHAT_ID:
        return
    text = update.message.text
    chat_id = update.effective_chat.id

    # ── Confirmación pendiente de tutoría ────────────────
    from agents.tutoria import pending_grades, pending_batch, pending_new_col
    hay_pendiente_tutoria = (
        chat_id in pending_grades or
        chat_id in pending_batch or
        chat_id in pending_new_col
    )
    if hay_pendiente_tutoria:
        response = await tutoria.handle(text, chat_id)
        await send_to_channel(context.bot, 'tutoria', response, update.effective_chat.id)
        return

    # ── Gasto pendiente ───────────────────────────────────
    if chat_id in pending_expenses:
        response = await gastos.handle(text, chat_id)
        await send_to_channel(context.bot, 'gastos', response, update.effective_chat.id)
        return

    # ── Cuestionario de viaje pendiente ──────────────────
    if chat_id in pending_viajes:
        response = await viajes.handle(text, chat_id)
        await send_to_channel(context.bot, 'viajes', response, update.effective_chat.id)
        return

    await context.bot.send_chat_action(chat_id, 'typing')

    # ── Pregunta sobre el tiempo ──────────────────────────
    es_tiempo, ciudad_mencionada = detectar_pregunta_tiempo(text)
    if es_tiempo:
        ciudad = ciudad_mencionada if ciudad_mencionada else get_ciudad()
        msg = formato_mensaje(ciudad)
        await update.message.reply_text(msg, parse_mode='Markdown')
        return

    text_lower_check = text.lower().strip()
    domain = None
    clean_text = text
    canal_nombres = [
        ('blasa', 'blasa'), ('manirrota', 'gastos'),
        ('pitagorín', 'calculin'), ('pitagorin', 'calculin'),
        ('ef,', 'ef'), ('ef:', 'ef'),
        ('racing', 'racing'), ('tutoría', 'tutoria'), ('tutoria', 'tutoria'),
        ('viajes', 'viajes'), ('escapada', 'viajes'), ('viaje', 'viajes'),
    ]
    for nombre, dom in canal_nombres:
        if text_lower_check.startswith(nombre):
            domain = dom
            clean_text = text[len(nombre):].lstrip(',:').strip()
            break
    if not domain:
        blasa_triggers = ['recuérdame','recuerda','recuerdame','avísame','avisame',
                          'recordatorio','no me olvide','que no se me olvide',
                          'cumpleaños de','cumpleanos de','apunta el cumple',
                          'qué tengo hoy','que tengo hoy','agenda hoy',
                          'qué tengo mañana','que tengo mañana','mis cumpleaños',
                          'hecho ','cancela ','borra ','completado ','listo ','esta semana','la semana']
        if any(k in text_lower_check for k in blasa_triggers):
            domain = 'blasa'
    if not domain:
        ef_triggers = ['juego de','juegos de','actividad para','sesión de ef','sin material','calentamiento']
        if any(k in text_lower_check for k in ef_triggers):
            domain = 'ef'
    if not domain:
        viajes_triggers = [
            'quiero ir a', 'planifica', 'organiza el viaje',
            'ideas para viajar', 'dónde vamos', 'donde vamos',
            'vacaciones de', 'viaje de', 'destino para',
            'qué me recomiendas para viajar'
        ]
        if any(k in text_lower_check for k in viajes_triggers):
            domain = 'viajes'
    if not domain:
        domain = await router.classify(text)
    if domain == 'tutoria':
        response = await tutoria.handle(clean_text, chat_id)
    elif domain == 'ef':
        response = await ef.handle(clean_text)
    elif domain == 'recordatorios':
        response = await recordatorios.handle(clean_text, chat_id)
    elif domain == 'racing':
        response = await racing.handle(clean_text)
    elif domain == 'gastos':
        response = await gastos.handle(clean_text, chat_id)
    elif domain == 'calculin':
        response = await calculin.handle(clean_text)
    elif domain == 'blasa':
        response = await blasa.handle(clean_text, chat_id)
    elif domain == 'viajes':
        response = await viajes.handle(clean_text, chat_id)
    else:
        response = gemini.ask("Eres el asistente personal de Txako. Responde en español.\n\n" + clean_text)
        domain = 'general'
    await send_to_channel(context.bot, domain, response, update.effective_chat.id)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != config.MY_CHAT_ID:
        return
    await context.bot.send_chat_action(update.effective_chat.id, 'typing')
    voice = update.message.voice or update.message.audio
    if not voice:
        return
    transcription = await transcribe_voice(context.bot, voice.file_id)
    if not transcription:
        await update.message.reply_text("No pude transcribir el audio. Intentalo de nuevo.")
        return
    await update.message.reply_text(f"Escuche: {transcription}")
    chat_id = update.effective_chat.id

    # ── Confirmación pendiente de tutoría por voz ────────
    from agents.tutoria import pending_grades, pending_batch, pending_new_col
    hay_pendiente_tutoria = (
        chat_id in pending_grades or
        chat_id in pending_batch or
        chat_id in pending_new_col
    )
    if hay_pendiente_tutoria:
        response = await tutoria.handle(transcription, chat_id, is_voice=True)
        await send_to_channel(context.bot, 'tutoria', response, chat_id)
        return

    if chat_id in pending_expenses:
        response = await gastos.handle(transcription, chat_id)
        await send_to_channel(context.bot, 'gastos', response, chat_id)
        return

    # ── Cuestionario de viaje pendiente por voz ──────────
    if chat_id in pending_viajes:
        response = await viajes.handle(transcription, chat_id)
        await send_to_channel(context.bot, 'viajes', response, chat_id)
        return

    es_tiempo, ciudad_mencionada = detectar_pregunta_tiempo(transcription)
    if es_tiempo:
        ciudad = ciudad_mencionada if ciudad_mencionada else get_ciudad()
        msg = formato_mensaje(ciudad)
        await update.message.reply_text(msg, parse_mode='Markdown')
        return

    trans_lower = transcription.lower().strip()
    domain = None
    clean_trans = transcription
    canal_nombres = [
        ('blasa', 'blasa'), ('manirrota', 'gastos'),
        ('pitagorín', 'calculin'), ('pitagorin', 'calculin'),
        ('racing', 'racing'), ('tutoría', 'tutoria'), ('tutoria', 'tutoria'),
        ('viajes', 'viajes'), ('escapada', 'viajes'), ('viaje', 'viajes'),
    ]
    for nombre, dom in canal_nombres:
        if trans_lower.startswith(nombre):
            domain = dom
            clean_trans = transcription[len(nombre):].lstrip(',:').strip()
            break
    if not domain:
        viajes_triggers = [
            'quiero ir a', 'planifica', 'organiza el viaje',
            'ideas para viajar', 'dónde vamos', 'donde vamos',
            'vacaciones de', 'viaje de', 'destino para',
            'qué me recomiendas para viajar'
        ]
        if any(k in trans_lower for k in viajes_triggers):
            domain = 'viajes'
    if not domain:
        domain = await router.classify(transcription)
    transcription = clean_trans
    if domain == 'tutoria':
        response = await tutoria.handle(transcription, chat_id, is_voice=True)
    elif domain == 'ef':
        response = await ef.handle(transcription)
    elif domain == 'recordatorios':
        response = await recordatorios.handle(transcription, chat_id)
    elif domain == 'racing':
        response = await racing.handle(transcription)
    elif domain == 'gastos':
        response = await gastos.handle(transcription, chat_id)
    elif domain == 'calculin':
        response = await calculin.handle(transcription)
    elif domain == 'blasa':
        response = await blasa.handle(transcription, chat_id)
    elif domain == 'viajes':
        response = await viajes.handle(clean_trans, chat_id)
    else:
        response = gemini.ask("Eres el asistente personal de Txako. Responde en espanol.\n\n" + transcription)
        domain = 'general'
    await send_to_channel(context.bot, domain, response, chat_id)

async def fire_reminders(bot):
    try:
        pending = db.get_pending_reminders()
        channels = db.get_channel_ids()
        recordatorios_chat = channels.get("recordatorios", config.MY_CHAT_ID)
        for r in pending:
            try:
                await bot.send_message(chat_id=recordatorios_chat, text="Recordatorio: " + r["descripcion"])
                db.mark_reminder_sent(r["id"])
            except Exception as e:
                logger.error(f"Error recordatorio: {e}")
    except Exception as e:
        logger.error(f"Error fire_reminders: {e}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != config.MY_CHAT_ID:
        return
    await context.bot.send_chat_action(update.effective_chat.id, 'typing')
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    import requests, base64, os, json
    groq_key = os.environ.get('GROQ_API_KEY', '')
    img_b64 = base64.b64encode(bytes(file_bytes)).decode()
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={
                "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                    {"type": "text", "text": "Analiza este ticket y extrae datos. Responde SOLO con JSON sin markdown: {\"total\": numero_decimal, \"concepto\": \"nombre establecimiento\", \"categoria\": \"supermercado/restaurante/farmacia/gasolina/otros\", \"quien\": null}"}
                ]}],
                "max_tokens": 200
            },
            timeout=30
        )
        data = response.json()
        raw = data["choices"][0]["message"]["content"].strip().replace('```json','').replace('```','').strip()
        parsed = json.loads(raw)
        from agents.gastos import pending_expenses
        pending_expenses[update.effective_chat.id] = {
            'concepto': parsed.get('concepto', 'Compra').capitalize(),
            'cantidad': parsed.get('total'),
            'categoria': parsed.get('categoria', '').capitalize(),
            'quien': None,
            'notas': None
        }
        from agents import gastos
        response_text = await gastos.ask_missing(update.effective_chat.id)
        await send_to_channel(context.bot, 'gastos', response_text, update.effective_chat.id)
    except Exception as e:
        await update.message.reply_text("No pude leer el ticket. Intentalo con mejor iluminacion o dictalo por voz.")

def main():
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('setup', cmd_setup))
    app.add_handler(CommandHandler('canales', cmd_canales))
    app.add_handler(CommandHandler('reset', cmd_reset))
    app.add_handler(CommandHandler('hoy', cmd_hoy))
    app.add_handler(CommandHandler('tiempo', cmd_tiempo))
    app.add_handler(CommandHandler('ciudad', cmd_ciudad))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    scheduler = AsyncIOScheduler(timezone=TZ)
    scheduler.add_job(fire_reminders, trigger=IntervalTrigger(minutes=1), kwargs={'bot': app.bot}, id='reminders', replace_existing=True)
    async def blasa_check_wrapper():
        await blasa.check_y_enviar(app.bot, config.CANALES.get('blasa', 0))
    scheduler.add_job(blasa_check_wrapper, trigger=IntervalTrigger(minutes=5), id='blasa_check', replace_existing=True)
    async def racing_plan_wrapper():
        now = datetime.now(pytz.timezone('Europe/Madrid'))
        if now.weekday() == 0 and now.hour == 9 and now.minute < 6:
            racing_chat = config.CANALES.get('racing', 0)
            if racing_chat:
                plan = await racing.plan_semanal()
                await app.bot.send_message(chat_id=racing_chat, text="PLAN DE LA SEMANA\n\n" + plan)
    scheduler.add_job(racing_plan_wrapper, trigger=IntervalTrigger(minutes=5), id='racing_plan', replace_existing=True)
    for hora, label in [(9,"09:00"), (11,"11:00"), (14,"14:00"), (18,"18:00"), (21,"21:00")]:
        scheduler.add_job(enviar_tiempo_programado, trigger=CronTrigger(hour=hora, minute=0, timezone=TZ), kwargs={'bot': app.bot, 'hora_label': label}, id=f'tiempo_{hora}h', replace_existing=True)
    scheduler.start()
    logger.info("Bot Maestro arrancado.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
