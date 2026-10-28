from datetime import datetime
import os
import sqlite3
import sys
import joblib
import numpy as np
import pandas as pd
import requests

# Importamos el gestor de lesiones de la Fase 2
from lesiones import obtener_penalizacion_lesion

if sys.platform == "win32":
  sys.stdout.reconfigure(encoding="utf-8")
  sys.stderr.reconfigure(encoding="utf-8")

# --- CONFIGURACIONES Y CONSTANTES ---
DB_PATH = "apuestas.db"
MODELO_GANADOR_PATH = "modelo_nba.pkl"
MODELO_TOTALES_PATH = "modelo_totales.pkl"
HISTORICO_PATH = "datos_historicos_nba.csv"
LOG_BOT = "logs_bot.txt"

# Configuración de The Odds API (Ligas múltiples de Baloncesto)
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "c47d66c9ae730ebc0dee61ac3c68581e")
DEPORTES_BASKET = [
    "basketball_nba",
    "basketball_euroleague",
    "basketball_spain_acb",
]

# --- CONFIGURACIÓN DE GESTIÓN DE BANKROLL (FASE 3) ---
BANKROLL_INICIAL = 20.0  # Capital inicial real (20 €)
FRACCION_KELLY = 0.25  # Fracción conservadora de Kelly (1/4 de Kelly)
STAKE_MAX_PORCENTAJE = (
    0.03  # Límite máximo del 3% del bankroll actual por apuesta
)
UMBRAL_EV = 0.02  # Filtro estricto +EV > 2%


