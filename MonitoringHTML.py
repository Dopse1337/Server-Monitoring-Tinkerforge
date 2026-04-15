#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║        Serverraum-Überwachung – Komplettversion              ║
╚══════════════════════════════════════════════════════════════╝
"""

import time
import threading
import smtplib
import requests
import json
import urllib3
from email.mime.text import MIMEText

# Unterdrückt SSL-Warnungen wegen verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from tinkerforge.ip_connection import IPConnection
from tinkerforge.bricklet_ptc_v2 import BrickletPTCV2
from tinkerforge.bricklet_ambient_light_v3 import BrickletAmbientLightV3
from tinkerforge.bricklet_humidity_v2 import BrickletHumidityV2
from tinkerforge.bricklet_motion_detector_v2 import BrickletMotionDetectorV2
from tinkerforge.bricklet_nfc import BrickletNFC
from tinkerforge.bricklet_dual_button_v2 import BrickletDualButtonV2
from tinkerforge.bricklet_rgb_led_button import BrickletRGBLEDButton
from tinkerforge.bricklet_piezo_speaker_v2 import BrickletPiezoSpeakerV2
from tinkerforge.bricklet_e_paper_296x128 import BrickletEPaper296x128
from tinkerforge.bricklet_segment_display_4x7_v2 import BrickletSegmentDisplay4x7V2
from tinkerforge.bricklet_lcd_128x64 import BrickletLCD128x64

# ══════════════════════════════════════════════════════════════════════════════
# KONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

HOST = "172.20.10.242"
PORT = 4223

# Dashboard Konfiguration
DASHBOARD_URL = "https://ais-dev-etxhd7eu4verifxhxvdjme-91545401271.europe-west2.run.app/api/update"

# UIDs
UID_PTC      = "Wcg"
UID_LIGHT    = "Pdw"
UID_HUMIDITY = "ViW"
UID_MOTION   = "ML4"
UID_NFC      = "22ND"
UID_DUALBT   = "Vd8"
UID_RGBLED   = "23Qx"
UID_PIEZO    = "R7M"
UID_EPAPER   = "24KJ"
UID_SEGMENT  = "Tre"
UID_LCD      = "24Rh"

# Schwellwerte
TEMP_WARN   = 26.0
TEMP_CRIT   = 32.0
TEMP_LOW    = 15.0
HUMID_WARN  = 60.0
HUMID_CRIT  = 75.0
HUMID_LOW   = 20.0

POLL_INTERVAL = 2.0
MUTE_GLOBAL   = False

# E-Mail
EMAIL_AN = ["eliaskramer3@gmail.com", "vincent.bruegge1@gmail.com"]
EMAIL_VON        = "forgetinker@gmail.com"
EMAIL_PASSWORT   = "sffdrmrvdfyoxqnc"
SMTP_SERVER      = "smtp.gmail.com"
SMTP_PORT        = 587
EMAIL_COOLDOWN_S = 300

# ══════════════════════════════════════════════════════════════════════════════
# SYSTEMZUSTAND
# ══════════════════════════════════════════════════════════════════════════════
state = {
    "aktiv":           True,
    "alarm":           False,
    "alarm_quittiert": False,
    "mute":            False,
    "zustand":         "OK",
    "temp":            0.0,
    "humidity":        0.0,
    "lux":             0.0,
    "motion":          False,
    "letzte_email":    0.0,
}

lock = threading.Lock()
nfc_bricklet = None
nfc_letzter_scan = 0.0

# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD SYNC
# ══════════════════════════════════════════════════════════════════════════════

def sync_with_dashboard():
    global state
    with lock:
        payload = {
            "temp": round(state["temp"], 2),
            "humidity": round(state["humidity"], 2),
            "lux": round(state["lux"], 2),
            "motion": state["motion"],
            "aktiv": state["aktiv"],
            "alarm": state["alarm"],
            "alarm_quittiert": state["alarm_quittiert"],
            "mute": state["mute"],
            "zustand": state["zustand"]
        }
    try:
        # verify=False wegen deines Zertifikatsfehlers
        response = requests.post(DASHBOARD_URL, json=payload, timeout=3, verify=False)
        if response.status_code == 200:
            res_json = response.json()
            remote_cmd = res_json.get("current_state", {})
            if remote_cmd:
                with lock:
                    if "mute" in remote_cmd: state["mute"] = remote_cmd["mute"]
                    if "alarm_quittiert" in remote_cmd: state["alarm_quittiert"] = remote_cmd["alarm_quittiert"]
    except Exception as e:
        print(f"  [Dashboard] Fehler: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# HILFSFUNKTIONEN (BERECHNUNG & MAIL)
# ══════════════════════════════════════════════════════════════════════════════

def zustand_berechnen(temp, humidity):
    if temp >= TEMP_CRIT or temp <= TEMP_LOW or humidity >= HUMID_CRIT:
        return "KRITISCH"
    if temp >= TEMP_WARN or humidity >= HUMID_WARN or humidity <= HUMID_LOW:
        return "WARNUNG"
    return "OK"

def rgb_fuer_zustand(zustand):
    return {"OK": (0, 255, 0), "WARNUNG": (255, 165, 0), "KRITISCH": (255, 0, 0)}.get(zustand, (0, 0, 255))

def sende_alarm_email(snap):
    jetzt = time.time()
    if jetzt - snap["letzte_email"] < EMAIL_COOLDOWN_S:
        return

    zeitstempel = time.strftime("%d.%m.%Y %H:%M:%S")
    betreff = f"[{snap['zustand']}] Serverraum-Alarm – {zeitstempel}"
    inhalt = (
        f"Serverraum-Überwachung – {snap['zustand']}\n\n"
        f"Zeitpunkt        : {zeitstempel}\n"
        f"Temperatur       : {snap['temp']:.1f} °C\n"
        f"Luftfeuchtigkeit : {snap['humidity']:.1f} %RH\n"
        f"Helligkeit       : {snap['lux']:.0f} lx\n"
        f"Bewegung         : {'JA' if snap['motion'] else 'NEIN'}\n"
    )

    try:
        msg = MIMEText(inhalt, "plain", "utf-8")
        msg["From"], msg["To"], msg["Subject"] = EMAIL_VON, ", ".join(EMAIL_AN), betreff
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(EMAIL_VON, EMAIL_PASSWORT)
            server.sendmail(EMAIL_VON, EMAIL_AN, msg.as_string())
        with lock: state["letzte_email"] = jetzt
        print("  [Email] Erfolgreich gesendet.")
    except Exception as e:
        print(f"  [Email] Fehler: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════

def cb_motion_detected():
    with lock: state["motion"] = True
    print("  [Motion] Bewegung!")

def cb_motion_ended():
    with lock: state["motion"] = False

def cb_button_state_changed(button_l, button_r, led_l, led_r):
    if button_l == BrickletDualButtonV2.BUTTON_STATE_PRESSED:
        with lock: state["mute"] = not state["mute"]
    if button_r == BrickletDualButtonV2.BUTTON_STATE_PRESSED:
        with lock: 
            state["alarm"] = False
            state["alarm_quittiert"] = True

def cb_nfc_reader_state_changed(reader_state, idle):
    global nfc_letzter_scan
    if reader_state == BrickletNFC.READER_STATE_IDLE:
        nfc_bricklet.reader_request_tag_id()
    elif reader_state == BrickletNFC.READER_STATE_REQUEST_TAG_ID_READY:
        jetzt = time.time()
        if jetzt - nfc_letzter_scan > 2.0:
            nfc_letzter_scan = jetzt
            with lock:
                if state["zustand"] != "OK":
                    state["alarm"], state["alarm_quittiert"] = False, True
                else:
                    state["aktiv"] = not state["aktiv"]
        nfc_bricklet.reader_request_tag_id()

# ══════════════════════════════════════════════════════════════════════════════
# AKTOREN (HARDWARE ANSTEUERUNG)
# ══════════════════════════════════════════════════════════════════════════════

def update_rgb(rgb_btn, zustand, aktiv):
    if not aktiv:
        rgb_btn.set_color(0, 0, 50)
    else:
        r, g, b = rgb_fuer_zustand(zustand)
        rgb_btn.set_color(r, g, b)

def update_piezo(piezo, zustand, quittiert, mute, aktiv):
    if not aktiv or mute or quittiert or zustand == "OK":
        piezo.set_beep(1000, 2, BrickletPiezoSpeakerV2.BEEP_DURATION_OFF)
    elif zustand == "KRITISCH":
        piezo.set_alarm(800, 2400, 200, 30, 2, BrickletPiezoSpeakerV2.ALARM_DURATION_INFINITE)
    elif zustand == "WARNUNG":
        piezo.set_beep(1200, 2, 300)

def update_segment(seg):
    h, m = int(time.strftime("%H")), int(time.strftime("%M"))
    seg.set_numeric_value([h // 10, h % 10, m // 10, m % 10])

def update_lcd(lcd, s):
    lcd.clear_display()
    lcd.write_line(0, 0, "== Serverraum ==")
    lcd.write_line(1, 0, f"Temp:   {s['temp']:5.1f} C")
    lcd.write_line(2, 0, f"Feuch:  {s['humidity']:5.1f} %")
    lcd.write_line(3, 0, f"Status: {s['zustand']}")
    lcd.write_line(7, 0, time.strftime("%H:%M:%S"))

def update_epaper(ep, s):
    ep.fill_display(BrickletEPaper296x128.COLOR_WHITE)
    ep.draw_text(5, 5, 2, 0, 0, "Serverraum-Monitor") # FONT_12X16 = 2
    farbe = 3 if s["zustand"] != "OK" else 0 # COLOR_RED=3, BLACK=0
    ep.draw_text(5, 28, 4, farbe, 0, s["zustand"]) # FONT_18X32 = 4
    ep.draw_text(5, 68, 2, 0, 0, f"T: {s['temp']:.1f}C  H: {s['humidity']:.1f}%")
    ep.draw()

# ══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ipcon = IPConnection()
    
    # Init Bricklets
    ptc = BrickletPTCV2(UID_PTC, ipcon)
    light = BrickletAmbientLightV3(UID_LIGHT, ipcon)
    humidity = BrickletHumidityV2(UID_HUMIDITY, ipcon)
    motion = BrickletMotionDetectorV2(UID_MOTION, ipcon)
    global nfc_bricklet
    nfc_bricklet = BrickletNFC(UID_NFC, ipcon)
    dualbt = BrickletDualButtonV2(UID_DUALBT, ipcon)
    rgb_btn = BrickletRGBLEDButton(UID_RGBLED, ipcon)
    piezo = BrickletPiezoSpeakerV2(UID_PIEZO, ipcon)
    epaper = BrickletEPaper296x128(UID_EPAPER, ipcon)
    segment = BrickletSegmentDisplay4x7V2(UID_SEGMENT, ipcon)
    lcd = BrickletLCD128x64(UID_LCD, ipcon)

    ipcon.connect(HOST, PORT)

    # Callbacks
    motion.register_callback(BrickletMotionDetectorV2.CALLBACK_MOTION_DETECTED, cb_motion_detected)
    motion.register_callback(BrickletMotionDetectorV2.CALLBACK_DETECTION_CYCLE_ENDED, cb_motion_ended)
    dualbt.register_callback(BrickletDualButtonV2.CALLBACK_STATE_CHANGED, cb_button_state_changed)
    dualbt.set_state_changed_callback_configuration(True)
    nfc_bricklet.set_mode(BrickletNFC.MODE_READER)
    nfc_bricklet.register_callback(BrickletNFC.CALLBACK_READER_STATE_CHANGED, cb_nfc_reader_state_changed)
    nfc_bricklet.reader_request_tag_id()
    lcd.set_display_configuration(14, 100, False, True)

    letzter_zustand = None
    letzter_epaper_update = 0

    try:
        while True:
            # 1. Sensoren auslesen
            t = ptc.get_temperature() / 100.0
            lux = light.get_illuminance() / 100.0
            hum = humidity.get_humidity() / 100.0
            z = zustand_berechnen(t, hum)

            # 2. State aktualisieren
            with lock:
                state.update({"temp": t, "lux": lux, "humidity": hum, "zustand": z})
                if z != "OK" and not state["alarm_quittiert"]:
                    state["alarm"] = True
                elif z == "OK":
                    state["alarm"], state["alarm_quittiert"] = False, False
                snap = dict(state)

            # 3. Hardware Updates
            update_rgb(rgb_btn, z, snap["aktiv"])
            update_piezo(piezo, z, snap["alarm_quittiert"], snap["mute"], snap["aktiv"])
            update_segment(segment)
            update_lcd(lcd, snap)
            
            # E-Paper (nur bei Änderung oder alle 60s)
            jetzt = time.time()
            if z != letzter_zustand or jetzt - letzter_epaper_update > 60:
                threading.Thread(target=update_epaper, args=(epaper, snap), daemon=True).start()
                letzter_zustand, letzter_epaper_update = z, jetzt

            # 4. Dashboard & Email Sync (Threads verhindern Verzögerung)
            threading.Thread(target=sync_with_dashboard, daemon=True).start()
            
            if z == "KRITISCH" and not snap["alarm_quittiert"]:
                threading.Thread(target=sende_alarm_email, args=(snap,), daemon=True).start()

            # Dual-Button LEDs
            led_l = 1 if snap["mute"] else 0
            led_r = 1 if snap["alarm_quittiert"] else 0
            dualbt.set_led_state(led_l, led_r)

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nBeende...")
    finally:
        ipcon.disconnect()

if __name__ == "__main__":
    main()
