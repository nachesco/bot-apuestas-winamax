import os
import sqlite3
import subprocess
import sys
import pandas as pd
import streamlit as st

# --- CONFIGURACIÓN DE PÁGINA Y CONSTANTES ---
st.set_page_config(
    page_title="Bot Multi-Deporte (NBA & Fútbol) - Winamax",
    page_icon="🏀⚽",
    layout="wide"
)

DB_PATH = "apuestas.db"
BANKROLL_INICIAL = 20.0  # Saldo real inicial en Winamax
LOG_BOT = "logs_bot.txt"

# --- FUNCIONES DE BASE DE DATOS Y MÉTRICAS ---
def cargar_datos_apuestas():
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    query = "SELECT * FROM apuestas ORDER BY id DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def obtener_metricas_saldo():
    if not os.path.exists(DB_PATH):
        return BANKROLL_INICIAL, 0.0, BANKROLL_INICIAL, 0.0, 0, 0, 0, 0.0
    
    conn = sqlite3.connect(DB_PATH)
    
    df_pnl = pd.read_sql_query("SELECT SUM(pnl) as total_pnl FROM apuestas WHERE estado != 'PENDIENTE'", conn)
    pnl_total = df_pnl['total_pnl'].values[0] if not df_pnl.empty and pd.notna(df_pnl['total_pnl'].values[0]) else 0.0
    
    df_pendientes = pd.read_sql_query("SELECT SUM(stake) as total_pendientes FROM apuestas WHERE estado = 'PENDIENTE'", conn)
    stake_pendiente = df_pendientes['total_pendientes'].values[0] if not df_pendientes.empty and pd.notna(df_pendientes['total_pendientes'].values[0]) else 0.0
    
    df_counts = pd.read_sql_query("SELECT estado, COUNT(*) as count FROM apuestas GROUP BY estado", conn)
    counts = dict(zip(df_counts['estado'], df_counts['count'])) if not df_counts.empty else {}
    
    ganadas = counts.get('GANADA', 0)
    perdidas = counts.get('PERDIDA', 0)
    pendientes = counts.get('PENDIENTE', 0)
    
    total_resueltas = ganadas + perdidas
    win_rate = (ganadas / total_resueltas * 100) if total_resueltas > 0 else 0.0
    
    conn.close()
    
    saldo_total = BANKROLL_INICIAL + pnl_total
    saldo_disponible = max(0.0, saldo_total - stake_pendiente)
    
    return saldo_total, stake_pendiente, saldo_disponible, pnl_total, ganadas, perdidas, pendientes, win_rate

def ejecutar_script(script_name):
    try:
        resultado = subprocess.run([sys.executable, script_name], capture_output=True, text=True, check=True)
        return True, resultado.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

# --- BARRA LATERAL (ACCIONES Y CONTROLES) ---
st.sidebar.title("🤖 Controles del Bot")

st.sidebar.subheader("🏀 Baloncesto (NBA)")
if st.sidebar.button("🚀 Escanear NBA", use_container_width=True):
    with st.spinner("Escaneando mercado NBA en Winamax..."):
        exito, output = ejecutar_script("bot_predictivo.py")
        if exito:
            st.sidebar.success("Escaneo NBA completado.")
            st.rerun()
        else:
            st.sidebar.error(f"Error en NBA: {output}")

st.sidebar.subheader("⚽ Fútbol (LaLiga & Premier)")
if st.sidebar.button("⚽ Escanear Fútbol", use_container_width=True):
    with st.spinner("Escaneando LaLiga y Premier League..."):
        exito, output = ejecutar_script("bot_futbol.py")
        if exito:
            st.sidebar.success("Escaneo Fútbol completado.")
            st.rerun()
        else:
            st.sidebar.error(f"Error en Fútbol: {output}")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Liquidar Apuestas Pendientes", use_container_width=True):
    with st.spinner("Verificando resultados en API..."):
        exito, output = ejecutar_script("liquidador.py")
        if exito:
            st.sidebar.success("Liquidación completada.")
            st.rerun()
        else:
            st.sidebar.error(f"Error al liquidar: {output}")

