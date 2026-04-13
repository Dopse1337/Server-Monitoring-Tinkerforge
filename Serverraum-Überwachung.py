#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║       Serverraum-Überwachung – Hauptscript                   ║
╚══════════════════════════════════════════════════════════════╝

Sensoren:
  - PTC Bricklet 2.0            (Wcg)  → Temperatur
  - Ambient Light Bricklet 3.0  (Pdw)  → Helligkeit
  - Humidity Bricklet 2.0       (ViW)  → Luftfeuchtigkeit
  - Motion Detector Bricklet 2.0(ML4)  → Bewegungserkennung
  - NFC Bricklet                (22ND) → System aktivieren/deaktivieren
  - Dual Button Bricklet 2.0    (Vd8)  → Linker Button: Mute | Rechter Button: Quittieren

Aktoren:
  - RGB LED Button Bricklet     (23Qx) → Zustandsanzeige (Grün/Orange/Rot)
  - Piezo Speaker Bricklet 2.0  (R7M)  → Akustischer Alarm
  - E-Paper 296x128             (24KJ) → Statusanzeige
  - Segment Display 4x7 V2      (Tre)  → Uhrzeitanzeige
  - LCD 128x64                  (24Rh) → Live-Sensorwerte

Voraussetzung: pip install tinkerforge
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

# Tinkerforge – IP-Adresse des Master Bricks
HOST = "172.20.10.242"
PORT = 4223

# UIDs der Bricklets (aus Brick Viewer ablesen)
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

# Schwellwerte Temperatur
TEMP_WARN   = 26.0  # °C – Warnung ab diesem Wert
TEMP_CRIT   = 32.0  # °C – Kritisch ab diesem Wert
TEMP_LOW    = 15.0  # °C – Warnung wenn Temperatur unter diesen Wert fällt

# Schwellwerte Luftfeuchtigkeit
HUMID_WARN  = 60.0  # %RH – Warnung ab diesem Wert
HUMID_CRIT  = 75.0  # %RH – Kritisch ab diesem Wert (Kondensationsgefahr)
HUMID_LOW   = 20.0  # %RH – Warnung wenn Feuchtigkeit unter diesen Wert fällt

# Allgemein
POLL_INTERVAL = 2.0   # Sekunden zwischen Sensor-Abfragen
MUTE          = False # True = Piezo dauerhaft stumm (für Tests)

# E-Mail Konfiguration
EMAIL_AN         = "eliaskramer3@gmail.com"   # Empfänger-Adresse
EMAIL_VON        = "forgetinker@gmail.com"    # Absender-Adresse (Gmail)
EMAIL_PASSWORT   = "sffdrmrvdfyoxqnc"         # Gmail App-Passwort (nicht das normale Passwort!)
SMTP_SERVER      = "smtp.gmail.com"           # Gmail SMTP-Server
SMTP_PORT        = 587                        # Port für TLS-Verschlüsselung
EMAIL_COOLDOWN_S = 300                        # Mindestabstand zwischen zwei Mails in Sekunden


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEMZUSTAND
# ══════════════════════════════════════════════════════════════════════════════
# Alle Zustandsvariablen des Systems in einem Dictionary.
# Wird aus mehreren Threads gelesen/geschrieben → Zugriff immer mit lock absichern.
state = {
    "aktiv":           True,   # False = System per NFC deaktiviert
    "alarm":           False,  # True = aktuell ein Alarm aktiv
    "alarm_quittiert": False,  # True = Alarm wurde quittiert (rechter Button)
    "mute":            False,  # True = Piezo manuell stummgeschaltet (linker Button)
    "zustand":         "OK",   # Aktueller Zustand: "OK" / "WARNUNG" / "KRITISCH"
    "temp":            0.0,    # Letzte gemessene Temperatur in °C
    "humidity":        0.0,    # Letzte gemessene Luftfeuchtigkeit in %RH
    "lux":             0.0,    # Letzte gemessene Helligkeit in lx
    "motion":          False,  # True = Bewegung aktuell erkannt
    "letzte_email":    0.0,    # Unix-Timestamp der zuletzt gesendeten Mail (Cooldown)
}

lock = threading.Lock()  # Verhindert gleichzeitigen Schreibzugriff aus mehreren Threads
nfc_bricklet = None      # Wird in main() gesetzt, damit der NFC-Callback darauf zugreifen kann
nfc_letzter_scan = 0.0   # Timestamp letzter NFC-Scan (verhindert Doppel-Trigger)


