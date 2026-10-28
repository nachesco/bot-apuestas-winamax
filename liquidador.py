from datetime import datetime
import os
import sqlite3
import sys
import requests

if sys.platform == "win32":
  sys.stdout.reconfigure(encoding="utf-8")
  sys.stderr.reconfigure(encoding="utf-8")

# --- CONFIGURACIONES ---
DB_PATH = "apuestas.db"
LOG_LIQ = "logs_liquidador.txt"
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "TU_API_KEY_AQUI")
SPORT = "basketball_nba"


def actualizar_log(mensaje):
  """Escribe el registro de ejecución del liquidador."""
  with open(LOG_LIQ, "w", encoding="utf-8") as f:
    f.write(
        f"Última ejecución del liquidador: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{mensaje}"
    )


def obtener_marcadores_api():
  """Consulta los resultados de los partidos finalizados en The Odds API.

  Se usa daysFrom=3 (entero) para cumplir con las especificaciones del
  endpoint.
  """
  if ODDS_API_KEY == "TU_API_KEY_AQUI":
    print("⚠️ ADVERTENCIA: No se ha configurado la API Key de The Odds API.")
    return []

  url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/scores/"
  params = {
      "apiKey": ODDS_API_KEY,
      "daysFrom": 3,  # Corregido: Valor entero entre 1 y 3 aceptado por la API
  }

  try:
    response = requests.get(url, params=params, timeout=10)
    if response.status_code == 200:
      return response.json()
    else:
      print(
          f"❌ Error al consultar marcadores ({response.status_code}):"
          f" {response.text}"
      )
      return []
  except Exception as e:
    print(f"❌ Excepción conectando con la API de marcadores: {e}")
    return []


def liquidar_apuestas():
  print(
      f"🔍 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Iniciando proceso"
      " de liquidación de apuestas..."
  )

  if not os.path.exists(DB_PATH):
    print("❌ No existe la base de datos apuestas.db.")
    return

  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  # Obtener apuestas con estado PENDIENTE
  cursor.execute(
      "SELECT id, id_partido, seleccion, cuota, stake FROM apuestas WHERE"
      " estado = 'PENDIENTE'"
  )
  apuestas_pendientes = cursor.fetchall()

  if not apuestas_pendientes:
    print("ℹ️ No hay apuestas pendientes por liquidador.")
    actualizar_log("No había apuestas pendientes.")
    conn.close()
    return

  print(
      f"📋 Evaluando {len(apuestas_pendientes)} apuestas pendientes en base de"
      " datos..."
  )

  # Consultar marcadores oficiales desde The Odds API
  partidos_scores = obtener_marcadores_api()

  if not partidos_scores:
    print(
        "⚠️ No se obtuvieron marcadores de la API (partidos no finalizados o"
        " error de respuesta)."
    )
    conn.close()
    return

  # Mapa para buscar marcadores finalizados por ID y por combinación de equipos
  mapa_partidos = {}
  for p in partidos_scores:
    if p.get("completed", False):
      scores = p.get("scores")
      if scores and len(scores) >= 2:
        home_team = p.get("home_team")
        away_team = p.get("away_team")

        # Convertir marcadores a enteros
        puntos_home = None
        puntos_away = None
        for s in scores:
          if s.get("name") == home_team:
            puntos_home = int(s.get("score"))
          elif s.get("name") == away_team:
            puntos_away = int(s.get("score"))

        if puntos_home is not None and puntos_away is not None:
          info_partido = {
              "home_team": home_team,
              "away_team": away_team,
              "pts_home": puntos_home,
              "pts_away": puntos_away,
              "totales": puntos_home + puntos_away,
          }
          # Indexar por ID
          mapa_partidos[p.get("id")] = info_partido
          # Indexar por nombre de equipos para mayor seguridad
          clave_equipos = f"{home_team}_vs_{away_team}".lower()
          mapa_partidos[clave_equipos] = info_partido

  liquidadas = 0

  for ap in apuestas_pendientes:
    ap_id, id_partido, seleccion, cuota, stake = ap

    partido_info = mapa_partidos.get(id_partido)

    # Si no se encontró por ID, intentar buscar por texto en la selección
    if not partido_info:
      for k, info in mapa_partidos.items():
        if (
            info["home_team"].lower() in seleccion.lower()
            or info["away_team"].lower() in seleccion.lower()
        ):
          partido_info = info
          break

    if not partido_info:
      continue

    # Evaluación de la selección
    ganada = False
    es_resoluble = False

    # 1. Apuestas a Ganador (H2H)
    if "Ganador:" in seleccion or "Ganador Local" in seleccion:
      es_resoluble = True
      if partido_info["pts_home"] > partido_info["pts_away"]:
        equipo_ganador = partido_info["home_team"]
      else:
        equipo_ganador = partido_info["away_team"]

      if equipo_ganador.lower() in seleccion.lower():
        ganada = True

    # 2. Apuestas a Totales (Over/Under)
    elif "Totales Puntos:" in seleccion:
      es_resoluble = True
      puntos_reales = partido_info["totales"]

      if "Over" in seleccion:
        linea = float(seleccion.split("Over ")[-1])
        if puntos_reales > linea:
          ganada = True
      elif "Under" in seleccion:
        linea = float(seleccion.split("Under ")[-1])
        if puntos_reales < linea:
          ganada = True

    # Actualizar BD si el evento concluyó y se pudo evaluar
    if es_resoluble:
      nuevo_estado = "GANADA" if ganada else "PERDIDA"
      pnl = round((stake * cuota) - stake, 2) if ganada else -round(stake, 2)

      cursor.execute(
          """
                UPDATE apuestas 
                SET estado = ?, resultado = ?, pnl = ? 
                WHERE id = ?
            """,
          (
              nuevo_estado,
              f"{partido_info['pts_home']}-{partido_info['pts_away']}",
              pnl,
              ap_id,
          ),
      )
      conn.commit()
      liquidadas += 1
      print(
          f"✅ Apuesta #{ap_id} liquidada: {nuevo_estado} | P&L: {pnl:+.2f} €"
          f" | Resultado: {partido_info['pts_home']}-{partido_info['pts_away']}"
      )

  conn.close()
  msg_final = f"Se liquidaron {liquidadas} apuestas exitosamente."
  actualizar_log(msg_final)
  print(f"🏁 {msg_final}")


if __name__ == "__main__":
  liquidar_apuestas()