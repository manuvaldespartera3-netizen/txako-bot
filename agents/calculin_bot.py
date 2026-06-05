"""
Bot Calculín - Calculadora de cuentas compartidas
Adultos pagan precio completo, niños pagan la mitad.
Se usa por audio o texto en el grupo CALCULÍN.
"""
import os, logging, requests, json, re
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ['CALCULIN_TOKEN']
GROQ_KEY = os.environ.get('GROQ_API_KEY', '')

# ─── CÁLCULO ─────────────────────────────────────────────

def calcular(total: float, adultos: int, ninos: int = 0, propina_pct: float = 0) -> str:
    propina = round(total * propina_pct / 100, 2)
    total_final = round(total + propina, 2)
    partes = adultos + ninos * 0.5
    precio_adulto = round(total_final / partes, 2)
    precio_nino = round(precio_adulto / 2, 2)

    lineas = []
    lineas.append(f"Total cuenta: {total}€")
    if propina_pct > 0:
        lineas.append(f"Propina {propina_pct}%: {propina}€")
        lineas.append(f"Total con propina: {total_final}€")
    lineas.append("")
    lineas.append(f"Adulto paga: {precio_adulto}€")
    if ninos > 0:
        lineas.append(f"Niño paga: {precio_nino}€")
    lineas.append("")
    lineas.append("Comprobacion:")
    lineas.append(f"  {adultos} adulto{'s' if adultos>1 else ''} x {precio_adulto}€ = {round(adultos*precio_adulto,2)}€")
    if ninos > 0:
        lineas.append(f"  {ninos} niño{'s' if ninos>1 else ''} x {precio_nino}€ = {round(ninos*precio_nino,2)}€")
    lineas.append(f"  TOTAL: {total_final}€")
    return "\n".join(lineas)

# ─── PARSEAR CON IA ──────────────────────────────────────

def parse_cuenta(text: str) -> dict | None:
    prompt = f"""Extrae los datos de esta cuenta a repartir entre personas.
Texto: "{text}"
Responde SOLO con JSON sin markdown:
{{"total": numero_decimal, "adultos": numero_entero, "ninos": numero_o_0, "propina_pct": numero_o_0, "valido": true}}
- Si no hay niños: ninos = 0
- Si no hay propina: propina_pct = 0
- Si falta el total o los adultos: valido = false
- "dos adultos y un niño" → adultos: 2, ninos: 1"""
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200
            },
            timeout=15
        )
        raw = r.json()["choices"][0]["message"]["content"].strip()
        raw = raw.replace('```json','').replace('```','').strip()
        data = json.loads(raw)
        return data if data.get('valido') else None
    except Exception as e:
        logger.error(f"Error parseando: {e}")
        return None

# ─── TRANSCRIBIR AUDIO ───────────────────────────────────

async def transcribir(bot, file_id: str) -> str | None:
    try:
        file = await bot.get_file(file_id)
        file_bytes = await file.download_as_bytearray()
        r = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            files={"file": ("audio.ogg", bytes(file_bytes), "audio/ogg")},
            data={"model": "whisper-large-v3", "language": "es"},
            timeout=30
        )
        return r.json().get("text", "").strip()
    except Exception as e:
        logger.error(f"Error transcribiendo: {e}")
        return None

# ─── PROCESAR TEXTO ──────────────────────────────────────

async def procesar(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    datos = parse_cuenta(text)
    if not datos:
        await update.message.reply_text(
            "No entendi. Dime asi:\n\n"
            "120 euros, 4 adultos y 2 ninos\n"
            "85 euros entre 3 adultos\n"
            "95 euros, 2 adultos, 1 nino, propina 10%"
        )
        return
    resultado = calcular(
        total=float(datos['total']),
        adultos=int(datos['adultos']),
        ninos=int(datos.get('ninos', 0)),
        propina_pct=float(datos.get('propina_pct', 0))
    )
    await update.message.reply_text(resultado)

# ─── HANDLERS ────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola! Soy Calculin.\n\n"
        "Dimelo por voz o texto:\n"
        "- 120 euros, 4 adultos y 2 ninos\n"
        "- 85 euros entre 3 adultos\n"
        "- 95 euros, 2 adultos, 1 nino, propina 10%\n\n"
        "Los ninos pagan la mitad que un adulto."
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    await context.bot.send_chat_action(update.effective_chat.id, 'typing')
    await procesar(update, context, update.message.text)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = update.message.voice or update.message.audio
    if not voice:
        return
    await context.bot.send_chat_action(update.effective_chat.id, 'typing')
    transcription = await transcribir(context.bot, voice.file_id)
    if not transcription:
        await update.message.reply_text("No pude escucharte. Intentalo de nuevo.")
        return
    await update.message.reply_text(f"Escuche: {transcription}")
    await procesar(update, context, transcription)

# ─── MAIN ────────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    logger.info("Calculin bot arrancado!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
