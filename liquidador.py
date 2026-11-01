from datetime import datetime
import os
import sqlite3
import sys
import time
import requests

if sys.platform == "win32":
  sys.stdout.reconfigure(encoding="utf-8")
  sys.stderr.reconfigure(encoding="utf-8")

# --- CONFIGURACIONES ---
DB_PATH = "apuestas.db"
LOG_LIQ = "logs_liquidador.txt"
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "c47d66c9ae730ebc0dee61ac3c68581e")

# Mapeo de categorías de la base de datos a los sport keys reales de The Odds API
MAPEO_DEPORTES = {
    "futbol": [
        "soccer_spain_la_liga",
        "soccer_epl",
        "soccer_italy_serie_a",
        "soccer_germany_bundesliga",
        "soccer_france_ligue_one",
        "soccer_uefa_champs_league",
    ],
    "basketball_nba": ["basketball_nba"],
    "basketball_euroleague": ["basketball_euroleague"],
    "basketball_spain_acb": ["basketball_spain_acb"],
    "basketball_italy_lega_basket": ["basketball_italy_lega_basket"],
    "basketball_germany_bbl": ["basketball_germany_bbl"],
    "basketball_ncaab": ["basketball_ncaab"],
    "baloncesto": [
        "basketball_nba",
        "basketball_euroleague",
        "basketball_spain_acb",
        "basketball_italy_lega_basket",
        "basketball_germany_bbl",
        "basketball_ncaab",
    ],
}


def actualizar_log(mensaje):
  """Escribe el registro de ejecución del liquidador evitando bloqueos de permisos."""
  intentos = 3
  for intento in range(intentos):
    try:
      with open(LOG_LIQ, "w", encoding="utf-8") as f:
        f.write(
            f"Última ejecución del liquidador:"
            f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{mensaje}"
        )
      break
    except PermissionError:
      if intento < intentos - 1:
        time.sleep(0.5)
      else:
        print(
            f"⚠️ Aviso: No se pudo actualizar {LOG_LIQ} por conflicto de"
            " permisos con otro proceso."
        )


def obtener_marcadores_api(sport_key):
  """Consulta los resultados de partidos finalizados para una competición en The Odds API."""
  url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores/"
  params = {"apiKey": ODDS_API_KEY, "daysFrom": 3}
  try:
    response = requests.get(url, params=params, timeout=10)
    if response.status_code == 200:
      return response.json()
    else:
      return []
  except Exception as e:
    print(f"❌ Excepción conectando con la API para {sport_key}: {e}")
    return []


