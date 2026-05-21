import os

# ─── TELEGRAM ─────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
MY_CHAT_ID     = int(os.environ['MY_CHAT_ID'])   # chat donde TÚ escribes

# IDs de los 4 chats de respuesta (se configuran con /setup)
# Se guardan en Supabase, no aquí. Ver db.py → get_channel_ids()

# ─── IA ───────────────────────────────────────────────────
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']

# ─── SUPABASE ─────────────────────────────────────────────
SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_KEY']

# ─── GOOGLE SHEETS ────────────────────────────────────────
GOOGLE_CREDENTIALS = os.environ['GOOGLE_CREDENTIALS']  # JSON completo como string
SHEETS_ID          = os.environ['SHEETS_ID']           # ID del Google Sheet

# ─── DOMINIOS ─────────────────────────────────────────────
DOMAINS = ['ef', 'tutoria', 'recordatorios', 'racing', 'gastos', 'general']
