"""
Bot Maestro — Txako
Recibe TODOS los mensajes de Txako y los enruta al agente correcto.
Las respuestas van al chat especializado correspondiente.
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
import gemini

import config, db, router
from agents import tutoria, ef, recordatorios, racing, gastos, calculin, blasa
from agents.tutoria import pending_grades
from agents.gastos import pending_expenses

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
TZ = pytz.timezone('Europe/Madrid')

# ─── ENVÍO A CHAT ESPECIALIZADO ───────────────────────────

async def send_to_channel(bot, domain: str, text: str, fallback_chat_id: int = None):
    """Envía la respuesta al chat del dominio correcto."""
    chat_id = config.CANALES.get(domain, 0)
    
    if not chat_id:
        # Sin canal configurado → responde donde escribió el usuario
        target = fallback_chat_id or config.MY_CHAT_ID
        logger.info(f"Canal '{domain}' no configurado. Enviando a {target}.")
        await bot.send_message(chat_id=target, text=text)
        return

    # Dividir mensajes largos (límite Telegram 4096 chars)
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            await bot.send_message(chat_id=chat_id, text=chunk)
        except Exception as e:
            logger.error(f"Error enviando mensaje: {e}")

# ─── TRANSCRIPCIÓN DE VOZ ─────────────────────────────────

async def transcribe_voice(bot, file_id: str) -> str | None:
    """Descarga el audio y lo transcribe con Groq Whisper."""
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

# ─── HANDLERS ─────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != config.MY_CHAT_ID:
        # Puede ser uno de los chats especializados haciendo /setup
        return
    channels = db.get_channel_ids()
    configured = [d for d in config.DOMAINS if d in channels]
    missing = [d for d in config.DOMAINS if d not in channels]
    
    msg = (
        "🤖 *Bot Maestro activo*\n\n"
        f"Escríbeme lo que necesites y lo envío al chat correcto.\n\n"
    )
    if configured:
        msg += f"✅ Canales configurados: {', '.join(configured)}\n"
    if missing:
        msg += (
            f"⚠️ Sin configurar: {', '.join(missing)}\n\n"
            "Para configurar un canal:\n"
            "1. Crea un grupo en Telegram\n"
            "2. Añade este bot al grupo\n"
            "3. Escribe en ese grupo: `/setup ef` (o tutoria, recordatorios, racing, general)"
        )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Se ejecuta en los chats especializados para registrarlos."""
    if not context.args:
        await update.message.reply_text(
            "Uso: `/setup dominio`\nDominios: ef, tutoria, recordatorios, racing, gastos, general",
            parse_mode='Markdown'
        )
        return
    # Buscar dominio en todos los args (por si viene con @bot delante)
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
    
    emoji = {'ef':'🏃','tutoria':'📋','recordatorios':'⏰','racing':'📸','general':'🧠'}.get(domain,'💬')
    await update.message.reply_text(
        f"{emoji} *Canal {domain.upper()} configurado*\n\nEste chat recibirá todas las respuestas de {domain}.",
        parse_mode='Markdown'
    )
    logger.info(f"Canal configurado: {domain} → {chat_id}")

async def cmd_hoy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los gastos de hoy."""
    from agents.gastos import resumen_hoy
    response = resumen_hoy()
    await send_to_channel(context.bot, 'gastos', response, update.effective_chat.id)

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Limpia todos los estados pendientes."""
    chat_id = update.effective_chat.id
    from agents.gastos import pending_expenses
    from agents.tutoria import pending_grades
    limpiados = []
    if chat_id in pending_expenses:
        del pending_expenses[chat_id]
        limpiados.append("gasto")
    if chat_id in pending_grades:
        del pending_grades[chat_id]
        limpiados.append("nota")
    if limpiados:
        await update.message.reply_text(f"Reset hecho. Limpiado: {', '.join(limpiados)}.")
    else:
        await update.message.reply_text("No habia nada pendiente.")

