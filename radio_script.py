"""Everything the plant radio says, in English, Latin American Spanish and German.

Pure Python (no Qt, no audio), so it can be edited and checked on its own.
After editing ANY text here, re-run:   python generate_radio_audio.py --lang all

Rules the text must follow (checked by validate()):
  * Never use "deliver", "delivery", "ready" (or German "liefer..."): the Vosk listener could
    hear the radio leaking out of the bone-conduction headphones and trigger a delivery.
  * Filler chatter never mentions colors, buttons, keys or alarm words, so the only colors the
    participant hears are inside real instructions.
"""

import hashlib
import json
import re

SCRIPT_VERSION = 1

LANGUAGES = {
    "en": "English",
    "es": "Español (Latinoamérica)",
    "de": "Deutsch",
}

# Language-independent color keys (used in markers / logs)
COLOR_KEYS = ["red", "blue", "green", "yellow", "purple"]

# ---------------------------------------------------------------------------
# Words on the buttons (shown on screen, uppercase)
# ---------------------------------------------------------------------------
LABELS = {
    "en": {"red": "RED", "blue": "BLUE", "green": "GREEN", "yellow": "YELLOW", "purple": "PURPLE"},
    "es": {"red": "ROJO", "blue": "AZUL", "green": "VERDE", "yellow": "AMARILLO", "purple": "MORADO"},
    "de": {"red": "ROT", "blue": "BLAU", "green": "GRÜN", "yellow": "GELB", "purple": "VIOLETT"},
}

# Spoken form when the instruction refers to the button's COLOR ("the red button")
COLOR_ADJ = {
    "en": {"red": "red", "blue": "blue", "green": "green", "yellow": "yellow", "purple": "purple"},
    "es": {"red": "rojo", "blue": "azul", "green": "verde", "yellow": "amarillo", "purple": "morado"},
    # accusative, masculine ("den roten Knopf")
    "de": {"red": "roten", "blue": "blauen", "green": "grünen", "yellow": "gelben", "purple": "violetten"},
}

# Spoken form when the instruction refers to the WORD on the button ("the button labeled red")
LABEL_SPOKEN = {
    "en": {"red": "red", "blue": "blue", "green": "green", "yellow": "yellow", "purple": "purple"},
    "es": {"red": "rojo", "blue": "azul", "green": "verde", "yellow": "amarillo", "purple": "morado"},
    "de": {"red": "Rot", "blue": "Blau", "green": "Grün", "yellow": "Gelb", "purple": "Violett"},
}


def step_phrase(lang, kind, color):
    """kind 'C' = by color, 'L' = by label word."""
    if lang == "en":
        return f"the {COLOR_ADJ[lang][color]} button" if kind == "C" \
            else f"the button labeled {LABEL_SPOKEN[lang][color]}"
    if lang == "es":
        return f"el botón {COLOR_ADJ[lang][color]}" if kind == "C" \
            else f"el botón que dice {LABEL_SPOKEN[lang][color]}"
    if lang == "de":
        return f"den {COLOR_ADJ[lang][color]} Knopf" if kind == "C" \
            else f"den Knopf mit der Aufschrift {LABEL_SPOKEN[lang][color]}"
    raise ValueError(lang)


def command_text(lang, steps):
    """steps: list of (kind, color). Returns the spoken command."""
    p = [step_phrase(lang, k, c) for k, c in steps]
    n = len(p)
    if lang == "en":
        lead = "To fix it, press"
        if n == 1:
            return f"{lead} {p[0]}."
        if n == 2:
            return f"{lead} {p[0]}, and then {p[1]}."
        return f"{lead} {p[0]}, then {p[1]}, and finally {p[2]}."
    if lang == "es":
        lead = "Para arreglarlo, presiona"
        if n == 1:
            return f"{lead} {p[0]}."
        if n == 2:
            return f"{lead} {p[0]}, y después {p[1]}."
        return f"{lead} {p[0]}, luego {p[1]}, y al final {p[2]}."
    if lang == "de":
        lead = "Um das zu beheben, drücke"
        if n == 1:
            return f"{lead} {p[0]}."
        if n == 2:
            return f"{lead} zuerst {p[0]}, und dann {p[1]}."
        return f"{lead} zuerst {p[0]}, dann {p[1]}, und zuletzt {p[2]}."
    raise ValueError(lang)


