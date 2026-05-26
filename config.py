import os

# ─── TELEGRAM ─────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
MY_CHAT_ID     = int(os.environ['MY_CHAT_ID'])

# ─── IA ───────────────────────────────────────────────────
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']

# ─── SUPABASE ─────────────────────────────────────────────
SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_KEY']

# ─── GOOGLE SHEETS ────────────────────────────────────────
GOOGLE_CREDENTIALS = os.environ.get('GOOGLE_CREDENTIALS', '')
SHEETS_ID          = os.environ.get('GOOGLE_SHEET_ID', '')

# ─── DOMINIOS ─────────────────────────────────────────────
DOMAINS = ['ef', 'tutoria', 'recordatorios', 'racing', 'gastos', 'calculin', 'blasa', 'general']

# ─── CANALES DE RESPUESTA ─────────────────────────────────
import os as _os
CANALES = {
    'gastos':        int(_os.environ.get('CANAL_GASTOS', 0) or 0),
    'ef':            int(_os.environ.get('CANAL_EF', 0) or 0),
    'tutoria':       int(_os.environ.get('CANAL_TUTORIA', 0) or 0),
    'recordatorios': int(_os.environ.get('CANAL_RECORDATORIOS', 0) or 0),
    'racing':        int(_os.environ.get('CANAL_RACING', 0) or 0),
    'calculin':      int(_os.environ.get('CANAL_CALCULIN', 0) or 0),
    'blasa':         int(_os.environ.get('CANAL_BLASA', 0) or 0),
    'general':       int(_os.environ.get('CANAL_GENERAL', 0) or 0),
}