# ══════════════════════════════════════════════════════════════════════════════
# HILFSFUNKTIONEN
# ══════════════════════════════════════════════════════════════════════════════
def zustand_berechnen(temp, humidity):
    """
    Berechnet den Systemzustand anhand von Temperatur und Luftfeuchtigkeit.
    Rückgabe: "KRITISCH", "WARNUNG" oder "OK"
    """
    if temp >= TEMP_CRIT or temp <= TEMP_LOW or humidity >= HUMID_CRIT:
        return "KRITISCH"
    if temp >= TEMP_WARN or humidity >= HUMID_WARN or humidity <= HUMID_LOW:
        return "WARNUNG"
    return "OK"


def rgb_fuer_zustand(zustand):
    """Gibt die RGB-Farbe passend zum Zustand zurück."""
    return {
        "OK":       (0, 255, 0),    # Grün
        "WARNUNG":  (255, 165, 0),  # Orange
        "KRITISCH": (255, 0, 0),    # Rot
    }.get(zustand, (0, 0, 255))     # Blau als Fallback


# ══════════════════════════════════════════════════════════════════════════════
# E-MAIL
# ══════════════════════════════════════════════════════════════════════════════
def sende_alarm_email(snap):
    """
    Sendet eine Alarm-E-Mail mit den aktuellen Sensorwerten.

    Diese Funktion wird in einem eigenen Thread aufgerufen damit der
    SMTP-Verbindungsaufbau die Hauptschleife nicht blockiert.

    Cooldown: Es wird maximal eine Mail alle EMAIL_COOLDOWN_S Sekunden
    gesendet, auch wenn der Alarmzustand dauerhaft anhält.
    """

    # Cooldown prüfen – wie lange ist die letzte Mail her?
    jetzt = time.time()
    vergangen = jetzt - snap["letzte_email"]
    if vergangen < EMAIL_COOLDOWN_S:
        verbleibend = int(EMAIL_COOLDOWN_S - vergangen)
        print(f"  [Email] Cooldown aktiv – naechste Mail in {verbleibend}s moeglich")
        return

    zeitstempel = time.strftime("%d.%m.%Y %H:%M:%S")

    # Betreff je nach aktuellem Zustand
    betreff = f"[{snap['zustand']}] Serverraum-Alarm – {zeitstempel}"

    # E-Mail-Text mit allen relevanten Infos – echte Umlaute dank UTF-8 Encoding
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
        # E-Mail-Objekt erstellen
        msg            = MIMEText(inhalt, "plain", "utf-8")
        msg["From"]    = EMAIL_VON
        msg["To"]      = EMAIL_AN
        msg["Subject"] = betreff

        # SMTP-Verbindung aufbauen, TLS aktivieren, einloggen und senden
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()                          # TLS-Verschlüsselung aktivieren
            server.ehlo()
            server.login(EMAIL_VON, EMAIL_PASSWORT)    # Mit App-Passwort einloggen
            server.sendmail(EMAIL_VON, EMAIL_AN, msg.as_string())

        # Cooldown-Zeitstempel aktualisieren damit nicht sofort wieder eine Mail gesendet wird
        with lock:
            state["letzte_email"] = jetzt

        print(f"  [Email] Erfolgreich gesendet an {EMAIL_AN}")

    except smtplib.SMTPAuthenticationError:
        print("  [Email] FEHLER: Login fehlgeschlagen – App-Passwort pruefen!")
    except smtplib.SMTPException as e:
        print(f"  [Email] SMTP-FEHLER: {e}")
    except Exception as e:
        print(f"  [Email] FEHLER: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# CALLBACKS – werden von Tinkerforge automatisch aufgerufen bei Ereignissen
# ══════════════════════════════════════════════════════════════════════════════
def cb_motion_detected():
    """Wird aufgerufen wenn der Bewegungsmelder eine Bewegung erkennt."""
    with lock:
        state["motion"] = True
    print("  [Motion] Bewegung erkannt!")

def cb_motion_ended():
    """Wird aufgerufen wenn der Bewegungsmelder keine Bewegung mehr erkennt."""
    with lock:
        state["motion"] = False
    print("  [Motion] Keine Bewegung mehr.")

def cb_button_state_changed(button_l, button_r, led_l, led_r):
    """
    Wird aufgerufen wenn sich der Zustand eines der zwei Buttons ändert.
    Linker Button  → Piezo muten/unmuten (Toggle)
    Rechter Button → Alarm quittieren (Piezo verstummt, LED zeigt Quittierung)
    """
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
    """
    Wird aufgerufen wenn sich der NFC-Reader-Zustand ändert.

    Das NFC Bricklet sucht NICHT automatisch nach Tags – man muss
    reader_request_tag_id() aktiv aufrufen. Der typische Ablauf ist:
      1. Bricklet wird IDLE → wir rufen reader_request_tag_id() auf
      2. Bricklet sucht nach Tag → Zustand wechselt zu REQUEST_TAG_ID_READY
      3. Tag wurde gefunden → Aktion ausführen, dann zurück zu Schritt 1

    Aktionen bei gefundenem Tag:
      - Alarm aktiv und nicht quittiert → Alarm quittieren
      - Kein aktiver Alarm              → System an/aus (Toggle)
    """
    if reader_state == BrickletNFC.READER_STATE_IDLE:
        # Bricklet ist bereit → neuen Tag-Scan starten
        nfc_bricklet.reader_request_tag_id()

    elif reader_state == BrickletNFC.READER_STATE_REQUEST_TAG_ID_READY:
        # Tag wurde erfolgreich erkannt → Aktion ausführen
        # Cooldown: Mindestens 2 Sekunden zwischen zwei Aktionen (verhindert Doppel-Trigger)
        global nfc_letzter_scan
        jetzt = time.time()
        if jetzt - nfc_letzter_scan < 2.0:
            return
        nfc_letzter_scan = jetzt

        with lock:
            aktueller_zustand = state["zustand"]
            if aktueller_zustand in ("KRITISCH", "WARNUNG"):
                # Bei Alarm-Zustand → Alarm quittieren
                state["alarm"]           = False
                state["alarm_quittiert"] = True
                print(f"  [NFC] Alarm quittiert (Zustand war: {aktueller_zustand})")
            else:
                # Bei OK → System aktivieren/deaktivieren
                state["aktiv"] = not state["aktiv"]
                print(f"  [NFC] System {'AKTIVIERT' if state['aktiv'] else 'DEAKTIVIERT'}")

    elif reader_state == BrickletNFC.READER_STATE_REQUEST_TAG_ID_ERROR:
        # Kein Tag gefunden → sofort erneut suchen
        nfc_bricklet.reader_request_tag_id()


# ══════════════════════════════════════════════════════════════════════════════
# AKTOREN – Funktionen zum Ansteuern der Ausgabe-Bricklets
# ══════════════════════════════════════════════════════════════════════════════
def update_rgb(rgb_btn, zustand):
    """Setzt die LED-Farbe des RGB-Buttons passend zum Zustand."""
    r, g, b = rgb_fuer_zustand(zustand)
    rgb_btn.set_color(r, g, b)


def update_piezo(piezo, zustand, quittiert, mute):
    """
    Steuert den Piezo-Speaker:
    - MUTE=True oder mute=True oder quittiert=True → Ton aus
    - KRITISCH → Alarm-Sweep (auf- und abschwellend)
    - WARNUNG  → kurzer Beep
    - OK       → Ton aus
    """
    if MUTE or mute or quittiert or zustand == "OK":
        # Ton ausschalten
        piezo.set_beep(frequency=1000, volume=2,
                       duration=BrickletPiezoSpeakerV2.BEEP_DURATION_OFF)
    elif zustand == "KRITISCH":
        # Dauerhafter Alarm-Sweep von 800Hz bis 2400Hz
        piezo.set_alarm(start_frequency=800, end_frequency=2400,
                        step_size=200, step_delay=30, volume=2,
                        duration=BrickletPiezoSpeakerV2.ALARM_DURATION_INFINITE)
    elif zustand == "WARNUNG":
        # Kurzer Warnton
        piezo.set_beep(frequency=1200, volume=2, duration=300)


def update_segment(seg):
    """Zeigt die aktuelle Uhrzeit (HH:MM) auf der 4x7-Segmentanzeige."""
    h = int(time.strftime("%H"))
    m = int(time.strftime("%M"))
    seg.set_numeric_value([h // 10, h % 10, m // 10, m % 10])


def update_lcd(lcd, s):
    """Schreibt alle aktuellen Sensorwerte und den Systemstatus auf das LCD."""
    lcd.clear_display()
    lcd.write_line(0, 0, "== Serverraum  ==")
    lcd.write_line(1, 0, f"Temp:   {s['temp']:5.1f} C")
    lcd.write_line(2, 0, f"Feuch:  {s['humidity']:5.1f} %RH")
    lcd.write_line(3, 0, f"Licht:  {s['lux']:5.0f} lx")
    lcd.write_line(4, 0, f"Motion: {'JA  ' if s['motion'] else 'NEIN'}")
    lcd.write_line(5, 0, f"Status: {s['zustand']}")
    lcd.write_line(6, 0, "")
    lcd.write_line(7, 0, time.strftime("%d.%m.%Y %H:%M:%S"))


def update_epaper(ep, s):
    """
    Aktualisiert das E-Paper-Display mit dem aktuellen Zustand.
    Wird nur bei Zustandswechsel oder alle 60s aufgerufen,
    da ein vollständiges Update ~7.5 Sekunden dauert.
    """
    ep.fill_display(BrickletEPaper296x128.COLOR_WHITE)
    time.sleep(0.1)  # Kurze Pause damit der Weiß-Buffer sauber gesetzt ist

    # Titelzeile
    ep.draw_text(5, 5, BrickletEPaper296x128.FONT_12X16,
                 BrickletEPaper296x128.COLOR_BLACK,
                 BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                 "Serverraum-Monitor")

    # Zustand groß anzeigen – rot wenn nicht OK, sonst schwarz
    farbe = (BrickletEPaper296x128.COLOR_RED if s["zustand"] != "OK"
             else BrickletEPaper296x128.COLOR_BLACK)
    ep.draw_text(5, 28, BrickletEPaper296x128.FONT_18X32,
                 farbe,
                 BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                 s["zustand"])

    # Temperatur und Luftfeuchtigkeit
    ep.draw_text(5, 68, BrickletEPaper296x128.FONT_12X16,
                 BrickletEPaper296x128.COLOR_BLACK,
                 BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                 f"T: {s['temp']:.1f}C   H: {s['humidity']:.1f}%")

    # Bewegungsstatus
    ep.draw_text(5, 90, BrickletEPaper296x128.FONT_6X8,
                 BrickletEPaper296x128.COLOR_BLACK,
                 BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                 f"Motion: {'JA' if s['motion'] else 'NEIN'}")

    # Zeitstempel des letzten Updates
    ep.draw_text(5, 108, BrickletEPaper296x128.FONT_6X8,
                 BrickletEPaper296x128.COLOR_BLACK,
                 BrickletEPaper296x128.ORIENTATION_HORIZONTAL,
                 time.strftime("%d.%m.%Y  %H:%M:%S"))

    ep.draw()  # Buffer auf das Display übertragen


# ══════════════════════════════════════════════════════════════════════════════
# HAUPTSCHLEIFE
# ══════════════════════════════════════════════════════════════════════════════
def main():
    ipcon = IPConnection()

    # Alle Bricklets initialisieren
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
    print(f"Verbunden mit {HOST}:{PORT}")
    print("╔══════════════════════════════════╗")
    print("║  Serverraum-Monitoring gestartet ║")
    print("╚══════════════════════════════════╝")
    print(f"  Temp:  Warn >= {TEMP_WARN}°C | Krit >= {TEMP_CRIT}°C | Kalt <= {TEMP_LOW}°C")
    print(f"  Feuch: Warn >= {HUMID_WARN}% | Krit >= {HUMID_CRIT}% | Trocken <= {HUMID_LOW}%\n")

    # Callbacks registrieren
    motion.register_callback(BrickletMotionDetectorV2.CALLBACK_MOTION_DETECTED,       cb_motion_detected)
    motion.register_callback(BrickletMotionDetectorV2.CALLBACK_DETECTION_CYCLE_ENDED, cb_motion_ended)
    motion.set_sensitivity(85)

    # Dual Button: Callback registrieren UND aktivieren (beim V2 zwingend nötig)
    dualbt.register_callback(BrickletDualButtonV2.CALLBACK_STATE_CHANGED, cb_button_state_changed)
    dualbt.set_state_changed_callback_configuration(True)

    # NFC im Reader-Modus starten und ersten Tag-Scan anstoßen
    nfc_bricklet.set_mode(BrickletNFC.MODE_READER)
    nfc_bricklet.register_callback(BrickletNFC.CALLBACK_READER_STATE_CHANGED, cb_nfc_reader_state_changed)
    nfc_bricklet.reader_request_tag_id()  # Ersten Scan starten

    # LCD Kontrast und Helligkeit setzen
    lcd.set_display_configuration(14, 100, False, True)

    letzter_zustand       = None   # Für E-Paper-Update bei Zustandswechsel
    letzter_epaper_update = 0      # Timestamp letztes E-Paper-Update

    try:
        while True:
            # ── System inaktiv (per NFC deaktiviert) ──────────────────────────
            if not state["aktiv"]:
                rgb_btn.set_color(0, 0, 50)  # Blau = System inaktiv
                piezo.set_beep(frequency=1000, volume=2,
                               duration=BrickletPiezoSpeakerV2.BEEP_DURATION_OFF)
                update_segment(segment)
                time.sleep(POLL_INTERVAL)
                continue

            # ── Sensoren lesen ─────────────────────────────────────────────────
            temp = ptc.get_temperature() / 100.0        # Rückgabe in 1/100 °C
            lux  = light.get_illuminance() / 100.0      # Rückgabe in 1/100 lx
            hum  = humidity.get_humidity() / 100.0      # Rückgabe in 1/100 %RH

            with lock:
                state["temp"]     = temp
                state["lux"]      = lux
                state["humidity"] = hum

            # ── Zustand berechnen ──────────────────────────────────────────────
            neuer_zustand = zustand_berechnen(temp, hum)

            with lock:
                if neuer_zustand == "KRITISCH":
                    state["alarm"] = True
                elif neuer_zustand == "WARNUNG":
                    state["alarm"] = True
                elif neuer_zustand == "OK":
                    # Bei OK: Alarm und Quittierung zurücksetzen
                    state["alarm"]           = False
                    state["alarm_quittiert"] = False
                state["zustand"] = neuer_zustand
                snap = dict(state)  # Snapshot des aktuellen Zustands für Aktoren

            # ── Konsole ────────────────────────────────────────────────────────
            print(f"[{time.strftime('%H:%M:%S')}]  "
                  f"Temp: {temp:.1f}°C  "
                  f"Feuch: {hum:.1f}%  "
                  f"Licht: {lux:.0f}lx  "
                  f"Motion: {'JA  ' if snap['motion'] else 'NEIN'}  "
                  f"-> {neuer_zustand}"
                  f"{'  [QUITTIERT]' if snap['alarm_quittiert'] else ''}"
                  f"{'  [MUTE]' if snap['mute'] else ''}")

            # ── Aktoren updaten ────────────────────────────────────────────────
            update_rgb(rgb_btn, neuer_zustand)
            update_piezo(piezo, neuer_zustand, snap["alarm_quittiert"], snap["mute"])
            update_segment(segment)
            update_lcd(lcd, snap)

            # E-Paper nur bei Zustandswechsel oder alle 60s aktualisieren
            jetzt = time.time()
            if neuer_zustand != letzter_zustand or jetzt - letzter_epaper_update > 60:
                print("  [E-Paper] Update ...")
                update_epaper(epaper, snap)
                letzter_zustand       = neuer_zustand
                letzter_epaper_update = jetzt

            # Dual-Button LEDs: Links leuchtet bei Mute, Rechts bei Quittierung
            led_l = (BrickletDualButtonV2.LED_STATE_ON
                     if snap["mute"]
                     else BrickletDualButtonV2.LED_STATE_OFF)
            led_r = (BrickletDualButtonV2.LED_STATE_ON
                     if snap["alarm_quittiert"]
                     else BrickletDualButtonV2.LED_STATE_OFF)
            dualbt.set_led_state(led_l, led_r)

            # ── E-Mail senden nur bei KRITISCH ────────────────────────────────
            # Läuft in eigenem Thread damit der SMTP-Aufbau nicht blockiert.
            # Cooldown und Quittierungs-Check erfolgen in sende_alarm_email().
            if neuer_zustand == "KRITISCH" and not snap["alarm_quittiert"]:
                threading.Thread(
                    target=sende_alarm_email, args=(snap,), daemon=True
                ).start()

            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        print("\nSystem gestoppt (Strg+C).")
    finally:
        # Beim Beenden alles sauber ausschalten
        rgb_btn.set_color(0, 0, 0)
        piezo.set_beep(frequency=1000, volume=2,
                       duration=BrickletPiezoSpeakerV2.BEEP_DURATION_OFF)
        segment.set_numeric_value([-1, -1, -1, -1])
        lcd.clear_display()
        lcd.write_line(0, 0, "  System offline")
        ipcon.disconnect()
        print("Verbindung getrennt.")


if __name__ == "__main__":
    main()
