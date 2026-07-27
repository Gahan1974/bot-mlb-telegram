
import os
import sys
import subprocess

# =========================================================
# 🌐 0. CONFIGURACIÓN INTELIGENTE DE PROXY
# =========================================================
if 'PYTHONANYWHERE_DOMAIN' in os.environ:
    print("🌐 Entorno detectado: PythonAnywhere. Activando proxy...")
    os.environ['HTTP_PROXY'] = 'http://proxy.server:3128'
    os.environ['HTTPS_PROXY'] = 'http://proxy.server:3128'
else:
    print("💻 Entorno detectado: Local / VPS. Conexión directa a internet sin proxy.")

# =========================================================
# 📦 1. AUTO-INSTALADOR PREVENTIVO DE LIBRERÍAS
# =========================================================
LIBRERIAS = {
    "pandas": "pandas",
    "numpy": "numpy",
    "statsapi": "MLB-StatsAPI",
    "requests": "requests"
}

for mod_name, pip_name in LIBRERIAS.items():
    try:
        __import__(mod_name)
    except ImportError:
        print(f"📦 Instalando paquete faltante: {pip_name}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])

import time
from datetime import datetime
import numpy as np
import requests
import statsapi

# =========================================================
# 📲 2. CONFIGURACIÓN DE TELEGRAM Y PARÁMETROS
# =========================================================
TELEGRAM_BOT_TOKEN = "8608714162:AAF5qgP754_HTwP1LpvkbWnKkSPSwkEpCIQ"
TELEGRAM_CHAT_ID = "1531631680"
UMBRAL_PROBABILIDAD = 80.0  # Alerta solo si P >= 80%

# Diccionario para rastrear el último estado procesado por partido
HISTORIAL_ALERTAS = {}

def enviar_alerta_telegram(mensaje):
    """Envía un mensaje formateado en Markdown a Telegram."""
    if TELEGRAM_BOT_TOKEN == "TU_BOT_TOKEN_AQUI" or not TELEGRAM_BOT_TOKEN:
        print("\n⚠️ Telegram no configurado. Mensaje impreso en consola:")
        print(mensaje)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, data=payload, timeout=10)
        if res.status_code == 200:
            print("📱 ¡Alerta enviada exitosamente a Telegram!")
        else:
            print(f"❌ Error al enviar a Telegram: {res.text}")
    except Exception as e:
        print(f"❌ Excepción en conexión con Telegram: {e}")

# =========================================================
# 🧮 3. MODELO AVANZADO DE PROBABILIDAD DE ENTRADA LIMPIA (NRFI)
# =========================================================
def calcular_probabilidad_entrada_limpia(whip, era, ops_proximos_bateadores, pitch_count=0, es_primer_inning=False):
    """
    Calcula la probabilidad de 0 carreras en el próximo inning
    basado en métricas ajustadas del lanzador y del orden al bat.
    """
    lambda_base = 0.46

    # 1. Ponderación Pitcher (WHIP representa el 70% del peso frente al ERA)
    factor_whip = whip / 1.25 if whip > 0 else 1.0
    factor_era = era / 4.10 if era > 0 else 1.0
    factor_pitcher = (factor_whip * 0.70) + (factor_era * 0.30)

    # 2. Ponderación Bateadores
    if isinstance(ops_proximos_bateadores, list) and len(ops_proximos_bateadores) > 0:
        ops_medio = sum(ops_proximos_bateadores) / len(ops_proximos_bateadores)
    else:
        ops_medio = float(ops_proximos_bateadores) if ops_proximos_bateadores else 0.730

    factor_lineup = ops_medio / 0.730

    # 3. Factor Fatiga (Picheos)
    factor_fatiga = 1.0
    if pitch_count > 95:
        factor_fatiga = 1.25
    elif pitch_count > 80:
        factor_fatiga = 1.12

    # 4. Ajuste 1er Inning (Tope del Lineup 1-2-3)
    factor_inicio = 1.10 if es_primer_inning else 1.0

    # Esperanza matemática ajustada de carreras
    lambda_ajustado = lambda_base * factor_pitcher * factor_lineup * factor_fatiga * factor_inicio

    # Probabilidad mediante Distribución de Poisson: P(X=0) = e^(-lambda)
    prob_no_carreras = np.exp(-lambda_ajustado) * 100
    prob_no_carreras = max(30.0, min(90.0, prob_no_carreras))

    return round(prob_no_carreras, 2), round(lambda_ajustado, 3)

# =========================================================
# ⚾ 4. EXTRACCIÓN Y MONITOREO DE INNINGS
# =========================================================
def obtener_ops_proximos_bateadores(game_id, team_offense_type, next_batter_index=1, cantidad=3):
    """Obtiene el OPS de los bateadores que vendrán a batear."""
    ops_list = []
    try:
        boxscore = statsapi.boxscore_data(game_id)
        team_key = 'home' if team_offense_type == 'home' else 'away'
        lineup = boxscore.get(team_key, {}).get('batters', [])

        if lineup:
            total = len(lineup)
            for i in range(cantidad):
                idx = (next_batter_index - 1 + i) % total
                batter_id = lineup[idx]
                p_data = statsapi.player_stat_data(batter_id, group="hitting", type="season")

                ops = 0.730
                for st in p_data.get('stats', []):
                    if st.get('type') == 'season':
                        ops = float(st.get('stats', {}).get('ops', 0.730))
                        break
                ops_list.append(ops)
    except Exception:
        ops_list = [0.730] * cantidad

    return ops_list

