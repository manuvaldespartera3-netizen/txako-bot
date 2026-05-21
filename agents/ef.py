"""
Agente Educación Física.
Busca en el repositorio de PDFs de Google Drive antes de generar respuestas.
Si no encuentra material relevante, genera con su conocimiento pero lo indica.
"""
import logging, json
import google.generativeai as genai
import config

logger = logging.getLogger(__name__)
model = genai.GenerativeModel('gemini-1.5-flash')

SYSTEM_PROMPT = """Eres el asistente de Educación Física de Txako, especialista en primaria.
Trabajas principalmente con alumnos de 1º y 2º de primaria (6-8 años) pero conoces toda la etapa.

Cuando sugieres actividades o juegos:
- Da SIEMPRE opciones REALES y concretas, no genéricas
- Especifica: nombre del juego, organización del espacio, reglas en 3 líneas, variantes
- Adapta al material disponible si te lo dicen
- Adapta a las condiciones (lluvia, espacio reducido, sin material, etc.)
- Indica el objetivo motriz principal de cada actividad

Si tienes material del repositorio del usuario, úsalo primero y cítalo.
Si generas de tu propio conocimiento, indícalo con: "(De mi base de conocimiento)"
"""

# ─── ACCESO AL REPOSITORIO ────────────────────────────────

async def search_repository(query: str) -> list[dict]:
    """
    Busca en Google Drive la carpeta 'Repositorio EF' y devuelve
    fragmentos relevantes de los PDFs encontrados.
    NOTA: Esta función se activa cuando el usuario sube su primer PDF.
    Por ahora devuelve lista vacía si no hay repositorio.
    """
    # TODO: Implementar con Google Drive API cuando Txako suba material
    # Por ahora el bot funciona con conocimiento propio
    return []

# ─── HANDLER PRINCIPAL ────────────────────────────────────

async def handle(text: str) -> str:
    """Procesa consulta de EF, buscando en repositorio primero."""

    # Buscar en repositorio (cuando exista)
    repo_results = await search_repository(text)
    repo_context = ""
    if repo_results:
        repo_context = "\n\nMATERIAL DEL REPOSITORIO PERSONAL DE TXAKO:\n"
        for r in repo_results:
            repo_context += f"\n[{r.get('source','')}]\n{r.get('content','')}\n"

    prompt = (
        SYSTEM_PROMPT
        + repo_context
        + f"\n\nConsulta de Txako: {text}"
        + "\n\nResponde de forma estructurada y práctica."
    )

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        logger.error(f"Error agente EF: {e}")
        return f"❌ Error: {e}"


async def handle_add_material(file_content: bytes, filename: str) -> str:
    """
    Procesa un PDF enviado al bot y lo añade al repositorio.
    Se activa cuando Txako manda un PDF al chat de EF.
    """
    # TODO: Subir a Google Drive carpeta 'Repositorio EF'
    # y generar embeddings o summary para búsqueda futura
    return (
        f"📄 *{filename}* recibido.\n"
        "Cuando conectemos el repositorio a Drive, lo añadiré automáticamente.\n"
        "Por ahora, ¿quieres que lo analice y te diga qué contiene?"
    )
