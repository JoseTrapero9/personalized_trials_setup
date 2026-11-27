"""Participant-facing screen text in the three languages.   t("key", n=3) -> string in state.language."""

from state import state

T = {
    # ---------------- game HUD ----------------
    "status_match": {"en": "FIND THE MATCH!"},
    "status_wait": {"en": "WAIT FOR YOUR INSTRUCTION!"},
    "status_answer": {"en": "ANSWER NOW!"},
    "mode_hard": {"en": "HARD"},
    "start_hard_line": {"en": "<br><b>HARD MODE</b>"},
    "radio_title": {"en": "PLANT RADIO"},
    "score": {"en": "SCORE"},
    "rank_up": {"en": "▲ You moved up to {place}!"},
    "rank_down": {"en": "▼ Another player passed you: now {place}!"},
    "rank_same": {"en": "★ You are holding {place}!"},
    "place_1": {"en": "1st place"},
    "place_2": {"en": "2nd place"},
    "place_3": {"en": "3rd place"},
    "place_n": {"en": "place {n}"},
    "next_cp": {"en": "CHECKPOINT IN {n}"},
    "assembly_mode": {"en": "ASSEMBLY RUNNING"},
    "audio_missing": {"en": "RADIO AUDIO MISSING"},
    "checkpoint_title": {"en": "CHECKPOINT (ROUND {r}/{m})"},
    "checkpoint_sub": {"en": "BRING BACK THE EMPTY PIECE!\nTake parts from CONTAINER {c}"},
    "delivery_title": {"en": "DELIVERY ({s}s PAUSE)"},
    "delivery_sub": {"en": "Walk to {pt} (the {key} delivery point), put the tray down\nand press the button AT {pt}!"},
    "system_failed": {"en": "SYSTEM FAILED\nDELIVER YOUR PIECE TO FIX"},

    # ---------------- right panel (battery) ----------------
    "point": {"en": "Point {n}"},
    "fb_correct": {"en": "✔ ASSEMBLY CORRECT"},
    "fb_incorrect": {"en": "✘ ASSEMBLY INCORRECT"},
    "fb_wrong_point": {"en": "✘ WRONG POINT: walk to {pt} (the {key} one)"},
    "key_left": {"en": "left"},             # side of the delivery point (not a keyboard key)
    "key_right": {"en": "right"},
    "advance": {"en": "Answer the radio to reach the next checkpoint."},
    "solve_header": {"en": "SOLVE THE BATTERY & KEEP LISTENING"},
    "deliver_hint": {"en": '<b>1. On the PC:</b> press <b>D</b> ({s}s pause).&nbsp;&nbsp; '
                           '<b>2. Walk</b> to <b>{pt}</b> ({key}) and press the button there.'},
    "delivery_active": {"en": "<b>DELIVERY WINDOW ({s}s)</b><br><b>Walk</b> to <b>{pt}</b> (the {key} delivery point), "
                              "put the tray down and press <b>the button at {pt}</b>!"},
    "warning_finish": {"en": "WARNING - FINISH"},
    "failed_short": {"en": "SYSTEM FAILED"},
    "round": {"en": "ROUND {r} / {m}"},

    # ---------------- start screen ----------------
    "start_title_training": {"en": "Training Session"},
    "start_title_cond": {"en": "Block {c}"},
    "start_body": {"en": "1. Listen to the <b>plant radio</b>. When something breaks, it tells you which buttons to press.<br>"
              "2. Find those buttons on the screen and press them with <b>← ↓ →</b> (left, middle, right).<br>"
              "3. After some problems the radio pauses for <b>{r}s</b>: take parts from Container I or II.<br>"
              "4. The screen splits: build the battery while you keep answering the radio.<br>"
              "5. Press <b>\"D: DELIVER\"</b> for a <b>{d}s</b> pause, place the piece and press the Point button.<br><br>"
              "Rounds: <b>{rounds}</b>"},
    "start_button": {"en": "Start"},
    "preparing": {"en": "Get ready..."},

    # ---------------- tutorial ----------------
    "tut_header": {"en": "TRAINING TUTORIAL — STEP {i} / {n}"},
    "tut_back": {"en": "← Back"},
    "tut_next": {"en": "Next →"},
    "tut_start": {"en": "Start Practice →"},
    "tut_continue": {"en": "Continue →"},
    "block_header": {"en": "PRACTICE BLOCK {i} / {n}"},
    "block_start": {"en": "Start block →"},
    "demo_pos": {"en": "1 · Right cue"},
    "demo_neg": {"en": "2 · Wrong cue"},
    # ---- warm-ups (screens/warmup_screen.py)
    "wu_radio_title": {"en": "Warm-up · Radio"},
    "wu_radio_intro": {"en": "<b>On the PC</b>, only the radio for now. Listen and press the buttons it names with the "
              "keyboard arrows <b>←</b> <b>↓</b> <b>→</b>.<br>"
              "First you can also <b>read</b> what it says, then you only <b>hear</b> it."},
    "wu_stage_read": {"en": "READ + LISTEN"},
    "wu_stage_listen": {"en": "LISTEN ONLY"},
    "wu_progress": {"en": "Instruction {i} of {n}  ·  solved {k}"},
    "wu_listen": {"en": "🔊 Listen to the radio..."},
    "wu_between": {"en": "Between instructions: press the button whose <b>color matches its word</b> (+{p})."},
    "wu_solved": {"en": "✔ Well done!"},
    "wu_wrong": {"en": "✘ Not quite. The answer was:"},
    "wu_timeout": {"en": "⏱ Too slow. The answer was:"},
    "wu_said": {"en": "The radio said:"},
    "wu_step_color": {"en": "{n}. the button that IS {x}: press {key}"},
    "wu_step_word": {"en": "{n}. the button with the WORD {x}: press {key}"},
    "wu_hud": {"en": "WARM-UP"},
    "wu_radio_done": {"en": "Radio warm-up done: {k} of {n} solved."},
    "wu_again": {"en": "↺ Again"},
    "wu_continue": {"en": "Continue →"},
    "wu_battery_title": {"en": "Warm-up · Battery sums"},
    "wu_battery_intro": {"en": "Solve it <b>on the PC</b> with the keyboard: press <b>1</b> Blue, <b>2</b> Red, "
              "<b>3</b> Yellow, <b>4</b> Green to fill the next slot (<b>Backspace</b> = undo). The sum is shown live."},
    "wu_tag_pc": {"en": "ON THE PC · keyboard"},
    "wu_tag_walk": {"en": "WALK TO {pt} · the {key} delivery point"},
    "wu_puzzle": {"en": "Puzzle {i} of {n}"},
    "wu_sum_now": {"en": "Sum now: {s}   (needed: {t})"},
    "wu_b_correct": {"en": "✔ Correct!  {calc}"},
    "wu_b_colors": {"en": "✘ Use exactly the batteries it says: {instr}."},
    "wu_b_order": {"en": "✘ Right batteries, wrong order: {calc}. Try another order."},
    "wu_b_answer": {"en": "The answer: {ans}  ({calc})"},
    "wu_b_next": {"en": "ENTER = next"},
    "wu_deliver_title": {"en": "Warm-up · Delivery"},
    "wu_deliver_d": {"en": "<b>On the PC:</b> your battery is ready. Press <b>D</b> on the keyboard to start the delivery."},
    "wu_deliver_pt": {"en": "<b>Now walk</b> to <b>{pt}</b>, the <b>{key}</b> delivery point. Put the tray down there "
                            "and press <b>the button at {pt}</b> (not the keyboard)."},
    "wu_deliver_ok": {"en": "✔ Right point!"},
    "wu_deliver_bad": {"en": "✘ That button is at the other point. Walk to {pt}, the {key} one."},
    "wu_battery_done": {"en": "Battery warm-up done: {k} of {n} right at the first try."},
    "wu_values": {"en": "VALUES"},
    "wu_key": {"en": "key {n}"},
    "wu_slot": {"en": "SLOT {n}"},
    "wu_slot_empty": {"en": "empty"},
    "color_Blue": {"en": "Blue"},
    "color_Red": {"en": "Red"},
    "color_Yellow": {"en": "Yellow"},
    "color_Green": {"en": "Green"},
    "start_title_block": {"en": "Practice block {i} of {n}: {name}"},
}