async def cmd_canales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el estado de los canales configurados."""
    channels = db.get_channel_ids()
    emoji_map = {'ef':'🏃','tutoria':'📋','recordatorios':'⏰','racing':'📸','gastos':'💰','calculin':'🧮','blasa':'🔔','general':'🧠'}
    msg = "📡 *Estado de canales*\n\n"
    for domain in config.DOMAINS:
        emoji = emoji_map.get(domain,'💬')
        if domain in channels:
            msg += f"{emoji} {domain}: ✅ configurado\n"
        else:
            msg += f"{emoji} {domain}: ❌ sin configurar\n"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa mensajes de texto del chat maestro."""
    if not update.message or not update.message.text:
        return
    if update.effective_chat.id != config.MY_CHAT_ID:
        return  # Ignorar mensajes en chats de respuesta

    text = update.message.text
    chat_id = update.effective_chat.id

    # ── Confirmación de nota pendiente ────────────────────
    if chat_id in pending_grades:
        if text.lower().strip() in ['sí', 'si', 'yes', 'ok', '✅', 'confirmar', 'correcto']:
            response = await tutoria.confirm_grade(chat_id)
            await send_to_channel(context.bot, 'tutoria', response, update.effective_chat.id)
            return
        elif text.lower().strip() in ['no', 'cancelar', 'cancel', '❌']:
            response = tutoria.cancel_grade(chat_id)
            await send_to_channel(context.bot, 'tutoria', response, update.effective_chat.id)
            return

    # ── Gasto en construcción (campos pendientes) ─────────
    if chat_id in pending_expenses:
        response = await gastos.handle(text, chat_id)
        await send_to_channel(context.bot, 'gastos', response, update.effective_chat.id)
        return

    # ── Mostrar "escribiendo..." ───────────────────────────
    await context.bot.send_chat_action(chat_id, 'typing')

    # ── MÁXIMA PRIORIDAD: nombre del canal al inicio ──────
    text_lower_check = text.lower().strip()
    domain = None
    clean_text = text

    # Si empieza por el nombre de un canal → va ahí SIN EXCEPCIONES
    canal_nombres = [
        ('blasa', 'blasa'),
        ('manirrota', 'gastos'),
        ('pitagorín', 'calculin'),
        ('pitagorin', 'calculin'),
        ('ef,', 'ef'),
        ('ef:', 'ef'),
        ('racing', 'racing'),
        ('tutoría', 'tutoria'),
        ('tutoria', 'tutoria'),
    ]
    for nombre, dom in canal_nombres:
        if text_lower_check.startswith(nombre):
            domain = dom
            clean_text = text[len(nombre):].lstrip(',:').strip()
            break

    # ── Solo si no hay canal explícito, usar palabras clave
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
        ef_triggers = ['juego de','juegos de','actividad para','sesión de ef',
                       'sin material','calentamiento']
        if any(k in text_lower_check for k in ef_triggers):
            domain = 'ef'

    # ── Router solo como último recurso ───────────────────
    if not domain:
        domain = await router.classify(text)

    # ── Procesar con agente correcto ──────────────────────
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
    else:
        response = gemini.ask("Eres el asistente personal de Txako. Responde en español.\n\n" + clean_text)
        domain = 'general'

    # ── Enviar al canal correcto ───────────────────────────
    await send_to_channel(context.bot, domain, response, update.effective_chat.id)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Transcribe nota de voz y procesa como texto."""
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

    # Si hay gasto pendiente, el audio va SIEMPRE al agente de gastos
    if chat_id in pending_expenses:
        response = await gastos.handle(transcription, chat_id)
        await send_to_channel(context.bot, 'gastos', response, chat_id)
        return

    # Sin pendiente — detectar canal por nombre primero
    trans_lower = transcription.lower().strip()
    domain = None
    clean_trans = transcription
    canal_nombres = [
        ('blasa', 'blasa'), ('manirrota', 'gastos'),
        ('pitagorín', 'calculin'), ('pitagorin', 'calculin'),
        ('racing', 'racing'), ('tutoría', 'tutoria'), ('tutoria', 'tutoria'),
    ]
    for nombre, dom in canal_nombres:
        if trans_lower.startswith(nombre):
            domain = dom
            clean_trans = transcription[len(nombre):].lstrip(',:').strip()
            break
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


# ─── MAIN ─────────────────────────────────────────────────

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa foto de ticket y extrae datos del gasto."""
    if update.effective_chat.id != config.MY_CHAT_ID:
        return
    await context.bot.send_chat_action(update.effective_chat.id, 'typing')
    
    # Descargar la foto
    photo = update.message.photo[-1]  # La de mayor resolución
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    
    # Mandar a Groq vision para extraer datos del ticket
    import requests, base64, os, json
    groq_key = os.environ.get('GROQ_API_KEY', '')
    img_b64 = base64.b64encode(bytes(file_bytes)).decode()
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
            json={
                "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                        {"type": "text", "text": """Analiza este ticket de compra y extrae los datos.
Responde SOLO con JSON sin markdown:
{"total": numero_decimal, "concepto": "nombre del establecimiento o tipo de compra", "categoria": "supermercado/restaurante/farmacia/gasolina/otros", "quien": null}
- total: el importe TOTAL del ticket (el número más grande que ponga TOTAL, IMPORTE, etc)
- concepto: nombre del establecimiento si aparece, si no "Compra"
- categoria: infiere por el tipo de negocio
- quien: siempre null (lo preguntaremos)"""}
                    ]
                }],
                "max_tokens": 200
            },
            timeout=30
        )
        data = response.json()
        raw = data["choices"][0]["message"]["content"].strip().replace('```json','').replace('```','').strip()
        parsed = json.loads(raw)
        
        # Meter en el flujo normal de gastos
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

    # Comandos
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('setup', cmd_setup))
    app.add_handler(CommandHandler('canales', cmd_canales))
    app.add_handler(CommandHandler('reset', cmd_reset))
    app.add_handler(CommandHandler('hoy', cmd_hoy))

    # Mensajes
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Scheduler recordatorios (cada minuto)
    scheduler = AsyncIOScheduler(timezone=TZ)
    scheduler.add_job(
        fire_reminders,
        trigger=IntervalTrigger(minutes=1),
        kwargs={'bot': app.bot},
        id='reminders',
        replace_existing=True
    )
    # Scheduler BLASA (cada 5 minutos)
    async def blasa_check_wrapper():
        await blasa.check_y_enviar(app.bot, config.CANALES.get('blasa', 0))
    scheduler.add_job(
        blasa_check_wrapper,
        trigger=IntervalTrigger(minutes=5),
        id='blasa_check',
        replace_existing=True
    )

    # Plan semanal Racing — cada lunes a las 9:00
    async def racing_plan_wrapper():
        import pytz
        from datetime import datetime
        now = datetime.now(pytz.timezone('Europe/Madrid'))
        if now.weekday() == 0 and now.hour == 9 and now.minute < 6:
            racing_chat = config.CANALES.get('racing', 0)
            if racing_chat:
                plan = await racing.plan_semanal()
                await app.bot.send_message(chat_id=racing_chat, text="PLAN DE LA SEMANA\n\n" + plan)
    scheduler.add_job(
        racing_plan_wrapper,
        trigger=IntervalTrigger(minutes=5),
        id='racing_plan',
        replace_existing=True
    )
    scheduler.start()

    logger.info("Bot Maestro arrancado.")

    # Arrancar Pitagorin en proceso separado
    import subprocess, sys
    subprocess.Popen([sys.executable, "pitagorin_bot.py"])
    logger.info("Pitagorin arrancado.")

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
