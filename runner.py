import time
from auto_settle import procesar_apuestas_pendientes
from bot_predictivo import analizar_mercado
import schedule


def ciclo_automatizado():
    print("\n" + "=" * 55)
    print("🚀 EJECUTANDO CICLO AUTOMÁTICO DE ANÁLISIS Y LIQUIDACIÓN")
    print("=" * 55)

    # 1. Comprobar y cerrar apuestas finalizadas
    print("\n1️⃣ Comprobando resultados de partidos finalizados...")
    try:
        procesar_apuestas_pendientes()
    except Exception as e:
        print(f"❌ Error en liquidación automática: {e}")

    # 2. Buscar oportunidades +EV
    print("\n2️⃣ Buscando nuevas apuestas (+EV)...")
    try:
        analizar_mercado()
    except Exception as e:
        print(f"❌ Error en análisis de mercado: {e}")

    print("\n✅ Ciclo finalizado. Esperando 15 minutos...")


if __name__ == "__main__":
    # Ejecución inmediata al arrancar
    ciclo_automatizado()

    # Programar cada 15 minutos
    schedule.every(15).minutes.do(ciclo_automatizado)

    while True:
        schedule.run_pending()
        time.sleep(1)