HARD_TUTORIAL_STEP = {"en": ("Radio · Find the match",
           "While you wait for the next instruction, the buttons keep changing, and each time <b>one</b> "
           "button's color <b>matches</b> its word (for example a <b>red</b> button that says RED).<br><br>"
           "Press it before the buttons change: <b>+{p} points</b>. You get <b>one try</b> per change, "
           "and missing it costs nothing.<br><br>"
           "While the radio gives an instruction (<b>WAIT FOR YOUR INSTRUCTION!</b>) the buttons spin and the "
           "arrows are <b>locked</b>. At <b>ANSWER NOW!</b> the real buttons appear: press the ones it said.<br><br>"
           "A solved radio instruction gives <b>{ip} points per button</b>; a wrong key or running out of "
           "time costs <b>{fp} points</b>.")}

TUTORIAL = {"en": [
        ("Two tasks at the same time",
         "Today you keep a power plant running <b>and</b> build batteries, both at the same time.<br><br>"
         "• <b>Radio task</b>: listen to the plant radio and press buttons with <b>←</b> <b>↓</b> <b>→</b><br>"
         "• <b>Battery task</b>: build batteries on the tray in front of you<br><br>"
         "Both tasks count, so try to keep both going."),
        ("Radio · Listen",
         "The plant radio talks all the time.<br><br>"
         "When something breaks (<i>\"Oh no, a short circuit!\"</i>), the radio tells you "
         "<b>which buttons to press</b>. It says it only once, so keep listening."),
        ("Radio · Color or word?",
         "Every button has a <b>color</b> and a <b>word</b>, and they never match.<br><br>"
         "• <i>\"the red button\"</i> → the button that <b>is red</b><br>"
         "• <i>\"the button labeled red\"</i> → the button with the <b>word RED</b><br><br>"
         "If the radio names several buttons, press them <b>in that order</b>."),
        ("Radio · Which key?",
         "Left button = <b>←</b> &nbsp; Middle button = <b>↓</b> &nbsp; Right button = <b>→</b><br><br>"
         "The buttons <b>stop changing</b> while a problem is active.<br>"
         "One wrong key or running out of time = problem failed, you lose points, and the radio goes on."),
        ("Checkpoints",
         "After <b>{n} problems</b> the radio pauses for <b>{r} seconds</b>: bring back the empty piece "
         "and take parts from <b>Container I or II</b> (the screen tells you which)."),
        ("Battery · Make the sum",
         "Then the screen splits. On the right you see the <b>sum</b> and <b>which batteries</b> to use.<br><br>"
         "Values: <b>Blue = 1 &nbsp; Red = 2 &nbsp; Yellow = 3 &nbsp; Green = 4</b><br>"
         "Slot 1 counts <b>×1</b>, slot 2 <b>×2</b>, slot 3 <b>×3</b><br><br>"
         "Example: <i>sum 18, use 1 Blue and 2 Green</i> → <b>Green · Blue · Green</b> = 4 + 2 + 12 = 18<br><br>"
         "Keep answering the radio while you build."),
        ("Battery · Deliver with D",
         "Finished? <b>1. On the PC</b>, press <b>D</b>: the radio pauses for <b>{d} seconds</b>.<br>"
         "<b>2. Walk</b> with the tray to <b>Point 1</b> (left) or <b>Point 2</b> (right), the screen tells you "
         "which. Put it down there and press <b>the button at that point</b> (not the keyboard).<br><br>"
         "You have <b>{s} seconds</b> per battery. At 0, <b>SYSTEM FAILED</b> flashes until you deliver."),
        ("How the practice works",
         "First a short <b>warm-up</b> for each task on its own: the radio, then the battery sums and the delivery.<br>"
         "Then you practise both together in <b>{b} short blocks of {k} rounds</b>:<br><br>"
         "{blocks}<br><br>"
         "Before each block, one slide shows how its feedback works."),
    ]}