# ---------------------------------------------------------------------------
# Background chatter (the radio talks continuously)
# ---------------------------------------------------------------------------
FILLER = {
    "en": [
        "Hello everyone, this is plant radio with your regular update from the control room.",
        "All four turbines are running smoothly, and output is right on target today.",
        "The maintenance team finished the inspection of the cooling towers this morning.",
        "The weather outside is calm, with a light breeze coming from the river.",
        "Energy output this hour is slightly above yesterday's average. Nice work, everyone.",
        "A reminder that the cafeteria serves soup and fresh bread until two o'clock.",
        "The new sensors in the boiler room are sending clean data, with no surprises so far.",
        "Grid demand is stable, so we expect a quiet afternoon on the network.",
        "Shift change is at six. Please leave your notes for the next team.",
        "The coal yard received a full shipment this morning, and storage is looking good.",
        "Water temperature in the condenser is steady and well within limits.",
        "The safety walk in sector two went well. Thanks to everyone who joined.",
        "Our solar field is adding a little extra power while the sun is out.",
        "A group of visitors from the university will tour the plant later today.",
        "Fuel consumption is lower than planned, which keeps the budget happy.",
        "Remember to drink some water and take a short stretch when you can.",
        "Vibration on the main shaft is low and steady, just how we like it.",
        "The parking lot will be repainted on the weekend, so please park near the gate.",
        "Steam pressure across the plant is balanced and holding nicely.",
        "That is all for now from the control room. Enjoy your shift.",
    ],
    "es": [
        "Hola a todos, aquí la radio de la planta con su actualización desde la sala de control.",
        "Las cuatro turbinas funcionan sin problemas, y la producción va justo según lo planeado.",
        "El equipo de mantenimiento terminó hoy la inspección de las torres de enfriamiento.",
        "El clima afuera está tranquilo, con una brisa ligera que viene del río.",
        "La producción de energía de esta hora está un poco arriba del promedio de ayer. Buen trabajo a todos.",
        "Les recordamos que el comedor sirve sopa y pan recién hecho hasta las dos de la tarde.",
        "Los sensores nuevos de la sala de calderas envían datos limpios, sin sorpresas hasta ahora.",
        "La demanda de la red está estable, así que esperamos una tarde tranquila.",
        "El cambio de turno es a las seis. Por favor dejen sus notas para el siguiente equipo.",
        "El patio de carbón recibió un cargamento completo esta mañana, y el almacén se ve bien.",
        "La temperatura del agua en el condensador está estable y dentro de los límites.",
        "El recorrido de seguridad en el sector dos salió muy bien. Gracias a todos los que participaron.",
        "El campo solar está aportando un poco de energía extra mientras hay sol.",
        "Un grupo de visitantes de la universidad va a recorrer la planta más tarde.",
        "El consumo de combustible está por debajo de lo planeado, y eso ayuda al presupuesto.",
        "Recuerden tomar agua y estirarse un poco cuando puedan.",
        "La vibración del eje principal está baja y estable, justo como nos gusta.",
        "El estacionamiento se va a repintar el fin de semana, así que estaciónense cerca de la entrada.",
        "La presión de vapor en toda la planta está equilibrada y se mantiene bien.",
        "Eso es todo por ahora desde la sala de control. Que tengan un buen turno.",
    ],
    "de": [
        "Hallo zusammen, hier ist das Werksradio mit dem aktuellen Bericht aus der Leitwarte.",
        "Alle vier Turbinen laufen einwandfrei, und die Leistung liegt genau im Plan.",
        "Das Wartungsteam hat heute Morgen die Inspektion der Kühltürme abgeschlossen.",
        "Draußen ist es ruhig, mit einer leichten Brise vom Fluss.",
        "Die Energieleistung in dieser Stunde liegt etwas über dem gestrigen Durchschnitt. Gute Arbeit, alle zusammen.",
        "Zur Erinnerung: Die Kantine serviert bis vierzehn Uhr Suppe und frisches Brot.",
        "Die neuen Sensoren im Kesselhaus senden saubere Daten, bisher ohne Überraschungen.",
        "Die Netzlast ist stabil, wir erwarten einen ruhigen Nachmittag.",
        "Schichtwechsel ist um sechs. Bitte hinterlasst eure Notizen für das nächste Team.",
        "Das Kohlelager hat heute Morgen eine volle Ladung bekommen, der Vorrat sieht gut aus.",
        "Die Wassertemperatur im Kondensator ist stabil und innerhalb der Grenzwerte.",
        "Der Sicherheitsrundgang in Sektor zwei lief gut. Danke an alle, die dabei waren.",
        "Unser Solarfeld bringt etwas zusätzlichen Strom, solange die Sonne scheint.",
        "Eine Besuchergruppe von der Universität besichtigt später die Anlage.",
        "Der Brennstoffverbrauch liegt unter Plan, das freut das Budget.",
        "Denkt daran, etwas Wasser zu trinken und euch kurz zu strecken.",
        "Die Vibrationen an der Hauptwelle sind niedrig und stabil, genau so, wie wir es mögen.",
        "Der Parkplatz wird am Wochenende neu markiert, bitte parkt in der Nähe des Tores.",
        "Der Dampfdruck in der gesamten Anlage ist ausgeglichen und hält sich gut.",
        "Das war es fürs Erste aus der Leitwarte. Eine gute Schicht euch allen.",
    ],
}

