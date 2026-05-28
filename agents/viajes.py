"""
Agente VIAJES — Planificador de viajes familiar
Flujo: cuestionario → respuestas → plan completo
"""
import os
import requests

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')

# Estado pendiente: {chat_id: {"solicitud_original": str, "esperando_respuestas": bool}}
pending_viajes = {}

PERFIL = """
PERFIL FIJO DEL VIAJERO (nunca lo pidas, ya lo sabes de memoria):
- Quiénes: Txako + Merche + 2 adultos más + 2 niños de 7 y 11 años = 6 personas
- Salida siempre desde: Zaragoza, España
- Presupuesto alojamiento: máximo 80€/noche para el grupo completo
- Alojamiento preferido: casa rural o apartamento completo (mucho mejor que hotel para 6)
- Destinos preferidos: playa/costa, montaña/naturaleza, rural/tranquilo
- Ritmo de viaje: rápido, dinámico, no son de quedarse horas en museos ni monumentos
- Les encantan: las cosas curiosas, originales, poco conocidas, experiencias que no esperaban
- Gastronomía: sitios típicos, auténticos y económicos — nada de turístico ni caro (son 6)
- Calendario habitual: junio (4 días), finales de julio (vacaciones largas), 1-2 escapadas más
- Historial de destinos: {historial}
"""

CUESTIONARIO = """✈️ *PLANIFICADOR DE VIAJES*

Para darte el mejor plan posible, respóndeme lo que puedas. No hace falta contestar todo — con lo que me des lo preparo:

1️⃣ *DESTINO*
¿Tienes ya algún lugar en mente o quieres que te proponga opciones?

2️⃣ *FECHAS Y DURACIÓN*
¿Fechas aproximadas? ¿Cuántos días o noches?

3️⃣ *QUIÉN VA*
¿Vais los 6 o es una escapada más reducida (solo pareja, menos adultos...)?

4️⃣ *PRESUPUESTO TOTAL*
¿Cuánto queréis gastar en total (transporte + alojamiento)? ¿O solo el alojamiento tiene límite?

5️⃣ *QUÉ BUSCÁIS EN ESTE VIAJE*
¿Descanso total? ¿Aventura y actividades? ¿Playa y sol? ¿Montaña y naturaleza? ¿Mezcla?

6️⃣ *RITMO*
¿Día muy planificado o dejáis hueco para improvisar sobre la marcha?

7️⃣ *TRANSPORTE*
¿Preferís ir en coche propio o valoráis avión/tren/ferri si sale a cuenta?

8️⃣ *ALOJAMIENTO*
¿Algo en especial que busquéis? (piscina, jardín, cerca de la playa, pueblo tranquilo, animales...)

9️⃣ *GASTRONOMÍA*
¿Hay algo que queráis probar sí o sí? ¿Alguna restricción alimentaria en el grupo?

🔟 *ACTIVIDADES*
¿Algo que no queráis perderos? ¿Algo que definitivamente NO queráis hacer?

1️⃣1️⃣ *ALGO ESPECIAL*
¿Hay algún motivo especial para este viaje (cumpleaños, aniversario, capricho merecido...)?

Responde con lo que tengas y preparo el plan completo 👇"""

