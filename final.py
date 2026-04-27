#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║       Serverraum-Überwachung – Hauptscript                   ║
╚══════════════════════════════════════════════════════════════╝
"""

import time
import threading
import smtplib
from email.mime.text import MIMEText

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

TEMP_WARN   = 26.0
TEMP_CRIT   = 32.0
TEMP_LOW    = 15.0

HUMID_WARN  = 60.0
HUMID_CRIT  = 75.0
HUMID_LOW   = 20.0

POLL_INTERVAL    = 2.0
MUTE             = False

EMAIL_AN = [
    "eliaskramer3@gmail.com",
    "vincent.bruegge1@gmail.com"
]
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

lock             = threading.Lock()
nfc_bricklet     = None
nfc_letzter_scan = 0.0


# ══════════════════════════════════════════════════════════════════════════════
# HILFSFUNKTIONEN
# ══════════════════════════════════════════════════════════════════════════════
def zustand_berechnen(temp, humidity):
    if temp >= TEMP_CRIT or temp <= TEMP_LOW or humidity >= HUMID_CRIT:
        return "KRITISCH"
    if temp >= TEMP_WARN or humidity >= HUMID_WARN or humidity <= HUMID_LOW:
        return "WARNUNG"
    return "OK"


def rgb_fuer_zustand(zustand):
    return {
        "OK":       (0, 255, 0),
        "WARNUNG":  (255, 165, 0),
        "KRITISCH": (255, 0, 0),
    }.get(zustand, (0, 0, 255))


# ══════════════════════════════════════════════════════════════════════════════
# E-MAIL
# ══════════════════════════════════════════════════════════════════════════════
def sende_alarm_email(snap):
    jetzt = time.time()
    vergangen = jetzt - snap["letzte_email"]
    if vergangen < EMAIL_COOLDOWN_S:
        verbleibend = int(EMAIL_COOLDOWN_S - vergangen)
        print(f"  [Email] Cooldown aktiv – naechste Mail in {verbleibend}s")
        return

    zeitstempel = time.strftime("%d.%m.%Y %H:%M:%S")
    betreff = f"[{snap['zustand']}] Serverraum-Alarm – {zeitstempel}"
    inhalt = (
        f"Serverraum-Überwachung – {snap['zustand']}\n\n"
        f"Zeitpunkt        : {zeitstempel}\n"
        f"Temperatur       : {snap['temp']:.1f} °C"
        f"  (Warnung >= {TEMP_WARN}°C | Kritisch >= {TEMP_CRIT}°C)\n"
        f"Luftfeuchtigkeit : {snap['humidity']:.1f} %RH"
        f"  (Warnung >= {HUMID_WARN}% | Kritisch >= {HUMID_CRIT}%)\n"
        f"Helligkeit       : {snap['lux']:.0f} lx\n"
        f"Bewegung         : {'JA' if snap['motion'] else 'NEIN'}\n\n"
        f"Bitte Serverraum umgehend überprüfen!\n"
        f"Nächste Mail frühestens in {EMAIL_COOLDOWN_S // 60} Minuten."
    )
    print(f"  [Email] Verbinde mit {SMTP_SERVER}:{SMTP_PORT} ...")
    try:
        msg            = MIMEText(inhalt, "plain", "utf-8")
        msg["From"]    = EMAIL_VON
        msg["To"]      = ", ".join(EMAIL_AN)
        msg["Subject"] = betreff
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(EMAIL_VON, EMAIL_PASSWORT)
            server.sendmail(EMAIL_VON, EMAIL_AN, msg.as_string())
        with lock:
            state["letzte_email"] = jetzt
        print(f"  [Email] Erfolgreich gesendet an {', '.join(EMAIL_AN)}")
    except smtplib.SMTPAuthenticationError:
        print("  [Email] FEHLER: Login fehlgeschlagen – App-Passwort pruefen!")
    except smtplib.SMTPException as e:
        print(f"  [Email] SMTP-FEHLER: {e}")
    except Exception as e:
        print(f"  [Email] FEHLER: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ══════════════════════════════════════════════════════════════════════════════
def cb_motion_detected():
    with lock:
        state["motion"] = True
    print("  [Motion] Bewegung erkannt!")

def cb_motion_ended():
    with lock:
        state["motion"] = False
    print("  [Motion] Keine Bewegung mehr.")

def cb_button_state_changed(button_l, button_r, led_l, led_r):
    if button_l == BrickletDualButtonV2.BUTTON_STATE_PRESSED:
        with lock:
            state["mute"] = not state["mute"]
        print(f"  [DualButton] Piezo {'STUMM' if state['mute'] else 'AN'} (linker Button)")
    if button_r == BrickletDualButtonV2.BUTTON_STATE_PRESSED:
        with lock:
            state["alarm"]           = False
            state["alarm_quittiert"] = True
        print("  [DualButton] Alarm quittiert (rechter Button)")

def cb_nfc_reader_state_changed(reader_state, idle):
    global nfc_letzter_scan
    if reader_state == BrickletNFC.READER_STATE_IDLE:
        nfc_bricklet.reader_request_tag_id()
    elif reader_state == BrickletNFC.READER_STATE_REQUEST_TAG_ID_READY:
        jetzt = time.time()
        if jetzt - nfc_letzter_scan < 2.0:
            nfc_bricklet.reader_request_tag_id()
            return
        nfc_letzter_scan = jetzt
        with lock:
            aktueller_zustand = state["zustand"]
            if aktueller_zustand in ("KRITISCH", "WARNUNG"):
                state["alarm"]           = False
                state["alarm_quittiert"] = True
                print(f"  [NFC] Alarm quittiert (Zustand war: {aktueller_zustand})")
            else:
                state["aktiv"] = not state["aktiv"]
                print(f"  [NFC] System {'AKTIVIERT' if state['aktiv'] else 'DEAKTIVIERT'}")
        nfc_bricklet.reader_request_tag_id()
    elif reader_state == BrickletNFC.READER_STATE_REQUEST_TAG_ID_ERROR:
        nfc_bricklet.reader_request_tag_id()


# ══════════════════════════════════════════════════════════════════════════════
# AKTOREN
# ══════════════════════════════════════════════════════════════════════════════
def update_rgb(rgb_btn, zustand):
    try:
        r, g, b = rgb_fuer_zustand(zustand)
        rgb_btn.set_color(r, g, b)
    except Exception as e:
        print(f"  [RGB] FEHLER: {e}")

def update_piezo(piezo, zustand, quittiert, mute):
    try:
        if MUTE or mute or quittiert or zustand == "OK":
            piezo.set_beep(frequency=1000, volume=2,
                           duration=BrickletPiezoSpeakerV2.BEEP_DURATION_OFF)
        elif zustand == "KRITISCH":
            piezo.set_alarm(start_frequency=800, end_frequency=2400,
                            step_size=200, step_delay=30, volume=2,
                            duration=BrickletPiezoSpeakerV2.ALARM_DURATION_INFINITE)
        elif zustand == "WARNUNG":
            piezo.set_beep(frequency=1200, volume=2, duration=300)
    except Exception as e:
        print(f"  [Piezo] FEHLER: {e}")

def update_segment(seg):
    try:
        h = int(time.strftime("%H"))
        m = int(time.strftime("%M"))
        seg.set_numeric_value([h // 10, h % 10, m // 10, m % 10])
    except Exception as e:
        print(f"  [Segment] FEHLER: {e}")

def update_lcd(lcd, s):
    try:
        lcd.clear_display()
        lcd.write_line(0, 0, "== Serverraum  ==")
        lcd.write_line(1, 0, f"Temp:   {s['temp']:5.1f} C")
        lcd.write_line(2, 0, f"Feuch:  {s['humidity']:5.1f} %RH")
        lcd.write_line(3, 0, f"Licht:  {s['lux']:5.0f} lx")
        lcd.write_line(4, 0, f"Motion: {'JA  ' if s['motion'] else 'NEIN'}")
        lcd.write_line(5, 0, f"Status: {s['zustand']}")
        lcd.write_line(6, 0, "")
        lcd.write_line(7, 0, time.strftime("%d.%m.%Y %H:%M:%S"))
    except Exception as e:
        print(f"  [LCD] FEHLER: {e}")

def update_epaper(ep, s):
    try:
        ep.fill_display(BrickletEPaper296x128.COLOR_WHITE)
        time.sleep(0.1)
        ep.draw_text(5, 5, BrickletEPaper296x128.FONT_12X16,
                     BrickletEPaper296x128.COLOR_BLACK,
                     BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                     "Serverraum-Monitor")
        farbe = (BrickletEPaper296x128.COLOR_RED if s["zustand"] != "OK"
                 else BrickletEPaper296x128.COLOR_BLACK)
        ep.draw_text(5, 28, BrickletEPaper296x128.FONT_18X32,
                     farbe,
                     BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                     s["zustand"])
        ep.draw_text(5, 68, BrickletEPaper296x128.FONT_12X16,
                     BrickletEPaper296x128.COLOR_BLACK,
                     BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                     f"T: {s['temp']:.1f}C   H: {s['humidity']:.1f}%")
        ep.draw_text(5, 90, BrickletEPaper296x128.FONT_6X8,
                     BrickletEPaper296x128.COLOR_BLACK,
                     BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                     f"Motion: {'JA' if s['motion'] else 'NEIN'}")
        ep.draw_text(5, 108, BrickletEPaper296x128.FONT_6X8,
                     BrickletEPaper296x128.COLOR_BLACK,
                     BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                     time.strftime("%d.%m.%Y  %H:%M:%S"))
        ep.draw()
    except Exception as e:
        print(f"  [E-Paper] FEHLER: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# HAUPTSCHLEIFE
# ══════════════════════════════════════════════════════════════════════════════
def main():
    ipcon = IPConnection()

    ptc      = BrickletPTCV2(UID_PTC, ipcon)
    light    = BrickletAmbientLightV3(UID_LIGHT, ipcon)
    humidity = BrickletHumidityV2(UID_HUMIDITY, ipcon)
    motion   = BrickletMotionDetectorV2(UID_MOTION, ipcon)
    global nfc_bricklet
    nfc_bricklet = BrickletNFC(UID_NFC, ipcon)
    dualbt   = BrickletDualButtonV2(UID_DUALBT, ipcon)
    rgb_btn  = BrickletRGBLEDButton(UID_RGBLED, ipcon)
    piezo    = BrickletPiezoSpeakerV2(UID_PIEZO, ipcon)
    epaper   = BrickletEPaper296x128(UID_EPAPER, ipcon)
    segment  = BrickletSegmentDisplay4x7V2(UID_SEGMENT, ipcon)
    lcd      = BrickletLCD128x64(UID_LCD, ipcon)

    ipcon.connect(HOST, PORT)
    time.sleep(1.0)  # Warten bis alle Bricklets bereit sind

    print(f"Verbunden mit {HOST}:{PORT}")
    print("╔══════════════════════════════════╗")
    print("║  Serverraum-Monitoring gestartet ║")
    print("╚══════════════════════════════════╝")
    print(f"  Temp:  Warn >= {TEMP_WARN}°C | Krit >= {TEMP_CRIT}°C | Kalt <= {TEMP_LOW}°C")
    print(f"  Feuch: Warn >= {HUMID_WARN}% | Krit >= {HUMID_CRIT}% | Trocken <= {HUMID_LOW}%\n")

    motion.register_callback(BrickletMotionDetectorV2.CALLBACK_MOTION_DETECTED,       cb_motion_detected)
    motion.register_callback(BrickletMotionDetectorV2.CALLBACK_DETECTION_CYCLE_ENDED, cb_motion_ended)
    motion.set_sensitivity(85)

    dualbt.register_callback(BrickletDualButtonV2.CALLBACK_STATE_CHANGED, cb_button_state_changed)
    dualbt.set_state_changed_callback_configuration(True)

    nfc_bricklet.set_mode(BrickletNFC.MODE_READER)
    nfc_bricklet.register_callback(BrickletNFC.CALLBACK_READER_STATE_CHANGED, cb_nfc_reader_state_changed)
    nfc_bricklet.reader_request_tag_id()

    lcd.set_display_configuration(14, 100, False, True)

    # ── GUI in eigenem Thread starten ─────────────────────────────────────
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gui as gui_module
    threading.Thread(
        target=gui_module.start_gui,
        args=(state, lock),
        daemon=True
    ).start()

    letzter_zustand       = None
    letzter_epaper_update = 0

    try:
        while True:
            # ── System inaktiv ─────────────────────────────────────────────
            if not state["aktiv"]:
                try:
                    rgb_btn.set_color(0, 0, 50)
                except Exception:
                    pass
                try:
                    piezo.set_beep(frequency=1000, volume=2,
                                   duration=BrickletPiezoSpeakerV2.BEEP_DURATION_OFF)
                except Exception:
                    pass
                update_segment(segment)
                time.sleep(POLL_INTERVAL)
                continue

            # ── Sensoren lesen ─────────────────────────────────────────────
            try:
                temp = ptc.get_temperature() / 100.0   # 1/100 °C → °C
            except Exception as e:
                print(f"  [PTC] FEHLER: {e}")
                time.sleep(POLL_INTERVAL)
                continue

            try:
                lux = light.get_illuminance() / 100.0  # 1/100 lx → lx
            except Exception as e:
                print(f"  [Light] FEHLER: {e}")
                lux = state["lux"]

            try:
                hum = humidity.get_humidity() / 100.0  # 1/100 %RH → %RH
            except Exception as e:
                print(f"  [Humidity] FEHLER: {e}")
                hum = state["humidity"]

            with lock:
                state["temp"]     = temp
                state["lux"]      = lux
                state["humidity"] = hum

            # ── Zustand berechnen ──────────────────────────────────────────
            neuer_zustand = zustand_berechnen(temp, hum)

            with lock:
                if neuer_zustand in ("KRITISCH", "WARNUNG"):
                    state["alarm"] = True
                elif neuer_zustand == "OK":
                    state["alarm"]           = False
                    state["alarm_quittiert"] = False
                state["zustand"] = neuer_zustand
                snap = dict(state)

            # ── Konsole ────────────────────────────────────────────────────
            print(f"[{time.strftime('%H:%M:%S')}]  "
                  f"Temp: {temp:.1f}°C  "
                  f"Feuch: {hum:.1f}%  "
                  f"Licht: {lux:.0f}lx  "
                  f"Motion: {'JA  ' if snap['motion'] else 'NEIN'}  "
                  f"-> {neuer_zustand}"
                  f"{'  [QUITTIERT]' if snap['alarm_quittiert'] else ''}"
                  f"{'  [MUTE]' if snap['mute'] else ''}")

            # ── Aktoren updaten ────────────────────────────────────────────
            update_rgb(rgb_btn, neuer_zustand)
            update_piezo(piezo, neuer_zustand, snap["alarm_quittiert"], snap["mute"])
            update_segment(segment)
            update_lcd(lcd, snap)

            jetzt = time.time()
            if neuer_zustand != letzter_zustand or jetzt - letzter_epaper_update > 60:
                print("  [E-Paper] Update ...")
                update_epaper(epaper, snap)
                letzter_zustand       = neuer_zustand
                letzter_epaper_update = jetzt

            led_l = (BrickletDualButtonV2.LED_STATE_ON if snap["mute"]
                     else BrickletDualButtonV2.LED_STATE_OFF)
            led_r = (BrickletDualButtonV2.LED_STATE_ON if snap["alarm_quittiert"]
                     else BrickletDualButtonV2.LED_STATE_OFF)
            try:
                dualbt.set_led_state(led_l, led_r)
            except Exception as e:
                print(f"  [DualButton] FEHLER: {e}")

            if neuer_zustand == "KRITISCH" and not snap["alarm_quittiert"]:
                threading.Thread(
                    target=sende_alarm_email, args=(snap,), daemon=True
                ).start()

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nSystem gestoppt (Strg+C).")
    finally:
        try:
            rgb_btn.set_color(0, 0, 0)
        except Exception:
            pass
        try:
            piezo.set_beep(frequency=1000, volume=2,
                           duration=BrickletPiezoSpeakerV2.BEEP_DURATION_OFF)
        except Exception:
            pass
        try:
            segment.set_numeric_value([-1, -1, -1, -1])
        except Exception:
            pass
        try:
            lcd.clear_display()
            lcd.write_line(0, 0, "  System offline")
        except Exception:
            pass
        try:
            ipcon.disconnect()
        except Exception:
            pass
        print("Verbindung getrennt.")


if __name__ == "__main__":
    main()