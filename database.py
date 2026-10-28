import sqlite3
import struct

DB_PATH = "apuestas.db"


def limpiar_flotante(valor, defecto=0.0) -> float:
    """Convierte de forma segura bytes, BLOBs, textos o números a float sin fallar."""
    if valor is None:
        return defecto
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, bytes):
        try:
            if len(valor) == 4:
                return round(struct.unpack("<f", valor)[0], 2)
            elif len(valor) == 8:
                return round(struct.unpack("<d", valor)[0], 2)
            return float(valor.decode("utf-8", errors="ignore"))
        except Exception:
            return defecto
    try:
        return float(valor)
    except (ValueError, TypeError):
        return defecto


def obtener_conexion():
    """Retorna una conexión activa a la base de datos SQLite."""
    return sqlite3.connect(DB_PATH)


def inicializar_db():
    """Crea e inspecciona las tablas garantizando que todas las columnas necesarias existan."""
    conn = obtener_conexion()
    cursor = conn.cursor()

    # 1. Tabla de apuestas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS apuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_partido TEXT,
            casa TEXT,
            seleccion TEXT,
            cuota REAL,
            stake REAL,
            ev REAL,
            prob REAL,
            estado TEXT DEFAULT 'PENDIENTE',
            resultado REAL DEFAULT 0.0,
            fecha_partido TEXT
        )
    """)

    # Inspeccionar columnas existentes e incorporar automáticamente las que falten
    cursor.execute("PRAGMA table_info(apuestas)")
    cols_existentes = [info[1] for info in cursor.fetchall()]

    columnas_necesarias = {
        "casa": "TEXT",
        "fecha_partido": "TEXT",
        "ev": "REAL",
        "prob": "REAL",
        "resultado": "REAL DEFAULT 0.0",
    }

    for col, tipo in columnas_necesarias.items():
        if col not in cols_existentes:
            try:
                cursor.execute(f"ALTER TABLE apuestas ADD COLUMN {col} {tipo}")
            except Exception:
                pass

    # 2. Tabla de bankroll
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bankroll (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            saldo REAL NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM bankroll")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO bankroll (saldo) VALUES (1000.0)")

    conn.commit()
    conn.close()


def obtener_saldo_actual() -> float:
    """Obtiene el último saldo registrado en la tabla bankroll (o banco)."""
    conn = obtener_conexion()
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tablas = [t[0] for t in cursor.fetchall()]
    tabla_bankroll = "bankroll" if "bankroll" in tablas else "banco"

    cursor.execute(
        f"SELECT saldo FROM {tabla_bankroll} ORDER BY id DESC LIMIT 1"
    )
    fila = cursor.fetchone()
    conn.close()

    if fila and fila[0] is not None:
        return limpiar_flotante(fila[0], defecto=1000.0)
    return 1000.0


def obtener_exposicion_pendiente() -> float:
    """Calcula la suma total del dinero (stake) comprometido en apuestas PENDIENTE."""
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT stake FROM apuestas WHERE estado = 'PENDIENTE'")
    filas = cursor.fetchall()
    conn.close()

    total_exposicion = sum(limpiar_flotante(f[0], defecto=0.0) for f in filas)
    return round(total_exposicion, 2)


def existe_apuesta_pendiente(id_partido: str, seleccion: str) -> bool:
    """Comprueba si ya existe una apuesta activa PENDIENTE para el mismo partido y selección."""
    conn = obtener_conexion()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(apuestas)")
    cols = [info[1] for info in cursor.fetchall()]
    col_p = next(
        (c for c in ["id_partido", "partido", "evento"] if c in cols),
        "id_partido",
    )
    col_s = next(
        (c for c in ["seleccion", "mercado", "opcion"] if c in cols), "seleccion"
    )

    query = f"""
        SELECT COUNT(*) 
        FROM apuestas 
        WHERE {col_p} = ? AND {col_s} = ? AND estado = 'PENDIENTE'
    """
    cursor.execute(query, (id_partido, seleccion))
    count = cursor.fetchone()[0]
    conn.close()

    return count > 0


def registrar_apuesta(
    id_partido: str,
    casa: str,
    seleccion: str,
    cuota: float,
    stake: float,
    ev: float,
    prob: float,
    fecha_partido: str = None,
):
    """Inserta una nueva apuesta recomendada por la IA en la base de datos."""
    conn = obtener_conexion()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO apuestas (id_partido, casa, seleccion, cuota, stake, ev, prob, estado, fecha_partido)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDIENTE', ?)
    """,
        (
            str(id_partido),
            str(casa),
            str(seleccion),
            float(cuota),
            float(stake),
            float(ev),
            float(prob),
            str(fecha_partido) if fecha_partido else None,
        ),
    )

    conn.commit()
    conn.close()


# Auto-inicializar la estructura de las tablas al importar el módulo
inicializar_db()