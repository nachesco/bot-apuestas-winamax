import os
import requests
from dotenv import load_dotenv
from database import obtener_conexion, obtener_saldo_actual

load_dotenv()
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
SPORT = 'basketball_nba'

def resolver_apuestas():
    """Consulta los marcadores finales de los partidos y actualiza las apuestas pendientes."""
    if not ODDS_API_KEY:
        print("❌ ERROR: Falta la API Key de The Odds API en .env")
        return

    conn = obtener_conexion()
    cursor = conn.cursor()
    
    # 1. Obtener apuestas pendientes
    cursor.execute("SELECT * FROM apuestas WHERE estado = 'PENDIENTE'")
    apuestas_pendientes = cursor.fetchall()

    if not apuestas_pendientes:
        print("💤 No hay apuestas pendientes por resolver en este momento.")
        conn.close()
        return

    print(f"🔍 Evaluando {len(apuestas_pendientes)} apuestas pendientes...")

    # 2. Consultar partidos finalizados a la API
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/scores"
    params = {
        "apiKey": ODDS_API_KEY,
        "daysFrom": 3
    }

    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        print(f"❌ Error al consultar resultados: {resp.status_code}")
        conn.close()
        return

    partidos = resp.json()
    
    # Mapear los partidos finalizados
    resultados = {}
    for p in partidos:
        if p.get("completed") and p.get("scores"):
            home = p["home_team"]
            away = p["away_team"]
            partido_id = f"{home} vs {away}"
            
            scores = {s["name"]: int(s["score"]) for s in p["scores"]}
            ganador = max(scores, key=scores.get) if len(scores) == 2 else None
            resultados[partido_id] = ganador

    saldo_actual = obtener_saldo_actual()

    # 3. Comparar apuestas con los resultados reales
    for ap in apuestas_pendientes:
        partido = ap["partido"]
        # Extraer el nombre del equipo quitando la casa de apuestas
        seleccion_equipo = ap["seleccion"].split(" en ")[0].strip()
        cuota = ap["cuota"]
        stake = ap["stake"]
        ap_id = ap["id"]

        if partido in resultados:
            ganador_real = resultados[partido]
            if ganador_real == seleccion_equipo:
                estado = "GANADA"
                pnl = stake * (cuota - 1)
                nuevo_saldo = saldo_actual + pnl
                print(f"✅ APUESTA GANADA (#{ap_id}): {partido} -> {seleccion_equipo} (+{pnl:.2f} €)")
            else:
                estado = "PERDIDA"
                pnl = -stake
                nuevo_saldo = saldo_actual + pnl
                print(f"❌ APUESTA PERDIDA (#{ap_id}): {partido} -> {seleccion_equipo} ({pnl:.2f} €)")

            # Actualizar estado de la apuesta
            cursor.execute("UPDATE apuestas SET estado = ?, pnl = ? WHERE id = ?", (estado, pnl, ap_id))

            # Insertar nuevo registro de bankroll
            cursor.execute("INSERT INTO bankroll (saldo) VALUES (?)", (nuevo_saldo,))
            saldo_actual = nuevo_saldo

    conn.commit()
    conn.close()
    print("✅ Proceso de resolución completado.")

if __name__ == "__main__":
    resolver_apuestas()