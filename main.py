import os
import sys
import subprocess
import threading
import time
from datetime import datetime

# =========================================================
# 🌐 0. SERVIDOR WEB EN SEGUNDO PLANO (REQUERIDO POR RENDER WEB SERVICE)
# =========================================================
from flask import Flask

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot de MLB activo y monitoreando en Render.", 200

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# Iniciar el servidor HTTP en un hilo separado
threading.Thread(target=run_web_server, daemon=True).start()

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
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])

import numpy as np
import requests
import statsapi

# =========================================================
# 📲 2. CONFIGURACIÓN DE TELEGRAM Y PARÁMETROS
# =========================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "TU_BOT_TOKEN_AQUI")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "TU_CHAT_ID_AQUI")
UMBRAL_PROBABILIDAD = 80.0

HISTORIAL_ALERTAS = {}

def enviar_alerta_telegram(mensaje):
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "TU_BOT_TOKEN_AQUI":
        print("\n⚠️ Telegram no configurado. Mensaje:")
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
# 🧮 3. MODELO DE PROBABILIDAD (NRFI)
# =========================================================
def calcular_probabilidad_entrada_limpia(whip, era, ops_proximos_bateadores, pitch_count=0, es_primer_inning=False):
    lambda_base = 0.46
    factor_whip = whip / 1.25 if whip > 0 else 1.0
    factor_era = era / 4.10 if era > 0 else 1.0
    factor_pitcher = (factor_whip * 0.70) + (factor_era * 0.30)

    if isinstance(ops_proximos_bateadores, list) and len(ops_proximos_bateadores) > 0:
        ops_medio = sum(ops_proximos_bateadores) / len(ops_proximos_bateadores)
    else:
        ops_medio = float(ops_proximos_bateadores) if ops_proximos_bateadores else 0.730

    factor_lineup = ops_medio / 0.730
    factor_fatiga = 1.25 if pitch_count > 95 else (1.12 if pitch_count > 80 else 1.0)
    factor_inicio = 1.10 if es_primer_inning else 1.0

    lambda_ajustado = lambda_base * factor_pitcher * factor_lineup * factor_fatiga * factor_inicio
    prob_no_carreras = np.exp(-lambda_ajustado) * 100
    prob_no_carreras = max(30.0, min(90.0, prob_no_carreras))

    return round(prob_no_carreras, 2), round(lambda_ajustado, 3)

# =========================================================
# ⚾ 4. EXTRACCIÓN Y MONITOREO DE INNINGS
# =========================================================
def obtener_ops_proximos_bateadores(game_id, team_offense_type, next_batter_index=1, cantidad=3):
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

            estado_actual = f"{inning_actual}-{half_inning}"
            ultimo_estado = HISTORIAL_ALERTAS.get(game_id)

            if ultimo_estado is None:
                HISTORIAL_ALERTAS[game_id] = estado_actual
                if estado_actual == "1-Top":
                    print(f"🚀 ¡Juego Recién Iniciado! Evaluando NRFI (1er Inning) para {partido_nombre}...")
                else:
                    continue
            elif ultimo_estado == estado_actual:
                continue
            else:
                HISTORIAL_ALERTAS[game_id] = estado_actual

            if half_inning.lower() == 'top':
                siguiente_medio = f"Alta del {inning_actual}°"
                defensa_team = 'home'
                ofensa_team = 'away'
            else:
                siguiente_medio = f"Baja del {inning_actual}°"
                defensa_team = 'away'
                ofensa_team = 'home'

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

            ops_bateadores = obtener_ops_proximos_bateadores(game_id, ofensa_team)
            ops_prom = round(sum(ops_bateadores) / len(ops_bateadores), 3) if ops_bateadores else 0.730

            es_inicio = (inning_actual == 1 and half_inning.lower() == 'top')
            prob_limpia, exp_carreras = calcular_probabilidad_entrada_limpia(
                whip=whip,
                era=era,
                ops_proximos_bateadores=ops_bateadores,
                pitch_count=pitch_count,
                es_primer_inning=es_inicio
            )

            print(f"📊 [{partido_nombre}] {siguiente_medio} | Prob. Limpia: {prob_limpia}%")

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
