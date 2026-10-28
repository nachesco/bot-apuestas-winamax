from datetime import datetime
import os
import sys
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import accuracy_score, mean_absolute_error
from sklearn.model_selection import train_test_split

if sys.platform == "win32":
  sys.stdout.reconfigure(encoding="utf-8")
  sys.stderr.reconfigure(encoding="utf-8")


def reentrenar_modelos():
  csv_path = "datos_historicos_nba.csv"
  if not os.path.exists(csv_path):
    print(f"❌ No se encontró el archivo de datos: {csv_path}")
    return

  print(
      f"🔄 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Iniciando"
      " reentrenamiento unificado..."
  )
  df_raw = pd.read_csv(csv_path)

  # ==========================================
  # INGENIERÍA DE VARIABLES UNIFICADA
  # ==========================================
  df_clas = df_raw.copy()
  df_clas["fecha"] = pd.to_datetime(df_clas["fecha"])
  df_clas = df_clas.sort_values("fecha").reset_index(drop=True)

  # Asegurar variable de puntos totales
  if "puntos_totales" not in df_clas.columns:
    df_clas["puntos_totales"] = (
        df_clas["puntos_local"] + df_clas["puntos_visitante"]
    )

  local = df_clas[
      [
          "fecha",
          "equipo_local",
          "puntos_local",
          "puntos_visitante",
          "fg_pct_local",
      ]
  ].copy()
  local.columns = ["fecha", "equipo", "pts_favor", "pts_contra", "fg_pct"]

  visitante = df_clas[
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

  local_stats = equipos.rename(
      columns={
          "equipo": "equipo_local",
          "pts_favor_m5": "loc_pts_favor_m5",
          "pts_contra_m5": "loc_pts_contra_m5",
          "fg_m5": "loc_fg_m5",
          "net_rating_m5": "loc_net_rating_m5",
          "dias_descanso": "loc_descanso",
          "es_b2b": "loc_b2b",
      }
  )

  vis_stats = equipos.rename(
      columns={
          "equipo": "equipo_visitante",
          "pts_favor_m5": "vis_pts_favor_m5",
          "pts_contra_m5": "vis_pts_contra_m5",
          "fg_m5": "vis_fg_m5",
          "net_rating_m5": "vis_net_rating_m5",
          "dias_descanso": "vis_descanso",
          "es_b2b": "vis_b2b",
      }
  )

  df_full = df_clas.merge(
      local_stats[
          [
              "fecha",
              "equipo_local",
              "loc_pts_favor_m5",
              "loc_pts_contra_m5",
              "loc_fg_m5",
              "loc_net_rating_m5",
              "loc_descanso",
              "loc_b2b",
          ]
      ],
      on=["fecha", "equipo_local"],
      how="left",
  )

  df_full = df_full.merge(
      vis_stats[
          [
              "fecha",
              "equipo_visitante",
              "vis_pts_favor_m5",
              "vis_pts_contra_m5",
              "vis_fg_m5",
              "vis_net_rating_m5",
              "vis_descanso",
              "vis_b2b",
          ]
      ],
      on=["fecha", "equipo_visitante"],
      how="left",
  )

  df_full["diff_pts_favor"] = (
      df_full["loc_pts_favor_m5"] - df_full["vis_pts_favor_m5"]
  )
  df_full["diff_pts_contra"] = (
      df_full["loc_pts_contra_m5"] - df_full["vis_pts_contra_m5"]
  )
  df_full["diff_fg_pct"] = df_full["loc_fg_m5"] - df_full["vis_fg_m5"]
  df_full["diff_net_rating"] = (
      df_full["loc_net_rating_m5"] - df_full["vis_net_rating_m5"]
  )
  df_full["diff_descanso"] = df_full["loc_descanso"] - df_full["vis_descanso"]

  df_full["gana_local"] = (
      df_full["puntos_local"] > df_full["puntos_visitante"]
  ).astype(int)

  df_full = df_full.dropna().reset_index(drop=True)

  features_nba = [
      "loc_pts_favor_m5",
      "loc_pts_contra_m5",
      "loc_fg_m5",
      "loc_net_rating_m5",
      "loc_descanso",
      "loc_b2b",
      "vis_pts_favor_m5",
      "vis_pts_contra_m5",
      "vis_fg_m5",
      "vis_net_rating_m5",
      "vis_descanso",
      "vis_b2b",
      "diff_pts_favor",
      "diff_pts_contra",
      "diff_fg_pct",
      "diff_net_rating",
      "diff_descanso",
  ]

  X = df_full[features_nba]

  # ==========================================
  # 1. ENTRENAR MODELO DE GANADOR
  # ==========================================
  print("\n--- [1/2] Entrenando Modelo de Ganador ---")
  y_nba = df_full["gana_local"]
  X_tr, X_te, y_tr, y_te = train_test_split(
      X, y_nba, test_size=0.2, random_state=42, shuffle=False
  )
  modelo_nba = RandomForestClassifier(
      n_estimators=150, max_depth=6, random_state=42
  )
  modelo_nba.fit(X_tr, y_tr)
  acc = accuracy_score(y_te, modelo_nba.predict(X_te))
  print(f"✅ Modelo de Ganador actualizado. Precisión: {acc*100:.2f}%")
  joblib.dump(modelo_nba, "modelo_nba.pkl")

  # ==========================================
  # 2. ENTRENAR MODELO DE PUNTOS TOTALES
  # ==========================================
  print("\n--- [2/2] Entrenando Modelo de Puntos Totales ---")
  y_tot = df_full["puntos_totales"]
  X_tr_t, X_te_t, y_tr_t, y_te_t = train_test_split(
      X, y_tot, test_size=0.2, random_state=42
  )
  modelo_totales = RandomForestRegressor(
      n_estimators=150, max_depth=10, random_state=42
  )
  modelo_totales.fit(X_tr_t, y_tr_t)
  mae = mean_absolute_error(y_te_t, modelo_totales.predict(X_te_t))
  print(f"✅ Modelo de Totales actualizado. MAE: ±{mae:.2f} puntos")
  joblib.dump(modelo_totales, "modelo_totales.pkl")

  print(
      "\n🎉 ¡Reentrenamiento unificado completado con éxito! Modelos listos."
  )


if __name__ == "__main__":
  reentrenar_modelos()