def liquidar_apuestas():
  print(
      f"🔍 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Iniciando proceso"
      " de liquidación multi-deporte..."
  )

  if not os.path.exists(DB_PATH):
    print("❌ No existe la base de datos apuestas.db.")
    return

  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  # Obtener apuestas con estado PENDIENTE
  cursor.execute(
      "SELECT id, id_partido, deporte, seleccion, cuota, stake FROM apuestas"
      " WHERE estado = 'PENDIENTE'"
  )
  apuestas_pendientes = cursor.fetchall()

  if not apuestas_pendientes:
    print("ℹ️ No hay apuestas pendientes por liquidar.")
    actualizar_log("No había apuestas pendientes.")
    conn.close()
    return

  print(
      f"📋 Evaluando {len(apuestas_pendientes)} apuestas pendientes en base de"
      " datos..."
  )

  # Descargar marcadores de todos los deportes implicados en las apuestas pendientes
  deportes_en_bd = set(ap[2] for ap in apuestas_pendientes)
  sport_keys_a_consultar = set()
  for d in deportes_en_bd:
    if d in MAPEO_DEPORTES:
      sport_keys_a_consultar.update(MAPEO_DEPORTES[d])
    else:
      sport_keys_a_consultar.add(d)

  mapa_partidos = {}
  for sk in sport_keys_a_consultar:
    partidos_scores = obtener_marcadores_api(sk)
    for p in partidos_scores:
      if p.get("completed", False):
        scores = p.get("scores")
        if scores and len(scores) >= 2:
          home_team = p.get("home_team")
          away_team = p.get("away_team")

          puntos_home, puntos_away = None, None
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
            mapa_partidos[p.get("id")] = info_partido

  liquidadas = 0

  for ap in apuestas_pendientes:
    ap_id, id_partido, deporte, seleccion, cuota, stake = ap

    partido_info = mapa_partidos.get(id_partido)

    if not partido_info:
      for _, info in mapa_partidos.items():
        if (
            info["home_team"].lower() in seleccion.lower()
            or info["away_team"].lower() in seleccion.lower()
        ):
          partido_info = info
          break

    if not partido_info:
      continue

    ganada = False
    es_resoluble = False
    resultado_str = f"{partido_info['pts_home']}-{partido_info['pts_away']}"

    # 1. Fútbol 1X2
    if "(1)" in seleccion and not "Handicap" in seleccion:
      es_resoluble = True
      if partido_info["pts_home"] > partido_info["pts_away"]:
        ganada = True
    elif "Empate (X)" in seleccion:
      es_resoluble = True
      if partido_info["pts_home"] == partido_info["pts_away"]:
        ganada = True
    elif "(2)" in seleccion and not "Handicap" in seleccion:
      es_resoluble = True
      if partido_info["pts_away"] > partido_info["pts_home"]:
        ganada = True

    # 2. Baloncesto Ganador H2H
    elif "Ganador:" in seleccion:
      es_resoluble = True
      if partido_info["pts_home"] > partido_info["pts_away"]:
        equipo_ganador = partido_info["home_team"]
      else:
        equipo_ganador = partido_info["away_team"]
      if equipo_ganador.lower() in seleccion.lower():
        ganada = True

    # 3. Totales (Goles u Over/Under)
    elif "Goles" in seleccion or "Totales" in seleccion:
      es_resoluble = True
      puntos_reales = partido_info["totales"]
      try:
        partes = seleccion.split()
        linea = float(partes[-3] if " - " in seleccion else partes[-1])
        if "Over" in seleccion:
          if puntos_reales > linea:
            ganada = True
        elif "Under" in seleccion:
          if puntos_reales < linea:
            ganada = True
      except Exception:
        es_resoluble = False

    # 4. Hándicaps (Spreads)
    elif "Handicap" in seleccion:
      es_resoluble = True
      try:
        if partido_info["home_team"].lower() in seleccion.lower():
          puntos_ajustados = partido_info["pts_home"] + float(
              seleccion.split("(")[1].split(")")[0]
          )
          rival_puntos = partido_info["pts_away"]
        else:
          puntos_ajustados = partido_info["pts_away"] + float(
              seleccion.split("(")[1].split(")")[0]
          )
          rival_puntos = partido_info["pts_home"]

        if puntos_ajustados > rival_puntos:
          ganada = True
      except Exception:
        es_resoluble = False

    # Actualizar Base de Datos si se pudo resolver
    if es_resoluble:
      nuevo_estado = "GANADA" if ganada else "PERDIDA"
      pnl = round((stake * cuota) - stake, 2) if ganada else -round(stake, 2)

      cursor.execute(
          """
                UPDATE apuestas 
                SET estado = ?, resultado = ?, pnl = ? 
                WHERE id = ?
            """,
          (nuevo_estado, resultado_str, pnl, ap_id),
      )
      conn.commit()
      liquidadas += 1
      print(
          f"✅ Apuesta #{ap_id} liquidada: {nuevo_estado} | P&L: {pnl:+.2f} € |"
          f" Resultado: {resultado_str}"
      )

  conn.close()
  msg_final = f"Se liquidaron {liquidadas} apuestas exitosamente."
  actualizar_log(msg_final)
  print(f"🏁 {msg_final}")


if __name__ == "__main__":
  liquidar_apuestas()