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
from agents import tutoria, ef, recordatorios, racing, gastos
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

async def cmd_canales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el estado de los canales configurados."""
    channels = db.get_channel_ids()
    emoji_map = {'ef':'🏃','tutoria':'📋','recordatorios':'⏰','racing':'📸','gastos':'💰','general':'🧠'}
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

    # ── Clasificar dominio ────────────────────────────────
    domain = await router.classify(text)

    # ── Procesar con agente correcto ──────────────────────
    if domain == 'tutoria':
        response = await tutoria.handle(text, chat_id)
    elif domain == 'ef':
        response = await ef.handle(text)
    elif domain == 'recordatorios':
        response = await recordatorios.handle(text, chat_id)
    elif domain == 'racing':
        response = await racing.handle(text)
    elif domain == 'gastos':
        response = await gastos.handle(text, chat_id)
    else:
        response = gemini.ask("Eres el asistente personal de Txako. Responde en español.\n\n" + text)
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
        await update.message.reply_text("❌ No pude transcribir el audio. Inténtalo de nuevo.")
        return

    # Confirmar transcripción al usuario
    await update.message.reply_text(f"🎤 *Escuché:* _{transcription}_", parse_mode='Markdown')

    # Procesar como texto normal
    domain = await router.classify(transcription)
    
    if domain == 'tutoria':
        response = await tutoria.handle(transcription, update.effective_chat.id, is_voice=True)
    elif domain == 'ef':
        response = await ef.handle(transcription)
    elif domain == 'recordatorios':
        response = await recordatorios.handle(transcription, update.effective_chat.id)
    elif domain == 'racing':
        response = await racing.handle(transcription)
    elif domain == 'gastos':
        response = await gastos.handle(transcription, update.effective_chat.id)
    else:
        response = gemini.ask(transcription)
        domain = 'general'

    await send_to_channel(context.bot, domain, response, update.effective_chat.id)

# ─── SCHEDULER DE RECORDATORIOS ───────────────────────────

async def fire_reminders(bot):
    pending = db.get_pending_reminders()
    channels = db.get_channel_ids()
    recordatorios_chat = channels.get('recordatorios', config.MY_CHAT_ID)
    
    for r in pending:
        try:
            await bot.send_message(
                chat_id=recordatorios_chat,
                text=f"⏰ *RECORDATORIO*\n\n{r['descripcion']}",
                parse_mode='Markdown'
            )
            db.mark_reminder_sent(r['id'])
        except Exception as e:
            logger.error(f"Error enviando recordatorio {r['id']}: {e}")

# ─── MAIN ─────────────────────────────────────────────────

def main():
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()

    # Comandos
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('setup', cmd_setup))
    app.add_handler(CommandHandler('canales', cmd_canales))

    # Mensajes
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))

    # Scheduler recordatorios (cada minuto)
    scheduler = AsyncIOScheduler(timezone=TZ)
    scheduler.add_job(
        fire_reminders,
        trigger=IntervalTrigger(minutes=1),
        kwargs={'bot': app.bot},
        id='reminders',
        replace_existing=True
    )
    scheduler.start()

    logger.info("🤖 Bot Maestro de Txako arrancado.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
    
