import time
import pandas as pd
from nba_api.stats.endpoints import leaguegamelog

# Temporadas que utilizaremos para entrenar el modelo
TEMPORADAS = ['2023-24', '2024-25', '2025-26']

def descargar_historial_nba():
    """Descarga todos los partidos de temporada regular de los años seleccionados."""
    partidos_totales = []

    for temporada in TEMPORADAS:
        print(f"📡 Descargando datos de la temporada {temporada}...")
        try:
            # Obtiene el registro completo de partidos de la temporada
            log = leaguegamelog.LeagueGameLog(
                season=temporada, 
                season_type_all_star='Regular Season'
            )
            df_temp = log.get_data_frames()[0]
            partidos_totales.append(df_temp)
            print(f"✅ {len(df_temp)} registros obtenidos.")
            
            # Pausa para evitar bloqueos por tasa de peticiones
            time.sleep(1.5)
        except Exception as e:
            print(f"❌ Error al descargar temporada {temporada}: {e}")

    if not partidos_totales:
        print("❌ No se pudieron obtener datos.")
        return None

    df_raw = pd.concat(partidos_totales, ignore_index=True)
    return df_raw

def procesar_partidos(df):
    """
    Empareja cada fila (que representa a un equipo en un partido)
    para consolidar 1 fila por partido con local, visitante y resultado.
    """
    print("🔄 Procesando y limpiando conjunto de datos...")
    
    # Separar partidos jugados como local y como visitante
    # En la columna 'MATCHUP', los locales tienen 'vs.' y los visitantes '@'
    df_local = df[df['MATCHUP'].str.contains('vs.')].copy()
    df_visitante = df[df['MATCHUP'].str.contains('@')].copy()

    # Unir ambas tablas usando el ID único del partido
    df_merged = pd.merge(
        df_local,
        df_visitante,
        on='GAME_ID',
        suffixes=('_LOCAL', '_VISITANTE')
    )

    # Crear dataset estructurado
    df_limpio = pd.DataFrame({
        'game_id': df_merged['GAME_ID'],
        'fecha': df_merged['GAME_DATE_LOCAL'],
        'equipo_local': df_merged['TEAM_NAME_LOCAL'],
        'equipo_visitante': df_merged['TEAM_NAME_VISITANTE'],
        'puntos_local': df_merged['PTS_LOCAL'],
        'puntos_visitante': df_merged['PTS_VISITANTE'],
        'puntos_totales': df_merged['PTS_LOCAL'] + df_merged['PTS_VISITANTE'],
        'diferencia_puntos': df_merged['PTS_LOCAL'] - df_merged['PTS_VISITANTE'],
        'gana_local': (df_merged['PTS_LOCAL'] > df_merged['PTS_VISITANTE']).astype(int),
        'fg_pct_local': df_merged['FG_PCT_LOCAL'],
        'fg_pct_visitante': df_merged['FG_PCT_VISITANTE'],
        'reb_local': df_merged['REB_LOCAL'],
        'reb_visitante': df_merged['REB_VISITANTE'],
        'ast_local': df_merged['AST_LOCAL'],
        'ast_visitante': df_merged['AST_VISITANTE'],
        'tov_local': df_merged['TOV_LOCAL'],
        'tov_visitante': df_merged['TOV_VISITANTE']
    })

    # Guardar en CSV local
    archivo_salida = "datos_historicos_nba.csv"
    df_limpio.to_csv(archivo_salida, index=False)
    print(f"💾 ¡Hecho! Dataset guardado en `{archivo_salida}` ({len(df_limpio)} partidos procesados).")
    return df_limpio

if __name__ == "__main__":
    df_raw = descargar_historial_nba()
    if df_raw is not None:
        procesar_partidos(df_raw)