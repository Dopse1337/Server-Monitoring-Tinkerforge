# Master-Bricklet-Thinkerforge

🖥️ Server Room Monitoring System

Ein Python-basiertes Überwachungssystem für Serverräume mit Tinkerforge-Hardware.
Erfasst Umweltwerte in Echtzeit, erkennt kritische Zustände und löst visuelle, akustische und E-Mail-Alarme aus.

⚙️ Features
🌡️ Temperaturüberwachung (PTC Bricklet 2.0)
💧 Luftfeuchtigkeit (Humidity Bricklet 2.0)
💡 Helligkeit (Ambient Light Bricklet 3.0)
🚶 Bewegungserkennung (Motion Detector 2.0)
📡 NFC-Steuerung (System an/aus, Alarm quittieren)
🔘 Dual Button (Mute & Quittierung)
🚨 Alarm-System
OK → alles normal
WARNUNG → Grenzwerte überschritten
KRITISCH → sofortiger Alarm

Reaktionen:
🔴 RGB-LED zeigt Zustand
🔊 Piezo-Speaker gibt Warn-/Alarmton aus
📧 E-Mail bei kritischem Zustand (mit Cooldown)
🖥️ Anzeigen auf LCD & E-Paper

🧠 Systemlogik
Zustandsberechnung basierend auf Temperatur & Luftfeuchtigkeit
Zentrale State-Verwaltung (Thread-safe mit Lock)
Event-basierte Verarbeitung (Callbacks für Bewegung, Buttons, NFC)
Hauptloop pollt Sensoren alle 2 Sekunden

🖥️ Anzeigen
LCD → Live-Daten (Temp, Feuchte, Licht, Status)
E-Paper → Statusübersicht (energiesparend, langsames Update)
7-Segment → Uhrzeit
RGB Button → Statusfarbe
📧 E-Mail Benachrichtigung
Versand über SMTP (Gmail)
Automatischer Alarm bei kritischem Zustand
Cooldown verhindert Spam (z. B. 5 Minuten)

🧩 Technologien
Python 3
Tinkerforge API
Multithreading (threading)
SMTP (smtplib)

▶️ Start
pip install tinkerforge
python main.py
🔒 Sicherheit
Verwendung von Gmail App-Passwort
Thread-safe Zugriff auf Systemzustand
Schutz vor Doppel-Triggern (NFC Cooldown)

📌 Use Case
Ideal für:
Serverräume
Labore
Technikräume
Smart Monitoring Projekte