# Names of the training blocks / conditions as the participant sees them
BLOCK_NAMES = {
    "baseline": {"en": "no feedback"},
    "audio": {"en": "sound feedback"},
    "audio_haptic": {"en": "sound + vest feedback"},
    "haptic": {"en": "vest feedback"},
}

# How each cue is described on the cue slides (depends on the audio cue mode and the vest patterns in config.py)
CUE_WORDS = {
    "audio_pos": {"voice": {"en": "a voice says <b>\"input correct\"</b>"},
                  "tone": {"en": "a <b>short bright sound</b>"}},
    "audio_neg": {"voice": {"en": "a voice says <b>\"input incorrect\"</b>"},
                  "tone": {"en": "an <b>error sound</b>"}},
    "positive_3": {"en": "a <b>soft swell</b>"},
    "negative_2": {"en": "<b>three strong pulses</b>"},
    "vest_any": {"en": "a <b>vibration</b>"},
    "VestBack": {"en": "on your back"},
    "VestFront": {"en": "on your chest"},
}

CUE_SLIDES = {
    "baseline": {"en": ("No feedback",
               "In this block the system gives you <b>no feedback</b> about your batteries.<br><br>"
               "Check yourself that the colors and the sum are right before you deliver.")},
    "intro": {"en": "Each time you put a battery in a slot, the system checks it right away:"},
    "audio_line": {"en": "<b>In your headphones</b><br>✔ {pos} → this battery is <b>right</b><br>"
              "✘ {neg} → this battery is <b>wrong</b>"},
    "vest_line": {"en": "<b>On the vest</b><br>✔ {pos} <b>{pos_loc}</b> → <b>right</b><br>"
              "✘ {neg} <b>{neg_loc}</b> → <b>wrong</b>"},
    "after": {"en": "Wrong battery? Take it out and put in the right one: every battery you place gets its own cue."},
    "pickup": {"en": "At a checkpoint, a double pulse on your <b>right side</b> reminds you to pick up new parts."},
    "try": {"en": "Try them now: <b>1</b> = right cue, <b>2</b> = wrong cue"},
}