# ---------------------------------------------------------------------------
# Incidents (the sudden "oh no" before each instruction)
# ---------------------------------------------------------------------------
INCIDENTS = {
    "en": [
        "Oh no, there's a short circuit in the turbine hall!",
        "Attention, the pressure in boiler two is rising fast!",
        "Warning, the main cooling pump just stopped!",
        "Oh no, the transformer in sector three is overloaded!",
        "Alert, there's a steam leak in the north pipeline!",
        "Careful, the conveyor belt in the coal yard is jammed!",
        "Oh no, the voltage is dropping on line four!",
        "Attention, the generator is overheating!",
    ],
    "es": [
        "¡Ay no, hay un cortocircuito en la sala de turbinas!",
        "¡Atención, la presión de la caldera dos está subiendo rápido!",
        "¡Cuidado, la bomba principal de enfriamiento se acaba de detener!",
        "¡Ay no, el transformador del sector tres está sobrecargado!",
        "¡Alerta, hay una fuga de vapor en la tubería norte!",
        "¡Cuidado, la banda transportadora del patio de carbón se atoró!",
        "¡Ay no, el voltaje está bajando en la línea cuatro!",
        "¡Atención, el generador se está sobrecalentando!",
    ],
    "de": [
        "Oh nein, Kurzschluss in der Turbinenhalle!",
        "Achtung, der Druck in Kessel zwei steigt schnell!",
        "Warnung, die Hauptkühlpumpe ist gerade ausgefallen!",
        "Oh nein, der Transformator in Sektor drei ist überlastet!",
        "Alarm, Dampfleck in der Nordleitung!",
        "Vorsicht, das Förderband im Kohlelager klemmt!",
        "Oh nein, die Spannung auf Leitung vier fällt ab!",
        "Achtung, der Generator überhitzt!",
    ],
}

