import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def enviar_alerta_telegram(mensaje):
    """Envía un mensaje de texto formateado en HTML a tu chat de Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Token o Chat ID de Telegram no configurados en .env")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("📱 Alerta enviada a Telegram con éxito.")
            return True
        else:
            print(f"❌ Error enviando a Telegram: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error de conexión con Telegram: {e}")
        return False

if __name__ == "__main__":
    # Prueba de envío
    mensaje_prueba = (
        "🚀 <b>¡Bot de Apuestas Conectado!</b>\n\n"
        "Las notificaciones locales están funcionando correctamente. "
        "Recibirás aquí las alertas de apuestas +EV."
    )
    enviar_alerta_telegram(mensaje_prueba)