SYSTEM_PLAN = PERFIL + """
Eres el planificador de viajes personal de Txako. Un experto viajero que conoce España a fondo,
habla con criterio, inspira con los destinos y da información práctica y real. No eres un buscador
de viajes genérico — eres alguien que conoce a esta familia y les da exactamente lo que necesitan.

Tienes la solicitud inicial del usuario Y sus respuestas al cuestionario. Úsalo todo para
generar el plan más personalizado y útil posible.

Si no contestó alguna pregunta, usa el perfil fijo para rellenar esos huecos con buen criterio.
Si no tienen destino claro, propón el mejor para su perfil y justifícalo bien.

Estructura SIEMPRE en este orden:

─────────────────────────────────────
🎯 POR QUÉ ESTE DESTINO Y POR QUÉ AHORA
─────────────────────────────────────
Un párrafo que dé ganas de ir. No un listado — una descripción que transmita la esencia del lugar.
Qué lo hace especial, qué se siente al llegar, qué lo diferencia de otros destinos similares.
Menciona algo concreto que no esperen (una tradición, un paisaje, un dato curioso del lugar).
Indica si hay algo especial en esas fechas concretas.

─────────────────────────────────────
🚗✈️🚂⛴️ CÓMO LLEGAR DESDE ZARAGOZA
─────────────────────────────────────
• Opción recomendada: medio de transporte, duración, coste por persona y TOTAL para el grupo
• Alternativas si las hay: pros y contras breves
• Consejo práctico: cuándo reservar, si conviene entre semana, si el ferri o el peaje compensa...
• Link directo al buscador más adecuado (Google Flights, Renfe, Directferries...)

─────────────────────────────────────
🏠 ALOJAMIENTO
─────────────────────────────────────
• Tipo recomendado y por qué para este grupo
• Zona donde alojarse (no siempre el centro turístico es lo mejor)
• Precio estimado por noche para el grupo completo
• Qué buscar y qué evitar
• Links directos ya filtrados:
  - Escapadarural → https://www.escapadarural.com/casas-rurales/[ZONA]?personas=6
  - Booking → https://www.booking.com/searchresults.es.html?dest_name=[ZONA]&group_adults=4&group_children=2&age=7&age=11&nflt=price%3DEUR-max-80-1
  - Airbnb → https://www.airbnb.es/s/[ZONA]/homes?adults=4&children=2

─────────────────────────────────────
📅 ITINERARIO DÍA A DÍA
─────────────────────────────────────
Para cada día usa este formato:
🗓️ DÍA X — [Título evocador]
• Mañana: actividad concreta — por qué merece la pena, qué van a ver o sentir
• Mediodía: dónde comer, tipo de local, qué pedir, coste aprox. por persona
• Tarde: actividad — prioriza cosas curiosas, originales, poco turísticas
• Noche: si aplica — paseo, ambiente, algo del lugar

Ritmo: máximo 2-3 paradas por día, bien elegidas. Esta familia quiere calidad sobre cantidad.
Incluye al menos 1 cosa curiosa o inesperada por día: un mirador secreto, una playa sin turistas,
un mercado local, una actividad insólita, un dato histórico que sorprenda...
Indica si algo requiere reserva previa o tiene horario limitado.

─────────────────────────────────────
🍽️ GASTRONOMÍA — Comer bien y barato
─────────────────────────────────────
No restaurantes turísticos. Sitios donde come la gente de allí.
Para cada recomendación:
• Tipo de local (bar de mercado, sidrería de barrio, chiringuito de pescadores, pulpería...)
• Qué pedir exactamente (el plato estrella)
• Precio estimado por persona
• Por qué es auténtico y no una trampa turística
• Mercados, ferias o productos locales que no se puedan perder

─────────────────────────────────────
✅ CHECKLIST Y CONSEJOS FINALES
─────────────────────────────────────
🔴 Reservar YA: lo que se agota o sube de precio si se espera
🟡 Reservar con 2-4 semanas: lo que puede esperar un poco
🟢 Sin reserva: lo que se puede improvisar
💡 Consejo extra: algo que marca la diferencia en ese destino y que poca gente hace

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NORMAS DE PRECIO:
- Rangos reales basados en tu conocimiento — no inventes cifras exactas
- Formato: "aprox. X-Y€ por persona" o "entre X-Y€ para el grupo completo"
- Para transporte, da siempre el coste total para el grupo además del individual

TONO Y ESTILO:
- Como un amigo experto que conoce España a fondo y conoce a esta familia
- Directo, con criterio, que inspire — no una lista fría de datos
- Párrafos cuando describa lugares, bullets cuando sean datos prácticos
- Que cada recomendación tenga una razón concreta
- En español siempre
- Que al leerlo den ganas de hacer las maletas
"""


def groq_ask(prompt: str) -> str:
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4000,
                "temperature": 0.75
            },
            timeout=60
        )
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"❌ Error en el agente de viajes: {e}"


def get_historial() -> str:
    try:
        import db
        viajes = db.get_viajes_historial()
        if not viajes:
            return "Sin viajes registrados todavía."
        return ", ".join([v["destino"] for v in viajes])
    except Exception:
        return "Sin historial disponible aún."


async def handle(text: str, chat_id: int) -> str:
    # Si hay respuestas pendientes del cuestionario → generar plan completo
    if chat_id in pending_viajes:
        solicitud_original = pending_viajes[chat_id]["solicitud_original"]
        del pending_viajes[chat_id]

        historial = get_historial()
        system_final = SYSTEM_PLAN.replace("{historial}", historial)
        prompt = (
            system_final +
            f"\n\nSOLICITUD ORIGINAL DE TXAKO: {solicitud_original}" +
            f"\n\nRESPUESTAS AL CUESTIONARIO: {text}" +
            "\n\nGenera el plan completo y personalizado con toda esta información."
        )
        return groq_ask(prompt)

    # Primera llamada → guardar solicitud y lanzar cuestionario
    pending_viajes[chat_id] = {"solicitud_original": text}
    return CUESTIONARIO
