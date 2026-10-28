import sqlite3

DB_PATH = "apuestas.db"


def limpiar_base_de_datos():
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  # Borramos todos los registros de apuestas anteriores
  cursor.execute("DELETE FROM apuestas")
  conn.commit()
  conn.close()
  print(
      "✅ ¡Base de datos limpiada con éxito! Todas las apuestas de prueba han"
      " sido eliminadas."
  )
  print(
      "💰 Tu bankroll vuelve a estar limpio en 1000.00 € para empezar desde"
      " cero."
  )


if __name__ == "__main__":
  limpiar_base_de_datos()