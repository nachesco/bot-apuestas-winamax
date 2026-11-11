from dotenv import load_dotenv
import os
import requests
import sqlite3
import pandas as pd

# Cargar variables del archivo .env local
load_dotenv()

# Recopilar las API Keys disponibles (Principal y Secundaria)
API_KEYS = [os.getenv("ODDS_API_KEY"), os.getenv("ODDS_API_KEY_SECUNDARIA")]
API_KEYS = [k for k in API_KEYS if k]

if not API_KEYS:
  print("❌ ERROR CRÍTICO: No se ha encontrado ninguna API Key en el archivo .env")

DB_PATH = "apuestas.db"
BANKROLL_INICIAL = 20.0
CRITERIO_KELLY = 0.25
MAX_STAKE_PCT = 0.03
MIN_STAKE_EUR = 0.10
UMBRAL_EV = 0.01  # Filtro relajado a +EV > 1% para mayor volumen

DEPORTES_FUTBOL = [
    "soccer_spain_la_liga",
    "soccer_epl",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league",
]


def obtener_bankroll_actual():
  if not os.path.exists(DB_PATH):
    return BANKROLL_INICIAL
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute("SELECT SUM(pnl) FROM apuestas WHERE estado != 'PENDIENTE'")
  pnl = cursor.fetchone()[0] or 0.0
  conn.close()
  return max(1.0, BANKROLL_INICIAL + pnl)


def inicializar_db():
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS apuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_partido TEXT,
            deporte TEXT DEFAULT 'futbol',
            seleccion TEXT,
            cuota REAL,
            ev REAL,
            stake REAL,
            estado TEXT DEFAULT 'PENDIENTE',
            resultado TEXT,
            fecha_partido TEXT,
            casa TEXT DEFAULT 'winamax',
            pnl REAL DEFAULT 0.0,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
  conn.commit()
  conn.close()