# ---------------------------------------------------------------------------
# Reactions after a problem
# ---------------------------------------------------------------------------
FEEDBACK = {
    "en": {
        "solved": ["Perfect, that fixed it.", "Great job, everything is stable again.", "Nice, problem solved."],
        "wrong": ["Oh no, that was not right. We lost some power.",
                  "That didn't work, the system took some damage.",
                  "Too bad, that was the wrong move."],
        "timeout": ["Too late, the system shut down for a moment.", "Time is up, we lost some power."],
    },
    "es": {
        "solved": ["Perfecto, eso lo arregló.", "Excelente, todo está estable otra vez.", "Muy bien, problema resuelto."],
        "wrong": ["Ay no, eso no era. Perdimos algo de energía.",
                  "Eso no funcionó, el sistema sufrió daños.",
                  "Qué mal, ese no era el movimiento correcto."],
        "timeout": ["Muy tarde, el sistema se apagó por un momento.", "Se acabó el tiempo, perdimos energía."],
    },
    "de": {
        "solved": ["Perfekt, das hat es behoben.", "Sehr gut, alles ist wieder stabil.", "Super, Problem gelöst."],
        "wrong": ["Oh nein, das war falsch. Wir haben etwas Leistung verloren.",
                  "Das hat nicht geklappt, das System wurde beschädigt.",
                  "Schade, das war der falsche Schritt."],
        "timeout": ["Zu spät, das System hat kurz abgeschaltet.", "Die Zeit ist um, wir haben Leistung verloren."],
    },
}

# ---------------------------------------------------------------------------
# Checkpoint announcements (replace the English-only container WAVs)
# ---------------------------------------------------------------------------
ANNOUNCEMENTS = {
    "en": {
        "container_1": "Checkpoint. Bring back the empty piece, and take new parts from container one.",
        "container_2": "Checkpoint. Bring back the empty piece, and take new parts from container two.",
    },
    "es": {
        "container_1": "Punto de control. Regresa la pieza vacía, y toma piezas nuevas del contenedor uno.",
        "container_2": "Punto de control. Regresa la pieza vacía, y toma piezas nuevas del contenedor dos.",
    },
    "de": {
        "container_1": "Kontrollpunkt. Bring das leere Teil zurück, und nimm neue Teile aus Behälter eins.",
        "container_2": "Kontrollpunkt. Bring das leere Teil zurück, und nimm neue Teile aus Behälter zwei.",
    },
}


# ---------------------------------------------------------------------------
# Clip catalogue
# ---------------------------------------------------------------------------
def problem_clip_parts(lang, problem):
    """(incident, command) for one problem from panel_logic.build_pool()."""
    incident = INCIDENTS[lang][problem["incident"] % len(INCIDENTS[lang])]
    return incident, command_text(lang, problem["steps"])


def all_clips(lang, problems):
    """clip_id -> list of text parts (parts are spoken with a short pause in between)."""
    clips = {}
    for i, t in enumerate(FILLER[lang]):
        clips[f"filler_{i:02d}"] = [t]
    for kind, lines in FEEDBACK[lang].items():
        for i, t in enumerate(lines):
            clips[f"fb_{kind}_{i}"] = [t]
    for key, t in ANNOUNCEMENTS[lang].items():
        clips[f"ann_{key}"] = [t]
    for p in problems:
        clips[f"prob_{p['id']}"] = list(problem_clip_parts(lang, p))
    return clips


def clips_hash(clips):
    blob = json.dumps(clips, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:12]


_FORBIDDEN = re.compile(r"\b(deliver\w*|delivery|ready|already)\b|liefer\w*", re.IGNORECASE)


def validate():
    """Return a list of problems with the script (empty list = OK)."""
    issues = []
    for lang in LANGUAGES:
        pools = {
            "filler": FILLER[lang],
            "incident": INCIDENTS[lang],
            "feedback": [t for v in FEEDBACK[lang].values() for t in v],
            "announcement": list(ANNOUNCEMENTS[lang].values()),
            "command": [command_text(lang, [("C", c), ("L", c2)]) for c in COLOR_KEYS for c2 in COLOR_KEYS],
        }
        for name, texts in pools.items():
            for t in texts:
                if _FORBIDDEN.search(t):
                    issues.append(f"[{lang}] {name} uses a voice-trigger word: {t!r}")
        color_words = set()
        for table in (LABELS, COLOR_ADJ, LABEL_SPOKEN):
            color_words |= {w.lower() for w in table[lang].values()}
        for t in FILLER[lang] + INCIDENTS[lang]:
            words = set(re.findall(r"\w+", t.lower()))
            hit = words & color_words
            if hit:
                issues.append(f"[{lang}] color word {sorted(hit)} outside an instruction: {t!r}")
    return issues
