"""
Módulo de tiempo — Bot Txako
- Avisos automáticos a las 9, 11, 14, 18 y 21h
- Previsión de lluvia próximas horas
- Consulta libre por comando o audio
"""

import os
import requests
from datetime import datetime, timezone, timedelta

WEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
BASE_URL        = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL    = "https://api.openweathermap.org/data/2.5/forecast"

# Ciudad por defecto — se actualiza con /ciudad o por audio
ciudad_activa = "Zaragoza"

def get_ciudad():
    global ciudad_activa
    return ciudad_activa

def set_ciudad(nueva: str):
    global ciudad_activa
    ciudad_activa = nueva


# ─── Emojis ───────────────────────────────────────────────────
ICONOS = {
    "clear sky": "☀️",
    "few clouds": "🌤️",
    "scattered clouds": "⛅",
    "broken clouds": "🌥️",
    "overcast clouds": "☁️",
    "light rain": "🌦️",
    "moderate rain": "🌧️",
    "heavy intensity rain": "⛈️",
    "thunderstorm": "⛈️",
    "snow": "❄️",
    "mist": "🌫️",
    "fog": "🌫️",
    "drizzle": "🌦️",
    "haze": "🌫️",
}

def icono_tiempo(descripcion: str) -> str:
    for clave, emoji in ICONOS.items():
        if clave in descripcion.lower():
            return emoji
    return "🌡️"


# ─── Tiempo actual ─────────────────────────────────────────────
def obtener_tiempo(ciudad: str) -> dict | None:
    try:
        resp = requests.get(BASE_URL, params={
            "q": ciudad,
            "appid": WEATHER_API_KEY,
            "units": "metric",
            "lang": "es"
        }, timeout=10)
        if resp.status_code != 200:
            return None
        d = resp.json()
        return {
            "ciudad":      d["name"],
            "temp":        round(d["main"]["temp"]),
            "sensacion":   round(d["main"]["feels_like"]),
            "humedad":     d["main"]["humidity"],
            "viento":      round(d["wind"]["speed"] * 3.6),
            "descripcion": d["weather"][0]["description"].capitalize(),
            "icono":       icono_tiempo(d["weather"][0]["description"]),
        }
    except Exception as e:
        print(f"[tiempo] Error tiempo actual: {e}")
        return None


# ─── Previsión de lluvia próximas horas ────────────────────────
def prevision_lluvia(ciudad: str) -> str:
    """
    Consulta el forecast y devuelve una línea sobre lluvia
    en las próximas ~9 horas (3 franjas de 3h).
    """
    try:
        resp = requests.get(FORECAST_URL, params={
            "q": ciudad,
            "appid": WEATHER_API_KEY,
            "units": "metric",
            "lang": "es",
            "cnt": 3          # próximas 3 franjas = ~9 horas
        }, timeout=10)
        if resp.status_code != 200:
            return ""

        franjas = resp.json().get("list", [])
        horas_lluvia = []

        for franja in franjas:
            lluvia = franja.get("rain", {}).get("3h", 0)
            if lluvia > 0.2:   # más de 0.2 mm se considera lluvia real
                dt = datetime.fromtimestamp(franja["dt"], tz=timezone.utc)
                hora_local = dt + timedelta(hours=2)  # CEST (verano España)
                horas_lluvia.append(hora_local.strftime("%H:%M"))

        if horas_lluvia:
            horas_str = ", ".join(horas_lluvia)
            return f"🌧️ _Lluvia prevista hacia las {horas_str}h_"
        else:
            return "✅ _Sin lluvia prevista en las próximas horas_"

    except Exception as e:
        print(f"[tiempo] Error forecast: {e}")
        return ""


# ─── Mensaje formateado ────────────────────────────────────────
def formato_mensaje(ciudad: str, hora_label: str = None) -> str:
    datos = obtener_tiempo(ciudad)
    if not datos:
        return f"⚠️ No pude obtener el tiempo para *{ciudad}*. Comprueba el nombre."

    lluvia = prevision_lluvia(ciudad)

    cabecera = (
        f"{datos['icono']} *Tiempo en {datos['ciudad']}*"
        + (f" · {hora_label}h" if hora_label else "")
    )
    cuerpo = (
        f"🌡 {datos['temp']}°C · Sensación {datos['sensacion']}°C\n"
        f"💧 Humedad {datos['humedad']}% · 🌬 Viento {datos['viento']} km/h\n"
        f"_{datos['descripcion']}_"
    )
    return f"{cabecera}\n{cuerpo}\n{lluvia}" if lluvia else f"{cabecera}\n{cuerpo}"
