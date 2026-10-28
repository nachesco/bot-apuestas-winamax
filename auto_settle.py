import os
import sys
from database import actualizar_resultado_apuesta, obtener_apuestas_pendientes
from dotenv import load_dotenv
import requests
from telegram_notifier import enviar_alerta_telegram

# Configurar salida UTF-8 en consola de Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
SPORT = "basketball_nba"


def obtener_resultados_nba(days_from=3):
    """Consulta los marcadores finales de los partidos a través de The Odds API."""
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/scores"
    params = {"apiKey": ODDS_API_KEY, "daysFrom": days_from}
    try:
        response = requests.get(url, params=params)
        if response.status_code != 200:
            print(
                f"❌ Error al obtener marcadores de la API: {response.status_code}"
            )
            return []
        return response.json()
    except Exception as e:
        print(f"❌ Excepción al conectar con la API de marcadores: {e}")
        return []


def procesar_apuestas_pendientes():
    apuestas_pendientes = obtener_apuestas_pendientes()
    if not apuestas_pendientes:
        print("💤 No hay apuestas pendientes por resolver en la base de datos.")
        return

    print(f"🔍 Evaluando {len(apuestas_pendientes)} apuestas pendientes...")
    partidos_api = obtener_resultados_nba(days_from=3)

    # Crear un mapa de resultados para los partidos finalizados
    resultados_map = {}
    for p in partidos_api:
        if not p.get("completed"):
            continue

        eq_local = p["home_team"]
        eq_vis = p["away_team"]
        key_partido = f"{eq_local} vs {eq_vis}"

        scores = p.get("scores")
        if not scores or len(scores) < 2:
            continue

        # Extraer puntos de cada equipo
        pts_local = next(
            (int(s["score"]) for s in scores if s["name"] == eq_local), None
        )
        pts_vis = next(
            (int(s["score"]) for s in scores if s["name"] == eq_vis), None
        )

        if pts_local is not None and pts_vis is not None:
            ganador = eq_local if pts_local > pts_vis else eq_vis
            resultados_map[key_partido] = {
                "ganador": ganador,
                "marcador": f"{eq_local} {pts_local} - {pts_vis} {eq_vis}",
            }

    liquidadas = 0
    for id_apuesta, id_partido, seleccion, cuota, stake in apuestas_pendientes:
        if id_partido in resultados_map:
            res = resultados_map[id_partido]
            ganador_real = res["ganador"]
            marcador = res["marcador"]

            # Extraer el equipo apostado (ej: "Detroit Pistons en onexbet" -> "Detroit Pistons")
            equipo_apostado = seleccion.split(" en ")[0].strip()

            if equipo_apostado == ganador_real:
                estado = "GANADA"
                ganancia = stake * (cuota - 1)
                icono = "✅"
            else:
                estado = "PERDIDA"
                ganancia = -stake
                icono = "❌"

            # Actualizar base de datos y bankroll
            actualizar_resultado_apuesta(id_apuesta, estado, ganancia)
            liquidadas += 1

            mensaje_telegram = (
                f"{icono} <b>APUESTA LIQUIDADA: {estado}</b>\n\n"
                f"<b>Partido:</b> {id_partido}\n"
                f"<b>Marcador Final:</b> {marcador}\n"
                f"<b>Tu Selección:</b> {equipo_apostado} @ {cuota}\n"
                f"<b>Stake:</b> {stake:.2f} €\n"
                f"<b>Beneficio/Pérdida:</b> {ganancia:+.2f} €"
            )

            print(
                f"✨ Apuesta #{id_apuesta} [{id_partido}] resuelta: {estado} ({ganancia:+.2f}€)"
            )
            enviar_alerta_telegram(mensaje_telegram)

    if liquidadas == 0:
        print("⏳ Ninguno de los partidos pendientes ha finalizado todavía.")


if __name__ == "__main__":
    procesar_apuestas_pendientes()