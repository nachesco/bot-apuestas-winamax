import os
import joblib
import numpy as np
import pandas as pd

CSV_PATH = "datos_historicos_nba.csv"
PATH_H2H = "modelo_nba.pkl"
PATH_TOTALES = "modelo_totales.pkl"

if not os.path.exists(CSV_PATH):
    print(f"❌ No se encontró el archivo {CSV_PATH}")
    exit()

df = pd.read_csv(CSV_PATH)
print(f"📂 Cargados {len(df)} partidos históricos para la evaluación.\n")

# ==============================================================================
# 1. EVALUACIÓN MODELO GANADOR (H2H)
# ==============================================================================
if os.path.exists(PATH_H2H):
    modelo_h2h = joblib.load(PATH_H2H)
    print("🧠 --- EVALUANDO MODELO GANADOR (H2H) ---")

    # Mapeo automático de features según las que espera el modelo
    if hasattr(modelo_h2h, "feature_names_in_"):
        cols = modelo_h2h.feature_names_in_
        X_h2h = pd.DataFrame(index=df.index)
        for col in cols:
            if col in df.columns:
                X_h2h[col] = df[col]
            else:
                X_h2h[col] = 0.0  # Relleno neutro si la feature no existía
    else:
        X_h2h = df.select_dtypes(include=[np.number])

    probs = modelo_h2h.predict_proba(X_h2h)[:, 1]
    predicciones = (probs >= 0.50).astype(int)
    reales = df["gana_local"].astype(int)

    aciertos = (predicciones == reales).sum()
    total = len(df)
    accuracy = (aciertos / total) * 100

    print(f"🎯 Porcentaje de Acierto (Accuracy): {accuracy:.2f}% ({aciertos}/{total} partidos)")

    # Simulación de rendimiento económico H2H a cuota media 1.91
    cuota_simulada = 1.91
    apuestas_ganadas = aciertos
    apuestas_perdidas = total - aciertos
    pnl_simulado = (apuestas_ganadas * (cuota_simulada - 1.0)) - apuestas_perdidas
    roi_simulado = (pnl_simulado / total) * 100

    print(f"💰 Rentabilidad Simulada (Cuota promedio 1.91): {pnl_simulado:+.2f} uds | ROI: {roi_simulado:+.2f}%\n")
else:
    print("⚠️ No se encontró `modelo_nba.pkl` para evaluar H2H.\n")


# ==============================================================================
# 2. EVALUACIÓN MODELO PUNTOS TOTALES (OVER/UNDER)
# ==============================================================================
if os.path.exists(PATH_TOTALES):
    modelo_totales = joblib.load(PATH_TOTALES)
    print("📊 --- EVALUANDO MODELO PUNTOS TOTALES (OVER/UNDER) ---")

    if hasattr(modelo_totales, "feature_names_in_"):
        cols = modelo_totales.feature_names_in_
        X_tot = pd.DataFrame(index=df.index)
        for col in cols:
            if col in df.columns:
                X_tot[col] = df[col]
            else:
                X_tot[col] = 0.0
    else:
        X_tot = df.select_dtypes(include=[np.number])

    pred_puntos = modelo_totales.predict(X_tot)
    reales_puntos = df["puntos_totales"]

    error_absoluto = np.abs(pred_puntos - reales_puntos)
    mae = error_absoluto.mean()
    rmse = np.sqrt(((pred_puntos - reales_puntos) ** 2).mean())

    print(f"📏 Error Absoluto Medio (MAE): {mae:.2f} puntos")
    print(f"📐 Error Cuadrático Medio (RMSE): {rmse:.2f} puntos")
    print(f"🔍 Ejemplo de predicción vs real (primeros 3 partidos):")
    for i in range(min(3, len(df))):
        print(f"   Partido #{i+1}: Predicho {pred_puntos[i]:.1f} pts | Real {reales_puntos.iloc[i]} pts (Dif: {error_absoluto.iloc[i]:.1f} pts)")
else:
    print("⚠️ No se encontró `modelo_totales.pkl` para evaluar Totales.\n")