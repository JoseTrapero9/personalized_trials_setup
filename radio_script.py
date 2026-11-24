"""Everything the plant radio says, in English, Latin American Spanish and German.

Pure Python (no Qt, no audio), so it can be edited and checked on its own.
After editing ANY text here, re-run:   python generate_radio_audio.py --lang all

Rules the text must follow (checked by validate()):
  * Filler chatter and incident descriptions intentionally mention the task colors (red, blue,
    green, yellow, purple) as distractors so the participant must discriminate real button
    commands from background color mentions.
"""

import hashlib
import json
import re

SCRIPT_VERSION = 4

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


def first_step_text(lang, step):
    """Spoken command for the FIRST button in an announcement."""
    s = step_phrase(lang, *step)
    if lang == "en":
        return f"Press first {s}."
    if lang == "es":
        return f"Presiona primero {s}."
    if lang == "de":
        return f"Drücke zuerst {s}."
    raise ValueError(lang)


def second_step_text(lang, step):
    """Spoken command for the SECOND button in an announcement."""
    s = step_phrase(lang, *step)
    if lang == "en":
        return f"Also press {s}."
    if lang == "es":
        return f"También presiona {s}."
    if lang == "de":
        return f"Drücke außerdem {s}."
    raise ValueError(lang)


def command_text(lang, steps):
    """steps: list of (kind, color). Returns the spoken command."""
    p = [step_phrase(lang, k, c) for k, c in steps]
    n = len(p)
    if lang == "en":
        if n == 1:
            return f"Press {p[0]}."
        if n == 2:
            return f"{first_step_text(lang, steps[0])} {second_step_text(lang, steps[1])}"
        return f"Press {p[0]}, then {p[1]}, and finally {p[2]}."
    if lang == "es":
        if n == 1:
            return f"Presiona {p[0]}."
        if n == 2:
            return f"{first_step_text(lang, steps[0])} {second_step_text(lang, steps[1])}"
        return f"Presiona {p[0]}, luego {p[1]}, y al final {p[2]}."
    if lang == "de":
        if n == 1:
            return f"Drücke {p[0]}."
        if n == 2:
            return f"{first_step_text(lang, steps[0])} {second_step_text(lang, steps[1])}"
        return f"Drücke zuerst {p[0]}, dann {p[1]}, und zuletzt {p[2]}."
    raise ValueError(lang)


