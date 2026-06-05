# agents/calculin.py
"""
Agente Calculín — integrado en el bot maestro.
Maneja mensajes enrutados desde main.py con "calculin" como dominio.
"""
import os, requests, json, logging

logger = logging.getLogger(__name__)
GROQ_KEY = os.environ.get('GROQ_API_KEY', '')

def calcular(total: float, adultos: int, ninos: int = 0, propina_pct: float = 0) -> str:
    propina = round(total * propina_pct / 100, 2)
    total_final = round(total + propina, 2)
    partes = adultos + ninos * 0.5
    precio_adulto = round(total_final / partes, 2)
    precio_nino = round(precio_adulto / 2, 2)

    lineas = [f"🧮 *Calculín*\n"]
    lineas.append(f"Cuenta: {total}€")
    if propina_pct > 0:
        lineas.append(f"Propina {propina_pct}%: +{propina}€")
        lineas.append(f"Total con propina: {total_final}€")
    lineas.append("")
    lineas.append(f"👤 Adulto paga: *{precio_adulto}€*")
    if ninos > 0:
        lineas.append(f"🧒 Niño paga: *{precio_nino}€*")
    lineas.append("")
    lineas.append("📊 Comprobación:")
    lineas.append(f"  {adultos} adulto{'s' if adultos>1 else ''} × {precio_adulto}€ = {round(adultos*precio_adulto,2)}€")
    if ninos > 0:
        lineas.append(f"  {ninos} niño{'s' if ninos>1 else ''} × {precio_nino}€ = {round(ninos*precio_nino,2)}€")
    lineas.append(f"  ✅ TOTAL: {total_final}€")
    return "\n".join(lineas)

def parse_cuenta(text: str) -> dict | None:
    prompt = f"""Extrae los datos de esta cuenta a repartir.
Texto: "{text}"
Responde SOLO con JSON sin markdown:
{{"total": numero_decimal, "adultos": numero_entero, "ninos": numero_o_0, "propina_pct": numero_o_0, "valido": true}}
- Si no hay niños: ninos = 0
- Si no hay propina: propina_pct = 0
- Si falta el total o los adultos: valido = false
- Los niños pagan la mitad que un adulto"""
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
        logger.error(f"Calculin parse error: {e}")
        return None

async def handle(text: str) -> str:
    datos = parse_cuenta(text)
    if not datos:
        return (
            "No entendí bien. Dímelo así:\n\n"
            "• 88,75 euros, 6 adultos y 3 niños\n"
            "• 120 euros entre 4 adultos\n"
            "• 95 euros, 2 adultos, 1 niño, propina 10%"
        )
    return calcular(
        total=float(datos['total']),
        adultos=int(datos['adultos']),
        ninos=int(datos.get('ninos', 0)),
        propina_pct=float(datos.get('propina_pct', 0))
    )
