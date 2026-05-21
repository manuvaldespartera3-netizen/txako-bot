"""
Agente Calculín.
Calculadora de cuentas compartidas. Sin IA, matemáticas puras.
Adultos pagan precio completo, niños pagan mitad.
"""
import re, logging
import gemini

logger = logging.getLogger(__name__)

def parse_cuenta(text: str) -> dict | None:
    """
    Intenta extraer del texto: total, adultos, niños, propina.
    Usa IA solo para entender el lenguaje natural, los cálculos son matemáticos.
    """
    prompt = f"""Extrae los datos de esta cuenta a repartir.
Texto: "{text}"

Responde SOLO con JSON sin markdown:
{{
  "total": numero_decimal,
  "adultos": numero_entero,
  "ninos": numero_entero_o_0,
  "propina_pct": numero_o_0,
  "valido": true
}}

- Si no hay niños → ninos: 0
- Si no hay propina → propina_pct: 0
- Si falta el total o los adultos → valido: false
- "dos adultos y un niño" → adultos: 2, ninos: 1
- propina "10%" → propina_pct: 10
"""
    try:
        raw = gemini.ask(prompt).strip().replace('```json','').replace('```','').strip()
        import json
        data = json.loads(raw)
        return data if data.get('valido') else None
    except Exception as e:
        logger.error(f"Error parseando cuenta: {e}")
        return None

def calcular(total: float, adultos: int, ninos: int, propina_pct: float = 0) -> str:
    """Cálculo matemático puro. Sin IA."""
    
    # Aplicar propina
    propina = round(total * propina_pct / 100, 2)
    total_con_propina = round(total + propina, 2)
    
    # Cada niño cuenta como medio adulto
    # Total partes = adultos + ninos*0.5
    partes = adultos + ninos * 0.5
    precio_adulto = round(total_con_propina / partes, 2)
    precio_nino = round(precio_adulto / 2, 2)
    
    # Verificación — sumatorio
    suma = round(adultos * precio_adulto + ninos * precio_nino, 2)
    # Ajustar posible diferencia de céntimos en el último adulto
    diferencia = round(total_con_propina - suma, 2)
    
    # Construir respuesta
    lineas = ["🧮 *Calculín*\n"]
    
    lineas.append(f"💶 Total cuenta: {total}€")
    if propina_pct > 0:
        lineas.append(f"   + Propina {propina_pct}%: {propina}€")
        lineas.append(f"   = Total con propina: {total_con_propina}€")
    
    lineas.append(f"\n👤 Adulto paga: *{precio_adulto}€*")
    lineas.append(f"👶 Niño paga: *{precio_nino}€*")
    
    # Sumatorio para los desconfiados
    lineas.append(f"\n✅ Comprobación:")
    lineas.append(f"   {adultos} adulto{'s' if adultos>1 else ''} × {precio_adulto}€ = {round(adultos*precio_adulto,2)}€")
    if ninos > 0:
        lineas.append(f"   {ninos} niño{'s' if ninos>1 else ''} × {precio_nino}€ = {round(ninos*precio_nino,2)}€")
    lineas.append(f"   Total: {total_con_propina}€ ✓")
    
    return "\n".join(lineas)

async def handle(text: str) -> str:
    text_lower = text.lower()
    
    # Ayuda
    if any(k in text_lower for k in ['ayuda','cómo','como funciona','help']):
        return (
            "🧮 *Calculín — Cómo usarme*\n\n"
            "Dime el total, cuántos adultos y cuántos niños.\n\n"
            "Ejemplos:\n"
            "• _120 euros, 4 adultos y 2 niños_\n"
            "• _La cuenta es 85€, somos 3 adultos_\n"
            "• _95 euros, 2 adultos, 1 niño, propina 10%_\n\n"
            "Los niños pagan la mitad que un adulto."
        )
    
    # Parsear con IA
    datos = await parse_cuenta(text)
    
    if not datos:
        return (
            "No entendí bien la cuenta. Dímelo así:\n\n"
            "_120 euros, 4 adultos y 2 niños_\n"
            "_85€, somos 3 adultos_"
        )
    
    # Calcular con matemáticas puras
    return calcular(
        total=float(datos['total']),
        adultos=int(datos['adultos']),
        ninos=int(datos.get('ninos', 0)),
        propina_pct=float(datos.get('propina_pct', 0))
    )
