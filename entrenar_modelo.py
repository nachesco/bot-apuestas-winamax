import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import train_test_split


def cargar_y_preparar_datos(csv_path="datos_historicos_nba.csv"):
    df = pd.read_csv(csv_path)
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = df.sort_values("fecha").reset_index(drop=True)

    # Reestructurar datos por equipo/fecha
    local = df[
        [
            "fecha",
            "equipo_local",
            "puntos_local",
            "puntos_visitante",
            "fg_pct_local",
        ]
    ].copy()
    local.columns = ["fecha", "equipo", "pts_favor", "pts_contra", "fg_pct"]

    visitante = df[
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

    # 1. Días de descanso reales (B2B)
    equipos["dias_descanso"] = (
        equipos.groupby("equipo")["fecha"].diff().dt.days - 1
    )
    equipos["dias_descanso"] = (
        equipos["dias_descanso"].fillna(2).clip(lower=0, upper=4)
    )
    equipos["es_b2b"] = (equipos["dias_descanso"] == 0).astype(int)

    # 2. Estimación de Ratings (ORTG / DRTG aproximado por rendimiento reciente)
    equipos["ortg"] = equipos["pts_favor"]
    equipos["drtg"] = equipos["pts_contra"]
    equipos["net_rating"] = equipos["ortg"] - equipos["drtg"]

    # 3. Promedios móviles de los últimos 5 partidos
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

    # Reconstruir el dataset de partidos con las nuevas variables
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

    df_full = df.merge(
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

    # Diferenciales clave
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
    df_full["diff_descanso"] = (
        df_full["loc_descanso"] - df_full["vis_descanso"]
    )

    # Variable objetivo (1 si gana local, 0 si gana visitante)
    df_full["gana_local"] = (
        df_full["puntos_local"] > df_full["puntos_visitante"]
    ).astype(int)

    df_full = df_full.dropna().reset_index(drop=True)
    return df_full


def entrenar():
    print("📊 Procesando datos e ingeniería de variables avanzadas...")
    df = cargar_y_preparar_datos()

    features = [
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

    X = df[features]
    y = df["gana_local"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, shuffle=False
    )

    modelo = RandomForestClassifier(
        n_estimators=150, max_depth=6, random_state=42
    )
    modelo.fit(X_train, y_train)

    preds = modelo.predict(X_test)
    acc = accuracy_score(y_test, preds)

    print(f"✅ Modelo re-entrenado con éxito. Precisión (Accuracy): {acc*100:.2f}%")
    joblib.dump(modelo, "modelo_nba.pkl")
    print("💾 Nuevo modelo guardado en `modelo_nba.pkl`.")


if __name__ == "__main__":
    entrenar()