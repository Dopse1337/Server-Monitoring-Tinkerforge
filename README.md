# Master-Bricklet-Thinkerforge

🖥️ **Server Room Monitoring System**

Python-basiertes Überwachungssystem für Serverräume mit Tinkerforge-Hardware. Erfasst Umweltwerte in Echtzeit, erkennt kritische Zustände und löst Alarme aus.

## Features

| Sensor | Funktion |
|--------|----------|
| 🌡️ PTC Bricklet 2.0 | Temperaturüberwachung |
| 💧 Humidity Bricklet 2.0 | Luftfeuchtigkeit |
| 💡 Ambient Light Bricklet 3.0 | Helligkeit |
| 🚶 Motion Detector 2.0 | Bewegungserkennung |
| 📡 NFC | System an/aus, Alarm quittieren |
| 🔘 Dual Button | Mute & Quittierung |

## Alarmsystem

- **OK** → 🟢 Alles normal
- **WARNUNG** → 🟡 Grenzwerte überschritten
- **KRITISCH** → 🔴 Sofortiger Alarm

**Reaktionen:** RGB-LED, Piezo-Speaker, E-Mail, LCD/E-Paper Anzeige

## Anzeigen

- LCD: Live-Daten (Temp, Feuchte, Licht, Status)
- E-Paper: Statusübersicht (energiesparend)
- 7-Segment: Uhrzeit
- RGB-LED: Systemstatus

## Installation & Start

```bash
pip install tinkerforge
python main.py
```

## Technologie

- Python 3
- Tinkerforge API
- Multithreading & SMTP
- Gmail App-Passwort für E-Mail-Versand

## Use Cases

Serverräume • Labore • Technikräume • Smart Monitoring Projekte