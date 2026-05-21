import os

# ─── TELEGRAM ─────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
MY_CHAT_ID     = int(os.environ['MY_CHAT_ID'])

# ─── IA ───────────────────────────────────────────────────
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']

# ─── SUPABASE ─────────────────────────────────────────────
SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_KEY']

# ─── GOOGLE SHEETS (opcional, se añade más adelante) ──────
GOOGLE_CREDENTIALS = os.environ.get('GOOGLE_CREDENTIALS', '')
SHEETS_ID          = os.environ.get('SHEETS_ID', '')

# ─── DOMINIOS ─────────────────────────────────────────────
DOMAINS = ['ef', 'tutoria', 'recordatorios', 'racing', 'gastos', 'general']
