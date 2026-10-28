import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, log_loss

# 1. SIMULACIÓN / CARGA DE DATASET HISTÓRICO
# En producción, estos datos se generan leyendo el historial con `nba_api`
def generar_dataset_ejemplo(n_partidos=1000):
    np.random.seed(42)
    
    # Variables predictivas (Features)
    net_rating_diff = np.random.normal(0, 5, n_partidos)       # Diferencia de eficiencia ofensiva/defensiva
    dias_descanso_diff = np.random.choice([-2, -1, 0, 1, 2], n_partidos) # Ventaja de descanso
    efg_pct_diff = np.random.normal(0, 0.04, n_partidos)       # Effective Field Goal %
    es_local = np.random.choice([0, 1], n_partidos)            # Ventaja de campo
    
    # Probabilidad real latente subyacente
    logit = (0.15 * net_rating_diff) + (0.3 * dias_descanso_diff) + (8.0 * efg_pct_diff) + (0.4 * es_local)
    prob_real = 1 / (1 + np.exp(-logit))
    
    # Variable objetivo (1 = Gana equipo local, 0 = Gana visitante)
    resultado = np.random.binomial(1, prob_real)
    
    df = pd.DataFrame({
        'net_rating_diff': net_rating_diff,
        'dias_descanso_diff': dias_descanso_diff,
        'efg_pct_diff': efg_pct_diff,
        'es_local': es_local,
        'resultado': resultado
    })
    return df

# 2. ENTRENAMIENTO DEL MODELO DE MACHINE LEARNING
def entrenar_modelo():
    print("📊 Cargando y preparando dataset histórico...")
    df = generar_dataset_ejemplo(1500)
    
    X = df[['net_rating_diff', 'dias_descanso_diff', 'efg_pct_diff', 'es_local']]
    y = df['resultado']
    
    # Separación entrenamiento (80%) y validación (20%)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    modelo = XGBClassifier(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.05,
        eval_metric='logloss'
    )
    
    modelo.fit(X_train, y_train)
    
    # Evaluación de precisión
    preds_prob = modelo.predict_proba(X_test)[:, 1]
    preds_bin = (preds_prob > 0.5).astype(int)
    
    acc = accuracy_score(y_test, preds_bin)
    loss = log_loss(y_test, preds_prob)
    
    print(f"✅ Modelo entrenado con éxito.")
    print(f"🎯 Accuracy en Test: {acc*100:.2f}%")
    print(f"📉 Log Loss: {loss:.4f}\n")
    
    return modelo

# 3. PREDICCIÓN Y DETECCIÓN DE VALOR (+EV)
def evaluar_partido_nuevo(modelo, datos_partido, cuota_local_casa):
    """
    Compara la probabilidad calculada por la IA contra la cuota ofrecida por la casa.
    """
    # Transformar datos de entrada a DataFrame
    df_partido = pd.DataFrame([datos_partido])
    
    # El modelo predice la probabilidad matemática de victoria (de 0.0 a 1.0)
    prob_modelo = modelo.predict_proba(df_partido)[0][1]
    cuota_justa_modelo = 1 / prob_modelo if prob_modelo > 0 else 999.0
    
    # EV = (Probabilidad_Modelo * (Cuota_Casa - 1)) - (1 - Probabilidad_Modelo)
    ev = (prob_modelo * (cuota_local_casa - 1)) - (1 - prob_modelo)
    
    print("🏀 --- ANÁLISIS DE PARTIDO (NUGGETS vs LAKERS) ---")
    print(f"🧠 Probabilidad estimada por el Modelo: {prob_modelo*100:.1f}%")
    print(f"📐 Cuota Justa según nuestro Modelo: {cuota_justa_modelo:.2f}")
    print(f"🏦 Cuota ofrecida por la Casa de Apuestas: {cuota_local_casa:.2f}")
    
    if ev > 0.04:
        print(f"🚀 ¡APUESTA DETECTADA! Ventaja (+EV): +{ev*100:.2f}%")
    else:
        print(f"❌ Sin ventaja suficiente (EV: {ev*100:.2f}%). No se recomienda apostar.")

if __name__ == "__main__":
    modelo = entrenar_modelo()
    
    # Ejemplo de partido de prueba
    # Denver Nuggets (Local) con +3.2 Net Rating, +1 día de descanso y +2% eFG
    partido_hoy = {
        'net_rating_diff': 3.2,
        'dias_descanso_diff': 1,
        'efg_pct_diff': 0.02,
        'es_local': 1
    }
    
    # Casa de apuestas paga la victoria a 1.85
    evaluar_partido_nuevo(modelo, partido_hoy, cuota_local_casa=1.85)