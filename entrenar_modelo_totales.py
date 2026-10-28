import os
import sys
import pandas as pd
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

print("📊 Cargando datos e ingeniería de variables para Puntos Totales...")

if not os.path.exists("datos_historicos_nba.csv"):
    print("❌ No se encontró `datos_historicos_nba.csv`.")
    sys.exit(1)

df = pd.read_csv("datos_historicos_nba.csv")

# 1. Crear la variable objetivo: Puntos Totales del Partido
if "puntos_totales" not in df.columns:
    if "puntos_local" in df.columns and "puntos_visitante" in df.columns:
        df["puntos_totales"] = df["puntos_local"] + df["puntos_visitante"]
    else:
        print("❌ El CSV debe contener las columnas `puntos_local` y `puntos_visitante`.")
        sys.exit(1)

# 2. Filtrar columnas no predictivas o dependientes de la variable objetivo
columnas_excluidas = [
    "puntos_totales", "puntos_local", "puntos_visitante",
    "ganador_local", "fecha", "equipo_local", "equipo_visitante"
]
feature_cols = [col for col in df.columns if col not in columnas_excluidas]

X = df[feature_cols].select_dtypes(include=[np.number]).fillna(0)
y = df["puntos_totales"]

# 3. Split de datos
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 4. Entrenamiento del modelo de Regresión
modelo_totales = RandomForestRegressor(n_estimators=150, max_depth=10, random_state=42)
modelo_totales.fit(X_train, y_train)

# 5. Evaluación del modelo
predicciones = modelo_totales.predict(X_test)
mae = mean_absolute_error(y_test, predicciones)

print(f"✅ Modelo de Totales entrenado con éxito.")
print(f"📈 Error Medio Absoluto (MAE): ±{mae:.2f} puntos de margen de error.")

# 6. Guardar modelo en disco
joblib.dump(modelo_totales, "modelo_totales.pkl")
print("💾 Modelo guardado en `modelo_totales.pkl`.")