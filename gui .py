#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║       Serverraum-Überwachung – Tkinter GUI                   ║
╚══════════════════════════════════════════════════════════════╝

Starte über final.py – die GUI liest den gemeinsamen state-Dict.
Beide Dateien müssen im selben Ordner liegen.
"""

import tkinter as tk
import threading
import time

# Wird von final.py beim Aufruf von start_gui() gesetzt
state = None
lock  = None

# Konstanten aus final.py (werden beim Import übernommen)
TEMP_WARN        = 26.0
TEMP_CRIT        = 32.0
TEMP_LOW         = 15.0
HUMID_WARN       = 60.0
HUMID_CRIT       = 75.0
HUMID_LOW        = 20.0
EMAIL_COOLDOWN_S = 300

# ══════════════════════════════════════════════════════════════════════════════
# FARBEN & FONTS
# ══════════════════════════════════════════════════════════════════════════════
BG       = "#0d0f14"
PANEL    = "#161a24"
BORDER   = "#1e2535"
ACCENT   = "#00e5ff"
OK_COL   = "#00e676"
WARN_COL = "#ff9100"
CRIT_COL = "#ff1744"
INACTIVE = "#546e7a"
TEXT_PRI = "#e8eaf6"
TEXT_SEC = "#546e7a"

F_MONO   = ("Courier New", 11)
F_SMALL  = ("Courier New", 9)
F_TITLE  = ("Courier New", 13, "bold")
F_BIG    = ("Courier New", 26, "bold")
F_BTN    = ("Courier New", 10, "bold")
F_VAL    = ("Courier New", 14, "bold")


def zustand_farbe(zustand):
    return {"OK": OK_COL, "WARNUNG": WARN_COL, "KRITISCH": CRIT_COL}.get(zustand, INACTIVE)


# ══════════════════════════════════════════════════════════════════════════════
# GUI-KLASSE
# ══════════════════════════════════════════════════════════════════════════════
class ServerraumGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Serverraum-Überwachung")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.geometry("820x600")
        self._build()
        self._tick()

    # ── Layout aufbauen ───────────────────────────────────────────────────
    def _build(self):
        # Titelzeile
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=20, pady=(14, 0))
        tk.Label(top, text="⬛  SERVERRAUM-MONITOR",
                 font=F_TITLE, bg=BG, fg=ACCENT).pack(side="left")
        self.lbl_zeit = tk.Label(top, text="--:--:--",
                                 font=F_MONO, bg=BG, fg=TEXT_SEC)
        self.lbl_zeit.pack(side="right")

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", padx=20, pady=6)

        # Hauptbereich
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=20)

        left  = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right = tk.Frame(body, bg=BG)
        right.pack(side="right", fill="both", expand=True, padx=(8, 0))

        # ── Linke Seite: Sensorwert-Karten ────────────────────────────────
        self.v_temp   = self._sensor_card(left, "TEMPERATUR",    "°C",  warn=f">= {TEMP_WARN}°C  |  Krit >= {TEMP_CRIT}°C")
        self.v_hum    = self._sensor_card(left, "LUFTFEUCHT.",   "%RH", warn=f">= {HUMID_WARN}%  |  Krit >= {HUMID_CRIT}%")
        self.v_lux    = self._sensor_card(left, "HELLIGKEIT",    "lx",  warn="")
        self.v_motion = self._motion_card(left)

        # ── Rechte Seite: Status, Flags, Steuerung ─────────────────────────

        # Statuskasten
        sp = self._panel(right)
        tk.Label(sp, text="SYSTEMSTATUS", font=F_SMALL, bg=PANEL, fg=TEXT_SEC
                 ).pack(anchor="w", padx=12, pady=(10, 0))
        self.lbl_zustand = tk.Label(sp, text="OK", font=F_BIG, bg=PANEL, fg=OK_COL)
        self.lbl_zustand.pack(anchor="w", padx=12)
        self.lbl_aktiv = tk.Label(sp, text="● AKTIV", font=F_SMALL, bg=PANEL, fg=OK_COL)
        self.lbl_aktiv.pack(anchor="w", padx=12, pady=(0, 10))

        tk.Frame(sp, bg=BORDER, height=1).pack(fill="x")

        flags = tk.Frame(sp, bg=PANEL)
        flags.pack(fill="x", padx=12, pady=8)
        self.flag_alarm = self._flag(flags, "ALARM",     0)
        self.flag_mute  = self._flag(flags, "MUTE",      1)
        self.flag_quitt = self._flag(flags, "QUITTIERT", 2)

        # E-Mail Cooldown
        mp = self._panel(right, pady=(0, 8))
        tk.Label(mp, text="E-MAIL COOLDOWN", font=F_SMALL, bg=PANEL, fg=TEXT_SEC
                 ).pack(anchor="w", padx=12, pady=(8, 0))
        self.lbl_cd = tk.Label(mp, text="—", font=F_MONO, bg=PANEL, fg=TEXT_PRI)
        self.lbl_cd.pack(anchor="w", padx=12, pady=(2, 10))

        # Steuerbuttons
        bp = self._panel(right, pady=(0, 8))
        tk.Label(bp, text="STEUERUNG", font=F_SMALL, bg=PANEL, fg=TEXT_SEC
                 ).pack(anchor="w", padx=12, pady=(10, 6))
        btns = tk.Frame(bp, bg=PANEL)
        btns.pack(fill="x", padx=12, pady=(0, 10))

        self.btn_mute = self._btn(btns, "🔇  MUTE",        self._toggle_mute,  side="left")
        self.btn_quitt = self._btn(btns, "✔  QUITTIEREN",  self._quittieren,   side="left", padx=(6, 6))
        self.btn_aktiv = self._btn(btns, "⏻  AN / AUS",    self._toggle_aktiv, side="left")

        # Schwellwerte Info
        ip = self._panel(right, pady=(0, 8))
        tk.Label(ip, text="SCHWELLWERTE", font=F_SMALL, bg=PANEL, fg=TEXT_SEC
                 ).pack(anchor="w", padx=12, pady=(8, 2))
        lines = [
            f"Temp  Warn >= {TEMP_WARN}°C  |  Krit >= {TEMP_CRIT}°C  |  Kalt <= {TEMP_LOW}°C",
            f"Feuch Warn >= {HUMID_WARN}%   |  Krit >= {HUMID_CRIT}%   |  Tr.  <= {HUMID_LOW}%",
        ]
        for l in lines:
            tk.Label(ip, text=l, font=("Courier New", 8), bg=PANEL, fg=TEXT_SEC
                     ).pack(anchor="w", padx=12)
        tk.Label(ip, text="", bg=PANEL).pack()

        # Log
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", padx=20, pady=(6, 0))
        logbar = tk.Frame(self.root, bg=BG)
        logbar.pack(fill="x", padx=20, pady=(4, 0))
        tk.Label(logbar, text="LOG", font=F_SMALL, bg=BG, fg=TEXT_SEC).pack(side="left")

        lf = tk.Frame(self.root, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        lf.pack(fill="both", expand=True, padx=20, pady=(4, 14))
        self.log = tk.Text(lf, bg=PANEL, fg=TEXT_SEC, font=("Courier New", 8),
                           state="disabled", relief="flat", height=5, wrap="word")
        self.log.pack(fill="both", expand=True, padx=6, pady=6)
        self._log("GUI gestartet.")

    # ── Hilfsmethoden UI ──────────────────────────────────────────────────
    def _panel(self, parent, pady=(0, 8)):
        f = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        f.pack(fill="x", pady=pady)
        return f

    def _sensor_card(self, parent, label, unit, warn=""):
        card = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", pady=(0, 8))
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill="x", padx=12, pady=8)
        tk.Label(row, text=label, font=F_SMALL, bg=PANEL, fg=TEXT_SEC).pack(side="left")
        if warn:
            tk.Label(row, text=warn, font=("Courier New", 7), bg=PANEL, fg=BORDER).pack(side="left", padx=8)
        val = tk.Label(row, text=f"--  {unit}", font=F_VAL, bg=PANEL, fg=TEXT_PRI)
        val.pack(side="right")
        return val

    def _motion_card(self, parent):
        card = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", pady=(0, 8))
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill="x", padx=12, pady=8)
        tk.Label(row, text="BEWEGUNG", font=F_SMALL, bg=PANEL, fg=TEXT_SEC).pack(side="left")
        lbl = tk.Label(row, text="NEIN", font=F_VAL, bg=PANEL, fg=TEXT_SEC)
        lbl.pack(side="right")
        return lbl

    def _flag(self, parent, text, col):
        lbl = tk.Label(parent, text=text, font=F_SMALL, bg=PANEL, fg=TEXT_SEC,
                       padx=6, pady=3, highlightthickness=1, highlightbackground=BORDER)
        lbl.grid(row=0, column=col, padx=(0, 6), sticky="w")
        return lbl

    def _btn(self, parent, text, cmd, side="left", padx=(0, 0)):
        b = tk.Button(parent, text=text, font=F_BTN,
                      bg="#1e2535", fg=TEXT_PRI,
                      activebackground=ACCENT, activeforeground=BG,
                      relief="flat", padx=10, pady=6, cursor="hand2",
                      command=cmd)
        b.pack(side=side, padx=padx)
        return b

    # ── Update-Schleife ───────────────────────────────────────────────────
    def _tick(self):
        self._refresh()
        self.root.after(500, self._tick)

    def _refresh(self):
        if state is None:
            return
        with lock:
            s = dict(state)

        zustand = s["zustand"]
        farbe   = zustand_farbe(zustand)

        # Uhrzeit
        self.lbl_zeit.config(text=time.strftime("%H:%M:%S"))

        # Sensorwerte – Farbe kippt bei Überschreitung
        temp_farbe = CRIT_COL if s["temp"] >= TEMP_CRIT or s["temp"] <= TEMP_LOW else \
                     WARN_COL if s["temp"] >= TEMP_WARN else TEXT_PRI
        hum_farbe  = CRIT_COL if s["humidity"] >= HUMID_CRIT else \
                     WARN_COL if s["humidity"] >= HUMID_WARN or s["humidity"] <= HUMID_LOW else TEXT_PRI

        self.v_temp.config(text=f"{s['temp']:6.1f}  °C",   fg=temp_farbe)
        self.v_hum.config( text=f"{s['humidity']:6.1f}  %RH", fg=hum_farbe)
        self.v_lux.config( text=f"{s['lux']:6.0f}  lx",    fg=TEXT_PRI)
        self.v_motion.config(
            text="JA" if s["motion"] else "NEIN",
            fg=WARN_COL if s["motion"] else TEXT_SEC
        )

        # Systemstatus
        self.lbl_zustand.config(text=zustand, fg=farbe)
        if s["aktiv"]:
            self.lbl_aktiv.config(text="● AKTIV",   fg=OK_COL)
        else:
            self.lbl_aktiv.config(text="○ INAKTIV", fg=INACTIVE)

        # Flags
        self.flag_alarm.config(
            fg=CRIT_COL if s["alarm"] else TEXT_SEC,
            highlightbackground=CRIT_COL if s["alarm"] else BORDER)
        self.flag_mute.config(
            fg=WARN_COL if s["mute"] else TEXT_SEC,
            highlightbackground=WARN_COL if s["mute"] else BORDER)
        self.flag_quitt.config(
            fg=OK_COL if s["alarm_quittiert"] else TEXT_SEC,
            highlightbackground=OK_COL if s["alarm_quittiert"] else BORDER)

        # Mute-Button leuchtet orange wenn aktiv
        self.btn_mute.config(
            bg=WARN_COL if s["mute"] else "#1e2535",
            fg=BG       if s["mute"] else TEXT_PRI)

        # E-Mail Cooldown
        vergangen = time.time() - s["letzte_email"]
        if s["letzte_email"] == 0.0:
            self.lbl_cd.config(text="Noch keine Mail gesendet", fg=TEXT_SEC)
        elif vergangen < EMAIL_COOLDOWN_S:
            rest = int(EMAIL_COOLDOWN_S - vergangen)
            self.lbl_cd.config(text=f"Cooldown: noch {rest}s", fg=WARN_COL)
        else:
            self.lbl_cd.config(text="Bereit zum Senden", fg=OK_COL)

    # ── Button-Aktionen ───────────────────────────────────────────────────
    def _toggle_mute(self):
        if state is None:
            return
        with lock:
            state["mute"] = not state["mute"]
            m = state["mute"]
        self._log(f"Mute {'AN' if m else 'AUS'} (GUI)")

    def _quittieren(self):
        if state is None:
            return
        with lock:
            state["alarm"]           = False
            state["alarm_quittiert"] = True
        self._log("Alarm quittiert (GUI)")

    def _toggle_aktiv(self):
        if state is None:
            return
        with lock:
            state["aktiv"] = not state["aktiv"]
            a = state["aktiv"]
        self._log(f"System {'AKTIVIERT' if a else 'DEAKTIVIERT'} (GUI)")

    # ── Log ───────────────────────────────────────────────────────────────
    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log.config(state="normal")
        self.log.insert("end", f"[{ts}] {msg}\n")
        self.log.see("end")
        self.log.config(state="disabled")


# ══════════════════════════════════════════════════════════════════════════════
# EINSTIEGSPUNKT – wird von final.py aufgerufen
# ══════════════════════════════════════════════════════════════════════════════
def start_gui(shared_state, shared_lock):
    """Startet die Tkinter-GUI. Wird von final.py in einem Thread aufgerufen."""
    global state, lock
    # Konstanten aus final.py übernehmen
    try:
        import final as f
        global TEMP_WARN, TEMP_CRIT, TEMP_LOW
        global HUMID_WARN, HUMID_CRIT, HUMID_LOW, EMAIL_COOLDOWN_S
        TEMP_WARN        = f.TEMP_WARN
        TEMP_CRIT        = f.TEMP_CRIT
        TEMP_LOW         = f.TEMP_LOW
        HUMID_WARN       = f.HUMID_WARN
        HUMID_CRIT       = f.HUMID_CRIT
        HUMID_LOW        = f.HUMID_LOW
        EMAIL_COOLDOWN_S = f.EMAIL_COOLDOWN_S
    except Exception:
        pass  # Fallback auf Standardwerte oben

    state = shared_state
    lock  = shared_lock

    root = tk.Tk()
    ServerraumGUI(root)
    root.mainloop()