def escanear_futbol():
  if not API_KEYS:
    print("❌ No hay claves configuradas. Abortando escaneo.")
    return

  inicializar_db()
  bankroll = obtener_bankroll_actual()
  print(
      f"--- Escaneando Fútbol (Ganadores y Goles) con Bankroll de"
      f" {bankroll:.2f}€ ---"
  )

  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  apuestas_encontradas = 0
  mercados = "h2h,totals"

  for deporte in DEPORTES_FUTBOL:
    partidos = None
    # Intento de petición rotando por las claves disponibles si da 401
    for api_key in API_KEYS:
      url = f"https://api.the-odds-api.com/v4/sports/{deporte}/odds/?apiKey={api_key}&regions=fr,de,eu&markets={mercados}"
      try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
          partidos = res.json()
          break
        elif res.status_code == 401:
          print(
              f"⚠️ Clave actual agotada (401) en {deporte}, probando clave"
              " alternativa..."
          )
          continue
        else:
          print(f"Error API en {deporte}: HTTP {res.status_code}")
          break
      except Exception as e:
        print(f"Excepción en {deporte}: {e}")
        break

    if partidos is None:
      continue

    for p in partidos:
      id_partido = p.get("id")
      home_team = p.get("home_team")
      away_team = p.get("away_team")
      commence_time = p.get("commence_time")

      bookmakers = p.get("bookmakers", [])
      winamax = next(
          (b for b in bookmakers if "winamax" in b.get("key", "").lower()), None
      )
      if not winamax:
        continue

      markets_list = winamax.get("markets", [])

      for m in markets_list:
        m_key = m.get("key")
        outcomes = m.get("outcomes", [])

        # 1. Mercado Ganador 1X2 (h2h)
        if m_key == "h2h" and len(outcomes) >= 3:
          cuotas_dict = {o["name"]: o["price"] for o in outcomes}
          cuota_1 = cuotas_dict.get(home_team)
          cuota_2 = cuotas_dict.get(away_team)
          cuota_x = cuotas_dict.get("Draw")

          if cuota_1 and cuota_x and cuota_2:
            prob_raw_1 = 1.0 / cuota_1
            prob_raw_x = 1.0 / cuota_x
            prob_raw_2 = 1.0 / cuota_2
            margin = prob_raw_1 + prob_raw_x + prob_raw_2

            p1 = prob_raw_1 / margin
            px = prob_raw_x / margin
            p2 = prob_raw_2 / margin

            opciones = [
                (f"{home_team} (1)", cuota_1, p1),
                (f"Empate (X) - {home_team} vs {away_team}", cuota_x, px),
                (f"{away_team} (2)", cuota_2, p2),
            ]

            for seleccion, cuota, prob_estimada in opciones:
              ev = (prob_estimada * cuota) - 1.0
              if ev >= UMBRAL_EV:
                cursor.execute(
                    "SELECT id FROM apuestas WHERE id_partido = ? AND seleccion"
                    " = ? AND estado = 'PENDIENTE'",
                    (id_partido, seleccion),
                )
                if cursor.fetchone():
                  continue

                b = cuota - 1.0
                q = 1.0 - prob_estimada
                f_kelly = (b * prob_estimada - q) / b
                f_kelly_ajustado = f_kelly * CRITERIO_KELLY
                stake_pct = min(f_kelly_ajustado, MAX_STAKE_PCT)
                stake_eur = max(MIN_STAKE_EUR, round(bankroll * stake_pct, 2))

                if stake_eur <= bankroll:
                  cursor.execute(
                      """
                                        INSERT INTO apuestas (id_partido, deporte, seleccion, cuota, ev, stake, fecha_partido, casa)
                                        VALUES (?, 'futbol', ?, ?, ?, ?, ?, 'winamax')
                                    """,
                      (
                          id_partido,
                          seleccion,
                          cuota,
                          round(ev, 4),
                          stake_eur,
                          commence_time,
                      ),
                  )
                  conn.commit()
                  print(
                      f"✅ Apuesta Fútbol Registrada: {seleccion} | Cuota:"
                      f" {cuota} | EV: +{ev*100:.1f}% | Stake: {stake_eur}€"
                  )
                  apuestas_encontradas += 1

        # 2. Mercado de Goles Totales (Over / Under)
        elif m_key == "totals":
          for o in outcomes:
            name = o.get("name")
            point = o.get("point")
            price = o.get("price")

            if name and point is not None and price:
              prob_estimada = 1.0 / price
              ev = (prob_estimada * price) - 1.0

              if ev >= UMBRAL_EV:
                seleccion = f"Goles {name} {point} - {home_team} vs {away_team}"

                cursor.execute(
                    "SELECT id FROM apuestas WHERE id_partido = ? AND seleccion"
                    " = ? AND estado = 'PENDIENTE'",
                    (id_partido, seleccion),
                )
                if cursor.fetchone():
                  continue

                b = price - 1.0
                q = 1.0 - prob_estimada
                f_kelly = (b * prob_estimada - q) / b
                f_kelly_ajustado = f_kelly * CRITERIO_KELLY
                stake_pct = min(f_kelly_ajustado, MAX_STAKE_PCT)
                stake_eur = max(MIN_STAKE_EUR, round(bankroll * stake_pct, 2))

                if stake_eur <= bankroll:
                  cursor.execute(
                      """
                                        INSERT INTO apuestas (id_partido, deporte, seleccion, cuota, ev, stake, fecha_partido, casa)
                                        VALUES (?, 'futbol', ?, ?, ?, ?, ?, 'winamax')
                                    """,
                      (
                          id_partido,
                          seleccion,
                          price,
                          round(ev, 4),
                          stake_eur,
                          commence_time,
                      ),
                  )
                  conn.commit()
                  print(
                      f"✅ Apuesta Goles Registrada: {seleccion} | Cuota:"
                      f" {price} | EV: +{ev*100:.1f}% | Stake: {stake_eur}€"
                  )
                  apuestas_encontradas += 1

  conn.close()
  print(f"Escaneo de fútbol finalizado. Nuevas apuestas: {apuestas_encontradas}")


if __name__ == "__main__":
  escanear_futbol()