# ---------------------------------------------------------------------------
# Background chatter (short control-room updates)
# ---------------------------------------------------------------------------
FILLER = {
    "en": [
        "Control room update: all green status lights are normal.",
        "All four turbines are running smoothly.",
        "Cooling tower inspection near the blue gate is complete.",
        "Weather outside is calm and clear.",
        "Energy output is right in the green zone.",
        "Cafeteria is open until two o'clock.",
        "Boiler room sensors show clean data on the yellow display.",
        "Grid demand is steady this afternoon.",
        "Shift change is at six o'clock in the red hall.",
        "Coal yard storage is full.",
        "Condenser water temperature is normal in the blue pipe.",
        "Sector two safety walk is finished.",
        "Solar field is adding extra power to the purple grid.",
        "University visitors in yellow vests arrive later today.",
        "Fuel use is below plan today.",
        "Remember to drink some water.",
        "Main shaft vibration is low on the red monitor.",
        "Please park near the purple fence by the main gate.",
        "Steam pressure is holding steady.",
        "Control room out. Enjoy your shift.",
    ],
    "es": [
        "Sala de control: todas las luces verdes están normales.",
        "Las cuatro turbinas funcionan bien.",
        "Inspección de torres cerca de la puerta azul terminada.",
        "El clima afuera está tranquilo.",
        "La producción sigue en la zona verde.",
        "El comedor cierra a las dos.",
        "Sensores de calderas sin novedades en la pantalla amarilla.",
        "La demanda de la red está estable.",
        "El cambio de turno es a las seis en la sala roja.",
        "El almacén de carbón está lleno.",
        "Temperatura del condensador normal en la tubería azul.",
        "Recorrido de seguridad terminado.",
        "El campo solar aporta energía extra a la red morada.",
        "Hoy vienen visitantes de la universidad con chaleco amarillo.",
        "El consumo de combustible es bajo.",
        "Recuerden tomar un poco de agua.",
        "Vibración del eje baja en el monitor rojo.",
        "Estaciónense cerca de la cerca morada junto a la entrada.",
        "La presión de vapor se mantiene bien.",
        "Eso es todo. Buen turno a todos.",
    ],
    "de": [
        "Leitwarte hier: alle grünen Statuslichter sind normal.",
        "Alle vier Turbinen laufen rund.",
        "Kühlturm-Inspektion am blauen Tor ist abgeschlossen.",
        "Draußen ist das Wetter ruhig.",
        "Die Leistung liegt genau im grünen Bereich.",
        "Die Kantine hat bis vierzehn Uhr offen.",
        "Kesselhaus-Sensoren zeigen saubere Daten auf dem gelben Display.",
        "Die Netzlast ist heute stabil.",
        "Schichtwechsel ist um achtzehn Uhr in der roten Halle.",
        "Das Kohlelager ist voll.",
        "Wassertemperatur im Kondensator der blauen Leitung normal.",
        "Sicherheitsrundgang in Sektor zwei beendet.",
        "Das Solarfeld liefert Zusatzstrom für das violette Netz.",
        "Später kommt eine Besuchergruppe in gelben Westen.",
        "Der Brennstoffverbrauch ist niedrig.",
        "Denkt daran, etwas Wasser zu trinken.",
        "Vibrationen an der Hauptwelle sind auf dem roten Monitor gering.",
        "Bitte nahe am violetten Zaun beim Haupttor parken.",
        "Der Dampfdruck bleibt stabil.",
        "Leitwarte Ende. Gute Schicht.",
    ],
}

# ---------------------------------------------------------------------------
# Incidents: 3 short clauses (alert, issue_detail, status_tail) so the two button
# commands are split up and woven into different places of the announcement.
# ---------------------------------------------------------------------------
INCIDENTS = {
    "en": [
        ("Alert, problem in the red turbine hall!", "There is a short circuit on the line.", "Isolate the fault now."),
        ("Attention, boiler two pressure is rising!", "The yellow relief valve is stuck.", "Watch the main gauge."),
        ("Warning, the blue cooling pump stopped!", "Water flow is dropping fast.", "Backup flow is starting."),
        ("Alert, transformer three is overloaded!", "The purple coils are heating up.", "Shed the extra load now."),
        ("Warning, steam leak in the green north pipe!", "Pressure is falling in that sector.", "Seal that section now."),
        ("Attention, the coal conveyor is jammed!", "The red drive motor is straining.", "Clear the belt quickly."),
        ("Alert, voltage is dropping on the blue line!", "The feeder is unstable.", "Balance the network now."),
        ("Warning, the main generator is overheating!", "The green exhaust sensor is high.", "Cool the unit down fast."),
    ],
    "es": [
        ("¡Alerta, problema en la sala roja de turbinas!", "Hay un cortocircuito en la línea.", "Aísla la falla ahora."),
        ("¡Atención, sube la presión en caldera dos!", "La válvula amarilla de alivio se trabó.", "Vigila el medidor."),
        ("¡Cuidado, se detuvo la bomba azul de enfriamiento!", "El flujo de agua cae rápido.", "Ya entra el respaldo."),
        ("¡Alerta, sobrecarga en el transformador tres!", "Las bobinas moradas se calientan.", "Baja la carga ahora."),
        ("¡Cuidado, fuga de vapor en la tubería verde!", "Cae la presión en ese sector.", "Cierra esa sección ya."),
        ("¡Atención, se atoró la banda de carbón!", "El motor rojo se esfuerza.", "Libera la banda rápido."),
        ("¡Alerta, cae el voltaje en la línea azul!", "El alimentador está inestable.", "Equilibra la red ya."),
        ("¡Cuidado, el generador se sobrecalienta!", "El sensor verde de escape marca alto.", "Enfría la unidad rápido."),
    ],
    "de": [
        ("Alarm, Problem in der roten Turbinenhalle!", "Kurzschluss auf der Leitung.", "Isoliere sofort den Fehler."),
        ("Achtung, Druckanstieg in Kessel zwei!", "Das gelbe Sicherheitsventil klemmt.", "Prüfe die Hauptanzeige."),
        ("Warnung, die blaue Kühlpumpe steht!", "Der Wasserfluss fällt schnell.", "Der Ersatzlauf startet."),
        ("Alarm, Trafo drei ist überlastet!", "Die violetten Spulen werden heiß.", "Senke sofort die Last."),
        ("Warnung, Dampfleck in der grünen Nordleitung!", "Der Druck im Sektor fällt.", "Sperre den Abschnitt ab."),
        ("Achtung, das Kohleband klemmt!", "Der rote Antriebsmotor ist überlastet.", "Mach das Band schnell frei."),
        ("Alarm, Spannungsabfall auf der blauen Leitung!", "Die Einspeisung schwankt stark.", "Stabilisiere das Netz."),
        ("Warnung, der Generator überhitzt!", "Der grüne Abgassensor ist zu hoch.", "Kühle die Einheit schnell."),
    ],
}