st.sidebar.markdown("---")
st.sidebar.caption("🏢 **Casa:** Winamax (EU)")
st.sidebar.caption(f"💰 **Bankroll Base:** {BANKROLL_INICIAL:.2f} €")
st.sidebar.caption("🎯 **Estrategia:** 25% Kelly | Max 3% Stake")

# --- CABECERA Y MÉTRICAS DE SALDO Y BANCO ---
st.title("📊 Panel de Control Multi-Deporte (NBA & Fútbol)")

saldo_total, stake_pendiente, saldo_disponible, pnl_total, ganadas, perdidas, pendientes, win_rate = obtener_metricas_saldo()

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="💵 Saldo Total (Bankroll)",
        value=f"{saldo_total:.2f} €",
        delta=f"{pnl_total:+.2f} € P&L"
    )

with col2:
    st.metric(
        label="🔓 Saldo Disponible",
        value=f"{saldo_disponible:.2f} €"
    )

with col3:
    st.metric(
        label="⏳ En Apuestas Pendientes",
        value=f"{stake_pendiente:.2f} €"
    )

with col4:
    st.metric(
        label="📈 Beneficio Neto (P&L)",
        value=f"{pnl_total:.2f} €",
        delta=f"{win_rate:.1f}% Win Rate" if (ganadas + perdidas) > 0 else "0.0% Win Rate"
    )

st.markdown("---")

# --- LISTADO Y PESTAÑAS DE APUESTAS ---
df_apuestas = cargar_datos_apuestas()

if df_apuestas.empty:
    st.info("ℹ️ No hay apuestas registradas en la base de datos aún. Utiliza los botones de la barra lateral para escanear partidos de la NBA o de Fútbol.")
else:
    tab1, tab2, tab3, tab4 = st.tabs([
        f"⏳ Pendientes ({pendientes})",
        f"✅ Ganadas ({ganadas})",
        f"❌ Perdidas ({perdidas})",
        "📊 Histórico Completo"
    ])

    cols = list(df_apuestas.columns)
    columnas_mostrar = [c for c in ['id', 'deporte', 'id_partido', 'seleccion', 'cuota', 'ev', 'stake', 'estado', 'resultado', 'fecha_partido', 'casa', 'pnl'] if c in cols]

    with tab1:
        st.subheader("Apuestas Pendientes de Resolución")
        df_pend = df_apuestas[df_apuestas['estado'] == 'PENDIENTE']
        if df_pend.empty:
            st.write("No hay apuestas pendientes en este momento.")
        else:
            st.dataframe(df_pend[columnas_mostrar], use_container_width=True)

    with tab2:
        st.subheader("Historial de Apuestas Ganadas")
        df_gan = df_apuestas[df_apuestas['estado'] == 'GANADA']
        if df_gan.empty:
            st.write("No hay apuestas ganadas todavía.")
        else:
            st.dataframe(df_gan[columnas_mostrar], use_container_width=True)

    with tab3:
        st.subheader("Historial de Apuestas Perdidas")
        df_per = df_apuestas[df_apuestas['estado'] == 'PERDIDA']
        if df_per.empty:
            st.write("No hay apuestas perdidas todavía.")
        else:
            st.dataframe(df_per[columnas_mostrar], use_container_width=True)

    with tab4:
        st.subheader("Registro Completo de Operaciones")
        st.dataframe(df_apuestas[columnas_mostrar], use_container_width=True)

# --- SECCIÓN DE REGISTROS / LOGS DEL SISTEMA ---
st.markdown("---")
with st.expander("🛠️ Ver Registros del Sistema (Logs y Estado de Scripts)"):
    if os.path.exists(LOG_BOT):
        with open(LOG_BOT, "r", encoding="utf-8") as f:
            logs = f.read()
        st.text_area("Consola de Logs", logs, height=150)
    else:
        st.write("No hay archivo de logs activo. Los scripts se ejecutan de manera independiente mediante subprocess.")