def actualizar_log():
  """Actualiza la marca de tiempo del log para el Dashboard."""
  with open(LOG_BOT, "w", encoding="utf-8") as f:
    f.write(
        f"Última ejecución del bot multi-liga: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )


def enviar_alerta_telegram(mensaje):
  """Envía notificación a Telegram si las variables de entorno están configuradas."""
  token = os.getenv("TELEGRAM_BOT_TOKEN")
  chat_id = os.getenv("TELEGRAM_CHAT_ID")
  if token and chat_id:
    try:
      url = f"https://api.telegram.org/bot{token}/sendMessage"
      payload = {"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"}
      requests.post(url, json=payload, timeout=5)
    except Exception as e:
      print(f"⚠️ Error enviando alerta a Telegram: {e}")


def preparar_features_partido(df_hist, equipo_local, equipo_visitante):
  """Calcula promedios móviles (m5), descanso y aplica el impacto de lesiones (Fase 2)."""
  local = df_hist[
      [
          "fecha",
          "equipo_local",
          "puntos_local",
          "puntos_visitante",
          "fg_pct_local",
      ]
  ].copy()
  local.columns = ["fecha", "equipo", "pts_favor", "pts_contra", "fg_pct"]

  visitante = df_hist[
      [
          "fecha",
          "equipo_visitante",
          "puntos_visitante",
          "puntos_local",
          "fg_pct_visitante",
      ]
  ].copy()
  visitante.columns = ["fecha", "equipo", "pts_favor", "pts_contra", "fg_pct"]

  equipos = (
      pd.concat([local, visitante])
      .sort_values(["equipo", "fecha"])
      .reset_index(drop=True)
  )

  equipos["dias_descanso"] = (
      equipos.groupby("equipo")["fecha"].diff().dt.days - 1
  )
  equipos["dias_descanso"] = (
      equipos["dias_descanso"].fillna(2).clip(lower=0, upper=4)
  )
  equipos["es_b2b"] = (equipos["dias_descanso"] == 0).astype(int)

  equipos["ortg"] = equipos["pts_favor"]
  equipos["drtg"] = equipos["pts_contra"]
  equipos["net_rating"] = equipos["ortg"] - equipos["drtg"]

  equipos["pts_favor_m5"] = equipos.groupby("equipo")["pts_favor"].transform(
      lambda x: x.shift(1).rolling(5).mean()
  )
  equipos["pts_contra_m5"] = equipos.groupby("equipo")[
      "pts_contra"
  ].transform(lambda x: x.shift(1).rolling(5).mean())
  equipos["fg_m5"] = equipos.groupby("equipo")["fg_pct"].transform(
      lambda x: x.shift(1).rolling(5).mean()
  )
  equipos["net_rating_m5"] = equipos.groupby("equipo")[
      "net_rating"
  ].transform(lambda x: x.shift(1).rolling(5).mean())

  st_local = equipos[equipos["equipo"] == equipo_local].tail(1)
  st_vis = equipos[equipos["equipo"] == equipo_visitante].tail(1)

  if st_local.empty or st_vis.empty:
    return None

  loc_descanso = float(st_local["dias_descanso"].values[0])
  loc_b2b = int(st_local["es_b2b"].values[0])
  vis_descanso = float(st_vis["dias_descanso"].values[0])
  vis_b2b = int(st_vis["es_b2b"].values[0])

  loc_net_rating = float(st_local["net_rating_m5"].values[0])
  vis_net_rating = float(st_vis["net_rating_m5"].values[0])

  # --- APLICACIÓN DEL IMPACTO DE LESIONES (FASE 2) ---
  pen_loc, pen_vis = obtener_penalizacion_lesion(equipo_local, equipo_visitante)
  loc_net_rating += pen_loc
  vis_net_rating += pen_vis

  features = {
      "loc_pts_favor_m5": float(st_local["pts_favor_m5"].values[0]),
      "loc_pts_contra_m5": float(st_local["pts_contra_m5"].values[0]),
      "loc_fg_m5": float(st_local["fg_m5"].values[0]),
      "loc_net_rating_m5": loc_net_rating,
      "loc_descanso": loc_descanso,
      "loc_b2b": loc_b2b,
      "vis_pts_favor_m5": float(st_vis["pts_favor_m5"].values[0]),
      "vis_pts_contra_m5": float(st_vis["pts_contra_m5"].values[0]),
      "vis_fg_m5": float(st_vis["fg_m5"].values[0]),
      "vis_net_rating_m5": vis_net_rating,
      "vis_descanso": vis_descanso,
      "vis_b2b": vis_b2b,
      "diff_pts_favor": float(st_local["pts_favor_m5"].values[0])
      - float(st_vis["pts_favor_m5"].values[0]),
      "diff_pts_contra": float(st_local["pts_contra_m5"].values[0])
      - float(st_vis["pts_contra_m5"].values[0]),
      "diff_fg_pct": float(st_local["fg_m5"].values[0])
      - float(st_vis["fg_m5"].values[0]),
      "diff_net_rating": loc_net_rating - vis_net_rating,
      "diff_descanso": loc_descanso - vis_descanso,
  }

  return pd.DataFrame([features])


def ejecutar_bot():
  print(
      f"🤖 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Ejecutando bot"
      f" multi-liga (Winamax, Bankroll: {BANKROLL_INICIAL}€)..."
  )

  # Cargar modelos si existen (para NBA)
  modelo_nba = (
      joblib.load(MODELO_GANADOR_PATH)
      if os.path.exists(MODELO_GANADOR_PATH)
      else None
  )
  modelo_totales = (
      joblib.load(MODELO_TOTALES_PATH)
      if os.path.exists(MODELO_TOTALES_PATH)
      else None
  )
  df_hist = (
      pd.read_csv(HISTORICO_PATH) if os.path.exists(HISTORICO_PATH) else None
  )
  if df_hist is not None:
    df_hist["fecha"] = pd.to_datetime(df_hist["fecha"])

  # Conexión a Base de Datos y Migración Automática
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS apuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_partido TEXT,
            deporte TEXT DEFAULT 'baloncesto',
            seleccion TEXT,
            cuota REAL,
            ev REAL,
            stake REAL,
            estado TEXT,
            resultado TEXT,
            fecha TEXT,
            fecha_partido TEXT,
            casa TEXT,
            prob REAL,
            pnl REAL
        )
    """)
  conn.commit()

  columnas_necesarias = {
      "deporte": "TEXT DEFAULT 'baloncesto'",
      "casa": "TEXT",
      "prob": "REAL",
      "pnl": "REAL DEFAULT 0.0",
  }
  cursor.execute("PRAGMA table_info(apuestas)")
  columnas_existentes = [col[1] for col in cursor.fetchall()]
  for col_nombre, col_tipo in columnas_necesarias.items():
    if col_nombre not in columnas_existentes:
      try:
        cursor.execute(
            f"ALTER TABLE apuestas ADD COLUMN {col_nombre} {col_tipo}"
        )
        conn.commit()
      except Exception:
        pass

  # --- CÁLCULO DEL BANKROLL DISPONIBLE REAL ---
  df_br = pd.read_sql_query(
      "SELECT SUM(pnl) as total_pnl FROM apuestas WHERE estado != 'PENDIENTE'",
      conn,
  )
  pnl_historico = (
      df_br["total_pnl"].values[0]
      if not df_br.empty and pd.notna(df_br["total_pnl"].values[0])
      else 0.0
  )
  bankroll_base = max(1.0, BANKROLL_INICIAL + pnl_historico)

  df_pendientes = pd.read_sql_query(
      "SELECT SUM(stake) as total_pendientes FROM apuestas WHERE estado ="
      " 'PENDIENTE'",
      conn,
  )
  stakes_pendientes = (
      df_pendientes["total_pendientes"].values[0]
      if not df_pendientes.empty
      and pd.notna(df_pendientes["total_pendientes"].values[0])
      else 0.0
  )

  bankroll_disponible = max(0.10, bankroll_base - stakes_pendientes)
  print(
      f"💰 Bankroll Base: {bankroll_base:.2f} € | Comprometido:"
      f" {stakes_pendientes:.2f} € | Disponible Real:"
      f" {bankroll_disponible:.2f} €"
  )

  apuestas_realizadas = 0

  # Iterar por cada competición de baloncesto configurada
  for deporte in DEPORTES_BASKET:
    url = f"https://api.the-odds-api.com/v4/sports/{deporte}/odds/"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": "h2h,spreads,totals",
        "bookmakers": "winamax",  # Exclusivo Winamax
        "oddsFormat": "decimal",
    }

    try:
      response = requests.get(url, params=params, timeout=10)
      if response.status_code != 200:
        continue
      partidos = response.json()
    except Exception as e:
      print(f"❌ Error consultando {deporte}: {e}")
      continue

    print(
        f"📡 Competición [{deporte}]: {len(partidos)} partidos encontrados en"
        " Winamax"
    )

    for p in partidos:
      if bankroll_disponible < 0.10:
        break

      id_partido = p.get("id")
      equipo_local = p.get("home_team")
      equipo_visitante = p.get("away_team")
      fecha_partido = p.get("commence_time")

      # Determinar probabilidades según la liga
      prob_local, prob_visitante = None, None
      if deporte == "basketball_nba" and modelo_nba and df_hist is not None:
        X_pred = preparar_features_partido(
            df_hist, equipo_local, equipo_visitante
        )
        if X_pred is not None:
          prob_local = float(modelo_nba.predict_proba(X_pred)[0][1])
          prob_visitante = 1.0 - prob_local

      for bookmaker in p.get("bookmakers", []):
        casa = bookmaker.get("title")
        if casa.lower() != "winamax":
          continue

        for market in bookmaker.get("markets", []):
          m_key = market.get("key")
          outcomes = market.get("outcomes", [])

          # --- 1. MERCADO GANADOR (H2H) ---
          if m_key == "h2h" and len(outcomes) == 2:
            cuotas_dict = {o.get("name"): o.get("price") for o in outcomes}
            c_home = cuotas_dict.get(equipo_local)
            c_away = cuotas_dict.get(equipo_visitante)

            if not c_home or not c_away:
              continue

            # Si no hay modelo ML (ACB / Euroliga), usar probabilidad implícita desvisada (sin vig)
            if prob_local is None:
              p_raw_h = 1.0 / c_home
              p_raw_a = 1.0 / c_away
              margin = p_raw_h + p_raw_a
              ph = p_raw_h / margin
              pa = p_raw_a / margin
            else:
              ph = prob_local
              pa = prob_visitante

            opciones_h2h = [
                (f"Ganador: {equipo_local}", c_home, ph),
                (f"Ganador: {equipo_visitante}", c_away, pa),
            ]

            for seleccion, cuota, p_real in opciones_h2h:
              ev = (p_real * cuota) - 1.0
              if ev > UMBRAL_EV:
                cursor.execute(
                    "SELECT id FROM apuestas WHERE id_partido = ? AND seleccion"
                    " = ? AND estado = 'PENDIENTE'",
                    (id_partido, seleccion),
                )
                if cursor.fetchone():
                  continue

                b = cuota - 1.0
                q = 1.0 - p_real
                kelly_puro = (p_real * b - q) / b if b > 0 else 0
                if kelly_puro > 0:
                  stake = round(
                      min(
                          bankroll_disponible * kelly_puro * FRACCION_KELLY,
                          bankroll_disponible * STAKE_MAX_PORCENTAJE,
                      ),
                      2,
                  )
                else:
                  stake = 0.0

                if stake >= 0.10 and bankroll_disponible >= stake:
                  cursor.execute(
                      """
                                        INSERT INTO apuestas (id_partido, deporte, seleccion, cuota, ev, stake, estado, fecha, fecha_partido, casa, prob, pnl)
                                        VALUES (?, ?, ?, ?, ?, ?, 'PENDIENTE', ?, ?, ?, ?, 0.0)
                                    """,
                      (
                          id_partido,
                          deporte,
                          seleccion,
                          cuota,
                          ev,
                          stake,
                          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                          fecha_partido,
                          casa,
                          p_real,
                      ),
                  )
                  conn.commit()
                  apuestas_realizadas += 1
                  bankroll_disponible -= stake

                  enviar_alerta_telegram(
                      f"🏀 *¡Apuesta Basket (+EV en Winamax)!*\n\n"
                      f"🏆 Ligar: {deporte}\n"
                      f"🆚 {equipo_local} vs {equipo_visitante}\n"
                      f"📌 {seleccion} | Cuota: {cuota} | EV: {ev*100:.2f}%\n"
                      f"💵 Stake: {stake}€ (Restante: {bankroll_disponible:.2f}€)"
                  )

          # --- 2. MERCADOS DE HÁNDICAPS (SPREADS) Y TOTALES (TOTALS) ---
          elif m_key in ["spreads", "totals"]:
            for outcome in outcomes:
              name = outcome.get("name")
              point = outcome.get("point")
              cuota = outcome.get("price")

              if not name or cuota is None:
                continue

              # Probabilidad implícita basada en cuota de mercado
              p_real = 1.0 / cuota
              ev = (p_real * cuota) - 1.0

              if ev > UMBRAL_EV:
                if m_key == "spreads":
                  seleccion = (
                      f"Handicap {name} ({point:+.1f}) - {equipo_local} vs"
                      f" {equipo_visitante}"
                  )
                else:
                  seleccion = (
                      f"Totales {name} {point} - {equipo_local} vs"
                      f" {equipo_visitante}"
                  )

                cursor.execute(
                    "SELECT id FROM apuestas WHERE id_partido = ? AND seleccion"
                    " = ? AND estado = 'PENDIENTE'",
                    (id_partido, seleccion),
                )
                if cursor.fetchone():
                  continue

                b = cuota - 1.0
                q = 1.0 - p_real
                kelly_puro = (p_real * b - q) / b if b > 0 else 0
                if kelly_puro > 0:
                  stake = round(
                      min(
                          bankroll_disponible * kelly_puro * FRACCION_KELLY,
                          bankroll_disponible * STAKE_MAX_PORCENTAJE,
                      ),
                      2,
                  )
                else:
                  stake = 0.0

                if stake >= 0.10 and bankroll_disponible >= stake:
                  cursor.execute(
                      """
                                        INSERT INTO apuestas (id_partido, deporte, seleccion, cuota, ev, stake, estado, fecha, fecha_partido, casa, prob, pnl)
                                        VALUES (?, ?, ?, ?, ?, ?, 'PENDIENTE', ?, ?, ?, ?, 0.0)
                                    """,
                      (
                          id_partido,
                          deporte,
                          seleccion,
                          cuota,
                          ev,
                          stake,
                          datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                          fecha_partido,
                          casa,
                          p_real,
                      ),
                  )
                  conn.commit()
                  apuestas_realizadas += 1
                  bankroll_disponible -= stake

                  enviar_alerta_telegram(
                      f"🏀 *¡Apuesta {m_key.capitalize()} (+EV Winamax)!*\n\n"
                      f"🏆 Liga: {deporte}\n"
                      f"🆚 {equipo_local} vs {equipo_visitante}\n"
                      f"📌 {seleccion} | Cuota: {cuota} | EV: {ev*100:.2f}%\n"
                      f"💵 Stake: {stake}€"
                  )

  conn.close()
  actualizar_log()
  print(
      f"✅ Ciclo multi-liga finalizado. Se registraron {apuestas_realizadas}"
      " nuevas apuestas en Winamax."
  )


if __name__ == "__main__":
  ejecutar_bot()