def _lang(lang=None):
    lang = lang or state.language
    return "en"                                # English only


def block_name(condition, lang=None):
    return BLOCK_NAMES[condition][_lang(lang)]


def cue_slide(condition, lang=None, audio_cue_mode=None):
    """(title, body) of the slide that explains the feedback cues of one condition."""
    from config import (BATTERY_CUE_CONDITIONS, HAPTIC_CORRECT_PATTERN, HAPTIC_CORRECT_POSITION,
                        HAPTIC_INCORRECT_PATTERN, HAPTIC_INCORRECT_POSITION)
    lang = _lang(lang)
    if condition not in BATTERY_CUE_CONDITIONS:
        return CUE_SLIDES["baseline"][lang]
    mode = audio_cue_mode if audio_cue_mode in ("voice", "tone") else "voice"
    channels = BATTERY_CUE_CONDITIONS[condition]
    parts = [CUE_SLIDES["intro"][lang]]
    if "audio" in channels:
        parts.append(CUE_SLIDES["audio_line"][lang].format(pos=CUE_WORDS["audio_pos"][mode][lang],
                                                           neg=CUE_WORDS["audio_neg"][mode][lang]))
    if "haptic" in channels:
        vest = lambda pattern: CUE_WORDS.get(pattern, CUE_WORDS["vest_any"])[lang]
        parts.append(CUE_SLIDES["vest_line"][lang].format(
            pos=vest(HAPTIC_CORRECT_PATTERN), neg=vest(HAPTIC_INCORRECT_PATTERN),
            pos_loc=CUE_WORDS[HAPTIC_CORRECT_POSITION][lang], neg_loc=CUE_WORDS[HAPTIC_INCORRECT_POSITION][lang]))
    parts.append(CUE_SLIDES["after"][lang])
    if "haptic" in channels:
        parts.append(CUE_SLIDES["pickup"][lang])
    parts.append(f"<i>{CUE_SLIDES['try'][lang]}</i>")
    name = block_name(condition, lang)
    return name[:1].upper() + name[1:], "<br><br>".join(parts)


def t(text_id, /, **kw):
    lang = "en"                                # English only
    s = T[text_id].get(lang) or T[text_id]["en"]
    return s.format(**kw) if kw else s