def monitorear_cambios_de_inning():
    """Detecta el inicio del juego (1-Top) y cada finalización de medio inning."""
    fecha_hoy = datetime.now().strftime('%Y-%m-%d')
    print(f"🔍 [{datetime.now().strftime('%H:%M:%S')}] Escaneando partidos en vivo...")

    try:
        juegos = statsapi.schedule(date=fecha_hoy)
    except Exception as e:
        print(f"❌ Error al consultar API de MLB: {e}")
        return

    partidos_en_vivo = [g for g in juegos if g.get('status') == 'In Progress']

    if not partidos_en_vivo:
        print("ℹ️ No hay partidos en vivo actualmente.")
        return

    for juego in partidos_en_vivo:
        game_id = juego['game_id']
        partido_nombre = f"{juego['away_name']} vs {juego['home_name']}"

        try:
            game_data = statsapi.get('game', {'gamePk': game_id})
            live_data = game_data.get('liveData', {})
            linescore = live_data.get('linescore', {})

            inning_actual = linescore.get('currentInning', 1)
            half_inning = linescore.get('inningHalf', 'Top')

            # Identificador del estado actual (Ej: "1-Top", "1-Bottom", "2-Top")
            estado_actual = f"{inning_actual}-{half_inning}"
            ultimo_estado = HISTORIAL_ALERTAS.get(game_id)

            # ---------------------------------------------------------
            # 🎯 LÓGICA DE DETECCIÓN Y PRIMER ESCANEO (NRFI 1er Inning)
            # ---------------------------------------------------------
            if ultimo_estado is None:
                HISTORIAL_ALERTAS[game_id] = estado_actual
                # Si recién inicia el partido (1-Top), forzamos la evaluación inicial
                if estado_actual == "1-Top":
                    print(f"🚀 ¡Juego Recién Iniciado! Evaluando NRFI (1er Inning) para {partido_nombre}...")
                else:
                    # Si el programa se encendió cuando el juego ya iba a la mitad, no spammear
                    continue
            elif ultimo_estado == estado_actual:
                # Sigue jugando el mismo medio inning -> No hacemos nada
                continue
            else:
                # Transición de inning detectada (Terminó un medio inning)
                HISTORIAL_ALERTAS[game_id] = estado_actual

            # Definir defensa y ofensa según el medio inning por iniciar
            if half_inning.lower() == 'top':
                siguiente_medio = f"Alta del {inning_actual}°"
                defensa_team = 'home'
                ofensa_team = 'away'
            else:
                siguiente_medio = f"Baja del {inning_actual}°"
                defensa_team = 'away'
                ofensa_team = 'home'

            # Obtener datos del Lanzador entrante
            boxscore = statsapi.boxscore_data(game_id)
            pitchers_def = boxscore.get(defensa_team, {}).get('pitchers', [])
            pitcher_id = pitchers_def[0] if pitchers_def else None

            pitcher_name = "Lanzador de Turno"
            whip, era, pitch_count = 1.25, 4.10, 0

            if pitcher_id:
                p_stat = statsapi.player_stat_data(pitcher_id, group="pitching", type="season")
                pitcher_name = f"{p_stat.get('first_name', '')} {p_stat.get('last_name', '')}"
                for st in p_stat.get('stats', []):
                    if st.get('type') == 'season':
                        whip = float(st.get('stats', {}).get('whip', 1.25))
                        era = float(st.get('stats', {}).get('era', 4.10))
                        break

            # Bateadores entrantes
            ops_bateadores = obtener_ops_proximos_bateadores(game_id, ofensa_team)
            ops_prom = round(sum(ops_bateadores) / len(ops_bateadores), 3) if ops_bateadores else 0.730

            # Cálculo de probabilidad
            es_inicio = (inning_actual == 1 and half_inning.lower() == 'top')
            prob_limpia, exp_carreras = calcular_probabilidad_entrada_limpia(
                whip=whip,
                era=era,
                ops_proximos_bateadores=ops_bateadores,
                pitch_count=pitch_count,
                es_primer_inning=es_inicio
            )

            print(f"📊 [{partido_nombre}] {siguiente_medio} | Prob. Limpia: {prob_limpia}%")

            # 🚨 ENVIAR ALERTA TELEGRAM (SI ES >= 80%)
            if prob_limpia >= UMBRAL_PROBABILIDAD:
                etiqueta = "🔥 *ALERTA NRFI / ENTRADA LIMPIA*" if es_inicio else "🚨 *ENTRADA LIMPIA POR INICIAR*"
                mensaje = (
                    f"{etiqueta}\n\n"
                    f"🏟️ *Partido:* {partido_nombre}\n"
                    f"📌 *Siguiente Inning:* {siguiente_medio}\n"
                    f"👤 *Pitcher a Lanzar:* {pitcher_name}\n"
                    f"📊 *Métricas Pitcher:* WHIP `{whip}` | ERA `{era}`\n"
                    f"🏏 *OPS Bateadores:* `{ops_prom}`\n\n"
                    f"🎯 *Prob. Entrada Limpia:* `{prob_limpia}%`\n"
                    f"📈 *Expectativa Carreras (λ):* `{exp_carreras}`\n"
                    f"⏰ *Hora:* {datetime.now().strftime('%H:%M:%S')}"
                )
                enviar_alerta_telegram(mensaje)

        except Exception as e:
            print(f"⚠️ Error procesando {partido_nombre}: {e}")

# =========================================================
# 🏁 5. BUCLE DE EJECUCIÓN CONTINUA
# =========================================================
if __name__ == "__main__":
    print("🚀 Bucle de monitoreo iniciado.")
    print("Escaneando estado de partidos cada 30 segundos...\n")
    while True:
        monitorear_cambios_de_inning()
        time.sleep(30)