# ---------------------------------------------------------------------------
# Reactions after a problem (short)
# ---------------------------------------------------------------------------
FEEDBACK = {
    "en": {
        "solved": ["Fixed.", "Nice, stable again.", "Good, problem solved."],
        "wrong": ["Wrong button, power lost.", "No, system damaged.", "Wrong move."],
        "timeout": ["Too late, power lost.", "Time's up."],
    },
    "es": {
        "solved": ["Listo, arreglado.", "Bien, estable otra vez.", "Problema resuelto."],
        "wrong": ["Botón incorrecto.", "No, hubo daños.", "Movimiento equivocado."],
        "timeout": ["Muy tarde.", "Se acabó el tiempo."],
    },
    "de": {
        "solved": ["Behoben.", "Gut, wieder stabil.", "Problem gelöst."],
        "wrong": ["Falscher Knopf.", "Nein, Systemschaden.", "Falscher Schritt."],
        "timeout": ["Zu spät.", "Zeit abgelaufen."],
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
    """Spoken parts for one problem from panel_logic.build_pool().
    Splits the two button steps and interleaves them at random positions inside the incident clauses.
    """
    a, b, c = INCIDENTS[lang][problem["incident"] % len(INCIDENTS[lang])]
    steps = problem["steps"]
    if len(steps) != 2:
        return a, b, command_text(lang, steps)
    cmd1 = first_step_text(lang, steps[0])
    cmd2 = second_step_text(lang, steps[1])
    pos = problem.get("pos", 0) % 4
    if pos == 0:
        return a, cmd1, b, cmd2, c
    if pos == 1:
        return cmd1, a, b, cmd2, c
    if pos == 2:
        return a, cmd1, b, c, cmd2
    return a, b, cmd1, c, cmd2


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




def validate():
    """Return a list of problems with the script (empty list = OK)."""
    issues = []
    # Inflected color stems per language so we can verify all 5 distractor colors appear.
    color_stems = {
        "en": {"red": "red", "blue": "blue", "green": "green", "yellow": "yellow", "purple": "purple"},
        "es": {"red": "roj", "blue": "azul", "green": "verd", "yellow": "amarill", "purple": "morad"},
        "de": {"red": "rot", "blue": "blau", "green": "grün", "yellow": "gelb", "purple": "violett"},
    }
    for lang in LANGUAGES:
        incident_texts = [part for pair in INCIDENTS[lang]
                          for part in (pair if isinstance(pair, (tuple, list)) else (pair,))]
        for pool_name, texts in (("filler", FILLER[lang]), ("incident", incident_texts)):
            joined_words = re.findall(r"\w+", " ".join(texts).lower())
            for color_key, stem in color_stems[lang].items():
                if not any(w.startswith(stem) for w in joined_words):
                    issues.append(f"[{lang}] {pool_name} missing distractor color {color_key!r}")
    return issues
