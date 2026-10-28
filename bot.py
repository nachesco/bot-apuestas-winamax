import os
import requests
import pandas as pd
from dotenv import load_dotenv
from database import registrar_apuesta, obtener_saldo_actual
from telegram_notifier import enviar_alerta_telegram

load_dotenv()
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
SPORT = 'basketball_nba'
REGIONS = 'eu' # Casas de apuestas europeas
MARKETS = 'h2h' # Solo buscaremos apuestas a Ganador del partido

def obtener_cuotas():
    """Descarga las cuotas de The Odds API"""
    if not ODDS_API_KEY:
        print("❌ ERROR: Falta la API Key de The Odds API en .env")
        return None

    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds"
    parametros = {
        "apiKey": ODDS_API_KEY,
        "regions": REGIONS,
        "markets": MARKETS,
        "oddsFormat": "decimal",
        "bookmakers": "pinnacle,bet365,bwin" # Comparamos entre estas
    }

    print("📡 Solicitando cuotas a The Odds API...")
    respuesta = requests.get(url, params=parametros)
    
    if respuesta.status_code != 200:
        print(f"❌ Error en la API: {respuesta.status_code} - {respuesta.text}")
        return None
        
    return respuesta.json()

def calcular_ev_y_apostar(datos_api):
    """Analiza las cuotas buscando +EV (usando Pinnacle como referencia de línea de cierre real)"""
    if not datos_api:
        return
        
    saldo_actual = obtener_saldo_actual()
    apuestas_encontradas = 0
    
    print("📊 Buscando oportunidades +EV...")
    
    for partido in datos_api:
        equipo_local = partido['home_team']
        equipo_visitante = partido['away_team']
        id_partido = f"{equipo_local} vs {equipo_visitante}"
        
        # Extraer cuotas
        cuotas = {}
        for bookmaker in partido.get('bookmakers', []):
            nombre_casa = bookmaker['key']
            for mercado in bookmaker['markets']:
                if mercado['key'] == 'h2h':
                    cuotas[nombre_casa] = {
                        mercado['outcomes'][0]['name']: mercado['outcomes'][0]['price'],
                        mercado['outcomes'][1]['name']: mercado['outcomes'][1]['price']
                    }
        
        # Necesitamos que Pinnacle (la casa más eficiente) esté disponible para calcular la probabilidad real
        if 'pinnacle' not in cuotas:
            continue
            
        for equipo in [equipo_local, equipo_visitante]:
            # Calcular probabilidad "real" según Pinnacle (eliminando el margen de la casa)
            cuota_pinnacle = cuotas['pinnacle'].get(equipo, 0)
            cuota_contraria = cuotas['pinnacle'].get(equipo_local if equipo == equipo_visitante else equipo_visitante, 0)
            
            if cuota_pinnacle == 0 or cuota_contraria == 0:
                continue
                
            prob_implicita_eq = 1 / cuota_pinnacle
            prob_implicita_contra = 1 / cuota_contraria
            margen = prob_implicita_eq + prob_implicita_contra
            prob_real = prob_implicita_eq / margen # Probabilidad purgada del margen
            
            # Buscar si otra casa de apuestas ofrece una cuota mejor (apuesta de valor)
            for casa, datos_casa in cuotas.items():
                if casa == 'pinnacle':
                    continue
                    
                cuota_ofrecida = datos_casa.get(equipo, 0)
                if cuota_ofrecida == 0:
                    continue
                    
                # Fórmula EV: (Prob_Real * Beneficio_Potencial) - (Prob_Perder * 1)
                ev = (prob_real * (cuota_ofrecida - 1)) - ((1 - prob_real) * 1)
                
                # Si el EV es mayor a 0.03 (3% de ventaja), disparamos apuesta
                if ev > 0.03:
                    # Calculamos el tamaño de la apuesta (Kelly fraccionado al 25%)
                    kelly = (((cuota_ofrecida - 1) * prob_real) - (1 - prob_real)) / (cuota_ofrecida - 1)
                    kelly_fraccionado = max(0, kelly * 0.25)
                    stake = min(saldo_actual * kelly_fraccionado, saldo_actual * 0.05) # Tope del 5% del saldo
                    
                    if stake > 1.0: # Apostar solo si el stake es mayor a 1 euro
                        registrar_apuesta(id_partido, f"{equipo} en {casa}", cuota_ofrecida, ev, stake)
                        apuestas_encontradas += 1
                        
                        mensaje_tg = (
                            f"🏀 <b>¡APUESTA +EV DETECTADA!</b>\n\n"
                            f"<b>Partido:</b> {id_partido}\n"
                            f"<b>Selección:</b> {equipo}\n"
                            f"<b>Casa:</b> {casa.capitalize()}\n"
                            f"<b>Cuota:</b> {cuota_ofrecida}\n"
                            f"<b>EV:</b> +{ev*100:.1f}%\n"
                            f"<b>Stake (Recomendado):</b> {stake:.2f} €"
                        )
                        enviar_alerta_telegram(mensaje_tg)

    if apuestas_encontradas == 0:
        print("💤 No se encontraron apuestas +EV en este ciclo.")

if __name__ == "__main__":
    datos = obtener_cuotas()
    calcular_ev_y_apostar(datos)