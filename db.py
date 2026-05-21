"""
Capa de base de datos. Todo lo que necesita persistencia va aquí.
"""
from supabase import create_client, Client
import config, logging

logger = logging.getLogger(__name__)
db: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

# ─── CANALES DE RESPUESTA ─────────────────────────────────

def save_channel(domain: str, chat_id: int):
    """Guarda o actualiza el chat_id de un dominio."""
    db.table('channels').upsert({
        'domain': domain,
        'chat_id': chat_id
    }, on_conflict='domain').execute()

def get_channel_ids() -> dict:
    """Devuelve {domain: chat_id} para todos los dominios configurados."""
    try:
        result = db.table('channels').select('domain, chat_id').execute()
        return {r['domain']: r['chat_id'] for r in (result.data or [])}
    except Exception as e:
        logger.error(f"Error obteniendo canales: {e}")
        return {}

# ─── RECORDATORIOS ────────────────────────────────────────

def save_reminder(chat_id: int, descripcion: str, fecha_hora: str) -> bool:
    """fecha_hora en formato ISO."""
    try:
        db.table('recordatorios').insert({
            'chat_id': chat_id,
            'descripcion': descripcion,
            'fecha_hora': fecha_hora,
            'enviado': False
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Error guardando recordatorio: {e}")
        return False

def get_pending_reminders() -> list:
    from datetime import datetime
    import pytz
    now = datetime.now(pytz.timezone('Europe/Madrid')).isoformat()
    try:
        result = db.table('recordatorios')\
            .select('*')\
            .eq('enviado', False)\
            .lte('fecha_hora', now)\
            .execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Error recordatorios pendientes: {e}")
        return []

def mark_reminder_sent(rid: int):
    db.table('recordatorios').update({'enviado': True}).eq('id', rid).execute()

def get_future_reminders(chat_id: int) -> list:
    from datetime import datetime
    import pytz
    now = datetime.now(pytz.timezone('Europe/Madrid')).isoformat()
    try:
        result = db.table('recordatorios')\
            .select('*')\
            .eq('chat_id', chat_id)\
            .eq('enviado', False)\
            .gte('fecha_hora', now)\
            .order('fecha_hora')\
            .execute()
        return result.data or []
    except Exception:
        return []
