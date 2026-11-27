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

SCRIPT_VERSION = 6

LANGUAGES = {"en": "English"}

# Language-independent color keys (used in markers / logs)
COLOR_KEYS = ["red", "blue", "green", "yellow", "purple"]

# ---------------------------------------------------------------------------
# Words on the buttons (shown on screen, uppercase)
# ---------------------------------------------------------------------------
LABELS = {"en": {"red": "RED", "blue": "BLUE", "green": "GREEN", "yellow": "YELLOW", "purple": "PURPLE"}}

# Spoken form when the instruction refers to the button's COLOR ("the red button")
COLOR_ADJ = {"en": {"red": "red", "blue": "blue", "green": "green", "yellow": "yellow", "purple": "purple"}}

# Spoken form when the instruction refers to the WORD on the button ("the button labeled red")
LABEL_SPOKEN = {"en": {"red": "red", "blue": "blue", "green": "green", "yellow": "yellow", "purple": "purple"}}


def step_phrase(lang, kind, color):
    """kind 'C' = by color, 'L' = by label word."""
    if lang == "en":
        return f"the {COLOR_ADJ[lang][color]} button" if kind == "C" \
            else f"the button labeled {LABEL_SPOKEN[lang][color]}"
    raise ValueError(lang)                     # English only


FIRST_STEP_TEMPLATES = {"en": [
        "Hit {s}.",
        "Tap {s}.",
        "First, {s}.",
        "Use {s}.",
        "Press {s}.",
    ]}

SECOND_STEP_TEMPLATES = {"en": [
        "Then {s}.",
        "And {s}.",
        "Next, {s}.",
        "Plus {s}.",
        "Last, {s}.",
    ]}


def first_step_text(lang, step, variant=0):
    """Spoken command for the FIRST button in an announcement."""
    if lang not in FIRST_STEP_TEMPLATES:
        raise ValueError(lang)
    s = step_phrase(lang, *step)
    templates = FIRST_STEP_TEMPLATES[lang]
    return templates[variant % len(templates)].format(s=s)


def second_step_text(lang, step, variant=0):
    """Spoken command for the SECOND button in an announcement."""
    if lang not in SECOND_STEP_TEMPLATES:
        raise ValueError(lang)
    s = step_phrase(lang, *step)
    templates = SECOND_STEP_TEMPLATES[lang]
    return templates[variant % len(templates)].format(s=s)


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
    raise ValueError(lang)                     # English only


# ---------------------------------------------------------------------------
# Background chatter (short control-room updates)
# ---------------------------------------------------------------------------
FILLER = {"en": [
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
    ]}

# ---------------------------------------------------------------------------
# Incidents: variable-length tuples of clauses (from ~3 s up to ~12 s total)
# so participants cannot predict when the short commands will arrive at the end.
# ---------------------------------------------------------------------------
INCIDENTS = {"en": [
        ("Red turbine alert!",),
        ("Boiler two pressure is rising.", "The yellow relief valve is stuck."),
        ("Yellow cooling pump stopped.", "Do not touch the white switch.", "Backup flow is starting."),
        ("Blue transformer is overloaded.", "Do not press the black switch.",
         "Check the purple gauge on the green panel.", "Shed the green load now."),
        ("Green steam leak in the north pipe.", "Pressure is falling in the red sector.",
         "Sensors on the yellow monitor show a sharp drop.", "Maintenance is heading to sector four.",
         "Seal that section."),
        ("Attention, the yellow conveyor is jammed near the blue gate.",
         "The red drive motor is straining under heavy load.",
         "Dust levels are climbing along the purple walkway.",
         "Control room is rerouting power from the green backup line.",
         "Keep the main hopper clear while we reset.", "Clear the belt."),
        ("Voltage is dropping on the blue main line.",
         "The purple feeder is unstable and flickering.",
         "Auxiliary relays in the green bay are clicking repeatedly.",
         "Operators report red warning lights in the yellow corridor.",
         "We are switching the secondary bus to manual hold.",
         "Wait for the frequency meter to settle before closing the breaker.", "Balance the network."),
        ("Green generator overheating!", "Yellow exhaust sensor high."),
    ]}

# ---------------------------------------------------------------------------
# Reactions after a problem (short)
# ---------------------------------------------------------------------------
FEEDBACK = {"en": {
        "solved": ["Fixed.", "Nice, stable again.", "Good, problem solved."],
        "wrong": ["Wrong button, power lost.", "No, system damaged.", "Wrong move."],
        "timeout": ["Too late, power lost.", "Time's up."],
    }}

# ---------------------------------------------------------------------------
# Checkpoint announcements (replace the English-only container WAVs)
# ---------------------------------------------------------------------------
ANNOUNCEMENTS = {"en": {
        "container_1": "Checkpoint. Bring back the empty piece, and take new parts from container one.",
        "container_2": "Checkpoint. Bring back the empty piece, and take new parts from container two.",
    }}


# ---------------------------------------------------------------------------
# Clip catalogue
# ---------------------------------------------------------------------------
def problem_clip_parts(lang, problem):
    """Spoken parts for one problem from panel_logic.build_pool().
    Places the two short button commands either both at the end, or almost at the end + at the end,
    after a variable-length incident lead-in.
    """
    clauses = INCIDENTS[lang][problem["incident"] % len(INCIDENTS[lang])]
    steps = problem["steps"]
    if len(steps) != 2:
        return (*clauses, command_text(lang, steps))
    seed = int(hashlib.sha1(str(problem["id"]).encode("utf-8")).hexdigest()[:8], 16)
    cmd1 = first_step_text(lang, steps[0], variant=seed)
    cmd2 = second_step_text(lang, steps[1], variant=seed >> 3)
    if len(clauses) >= 2 and problem.get("pos", 0) % 2 == 1:
        return (*clauses[:-1], cmd1, clauses[-1], cmd2)
    return (*clauses, cmd1, cmd2)


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
    color_stems = {"en": {"red": "red", "blue": "blue", "green": "green", "yellow": "yellow", "purple": "purple"}}
    for lang in LANGUAGES:
        incident_texts = [part for pair in INCIDENTS[lang]
                          for part in (pair if isinstance(pair, (tuple, list)) else (pair,))]
        for pool_name, texts in (("filler", FILLER[lang]), ("incident", incident_texts)):
            joined_words = re.findall(r"\w+", " ".join(texts).lower())
            for color_key, stem in color_stems[lang].items():
                if not any(w.startswith(stem) for w in joined_words):
                    issues.append(f"[{lang}] {pool_name} missing distractor color {color_key!r}")
    return issues
