# lesiones.py
# Diccionario o conector de bajas críticas para la NBA (Temporada 2026)
# Aquí puedes registrar manualmente o mediante API las bajas de última hora de los jugadores All-Star / Titulares clave.

# Estructura: {"Nombre del Equipo": ["Jugador 1", "Jugador 2"]}
BAJAS_ACTUALES = {
    # Ejemplo de estructura. Se actualiza antes de los partidos clave.
    # "Detroit Pistons": ["Cade Cunningham"],
    # "Boston Celtics": ["Jayson Tatum"]
}


def obtener_penalizacion_lesion(equipo_local, equipo_visitante):
    """Calcula un factor de ajuste basado en las bajas de estrellas reportadas."""
    penalizacion_local = 0.0
    penalizacion_visitante = 0.0

    # Si hay bajas registradas para el equipo local, restamos capacidad ofensiva (ej. -2.5 puntos de net rating)
    if equipo_local in BAJAS_ACTUALES and len(BAJAS_ACTUALES[equipo_local]) > 0:
        penalizacion_local = -3.5 * len(BAJAS_ACTUALES[equipo_local])

    if (
        equipo_visitante in BAJAS_ACTUALES
        and len(BAJAS_ACTUALES[equipo_visitante]) > 0
    ):
        penalizacion_visitante = -3.5 * len(BAJAS_ACTUALES[equipo_visitante])

    return penalizacion_local, penalizacion_visitante