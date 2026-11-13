"""Paths, audio files, timing constants and experiment-wide settings (no logic, no state)."""

import os


base_dir = os.path.dirname(os.path.abspath(__file__))
audio_dir = os.path.join(base_dir, "audios")

correct_audio = os.path.join(audio_dir, "correct_answer.wav")
incorrect_audio = os.path.join(audio_dir, "loud_incorrect_answer.wav")
alarm_audio = os.path.join(audio_dir, "alarm_llm.wav")

if not os.path.exists(alarm_audio):
    alarm_audio = incorrect_audio

mode_audio_haptic = os.path.join(audio_dir, "AUDIO_HAPTIC_MODE.wav")
mode_audio_only = os.path.join(audio_dir, "AUDIOHELP_mode.wav")
mode_haptic_only = os.path.join(audio_dir, "HapticVest_Mode.wav")
mode_baseline = os.path.join(audio_dir, "BASELINE_MODE.wav")

container1_audio = os.path.join(audio_dir, "CONTAINER1_ALERT.wav")
container2_audio = os.path.join(audio_dir, "CONTAINER2.wav")
mistake_audio = os.path.join(audio_dir, "loud_incorrect_answer.wav")

ROBOT_OWN_IP = "192.168.29.61"
DIFFICULTY_PORT = 50001


# ---------------------------------------------------------------------------
# Timing / Dual-Task / Training Configuration
# ---------------------------------------------------------------------------
MAX_ROUNDS_PER_CONDITION = 8    # Fixed 8 battery rounds per condition for equal data
TRAINING_ROUNDS = 3             # Practice rounds in training mode
RETRIEVAL_SECONDS = 5           # 5-second safe pause at checkpoint to pick up a piece
DELIVERY_WINDOW_SECONDS = 5     # 5-second safe pause after saying "deliver"
TASK_SECONDS_DEFAULT = 25       # Assembly time in baseline / audio / haptic scenarios
WARNING_SECONDS = 10            # Red timer + blinking warning threshold

# Voice ("deliver") recognition – offline Vosk
VOSK_MODEL_DIR = os.path.join(base_dir, "model")   # downloaded Vosk model, renamed to "model"
if os.path.isdir(VOSK_MODEL_DIR) and not os.path.isdir(os.path.join(VOSK_MODEL_DIR, "am")):
    # model unzipped one level deeper (model/vosk-model-small-en-us-0.15/...): use that folder
    for _name in sorted(os.listdir(VOSK_MODEL_DIR)):
        if os.path.isdir(os.path.join(VOSK_MODEL_DIR, _name, "am")):
            VOSK_MODEL_DIR = os.path.join(VOSK_MODEL_DIR, _name)
            break
VOSK_SAMPLE_RATE = 16000                           # 16 kHz mono int16 is what Vosk expects
DELIVER_WORDS = ("deliver", "delivery", "ready")   # grammar-locked trigger words
VOICE_INPUT_KEYWORD = "Trekz"                         # e.g. "Realtek" to force a specific mic; None = system default
VOICE_COOLDOWN_SECONDS = 1.0                       # ignore repeat triggers from the same utterance
VOICE_KEEP_MIC_OPEN = True                         # open the microphone when a condition starts and keep it open.
                                                   # A Bluetooth headset (Trekz) switches to its hands-free mode while
                                                   # its microphone is in use, which changes the playback volume and
                                                   # quality. Opening the mic only for the battery task made the radio
                                                   # jump in volume at every dual-task phase; open all the time, the
                                                   # level stays the same. False = old behaviour.

# Radio game (radio_script.py / panel_logic.py / game.py)
RADIO_AUDIO_DIR = os.path.join(base_dir, "radio_audio")   # made by generate_radio_audio.py
PROBLEMS_PER_CHECKPOINT = 3        # radio problems (solved or not) before a checkpoint;
                                   # problems during the battery task do not count
RESPONSE_SECONDS = 6.0             # time to finish the presses after the instruction ends
SHUFFLE_SECONDS = 4.0              # idle buttons change color/word this often (frozen during a problem)
PROBLEM_GAP_SECONDS = (0.0, 0.0)   # random chatter time between two problems (0 = back-to-back problems)
FILLER_GAP_SECONDS = (0.3, 0.9)    # silence between two radio lines
RESUME_GAP_SECONDS = 0.0           # earliest next problem after a pause ends
POINTS_PER_STEP = 30               # solved: +30 per button in the sequence
FAIL_PENALTY = 40                  # wrong key or timeout (score never below 0)
SHOW_RESPONSE_BAR = True           # shrinking time bar once the instruction has ended
RADIO_VOLUME = 1.0
RADIO_FX = True                    # light band-pass "radio" sound
RADIO_STATIC_DB = -48              # constant soft hiss in dBFS (None = off)
USE_RADIO_CONTAINER_CUES = True    # checkpoint announcement in the chosen language (else the old WAVs)

# Game mode (chosen on the setup screen)
GAME_MODES = ["normal", "hard"]
# Hard mode: between instructions every button change shows exactly ONE button whose color matches
# its word. Pressing it scores; a miss costs nothing; one press per change (no button mashing).
HARD_INSTRUCTION_MULTIPLIER = 2    # radio instructions: double points when solved...
HARD_PENALTY_MULTIPLIER = 2        # ...and double penalty when wrong / too late
IDLE_HIT_POINTS = POINTS_PER_STEP * HARD_INSTRUCTION_MULTIPLIER // 2   # = half a hard one-button instruction (30)
IDLE_WRONG_PENALTY = 0             # wrong button on a match round (0 = no penalty, the try is just used up)
PRESS_GRACE_SECONDS = 0.5          # presses this soon after an instruction starts are ignored
                                   # (they were aimed at the match round, not the instruction)
LATE_PRESS_SECONDS = 0.25
ROULETTE_DURING_INSTRUCTION = ("hard",)   # modes where the buttons spin + arrows lock while the radio
                                          # speaks; the real buttons appear at ANSWER NOW. Add "normal" to use it there too.
ROULETTE_FRAME_SECONDS = 0.5             # spin speed          # a press this soon after a button change still counts for the previous one

# Remote camera evaluator (live_evaluator.py on the camera PC, same network).
# It reads the ParadigmMarkers LSL stream and answers on its own LSL stream; its verdict is applied
# right away. While True the manual y / c evaluation keys are disabled.
USE_REMOTE_EVALUATOR = True
EVALUATOR_STREAM_NAME = "BatteryEvaluator"


# Per-battery cues: sent by live_evaluator.py as soon as it sees a battery in a slot
# (Eval_Battery_Round_<r>_Slot_<k>_correct|incorrect). What the participant gets depends on the condition:
#   audio -> sound, haptic -> vest, audio_haptic -> both, baseline / training / robot_* -> nothing.
BATTERY_CUE_CONDITIONS = {"audio": ("audio",), "haptic": ("haptic",), "audio_haptic": ("audio", "haptic")}
correct_cue_audio = os.path.join(audio_dir, "positive_sound2.wav")   # swap the file name to change the sound
incorrect_cue_audio = mistake_audio                                  # the mistake sound used so far
CUE_AUDIO_MAX_SECONDS = 1.0        # every cue sound is cut to this length when played (files untouched)
HAPTIC_CORRECT_PATTERN = "positive_3"      # warm swell (pre-study)
HAPTIC_INCORRECT_PATTERN = "negative_2"    # sharp staccato (pre-study)
HAPTIC_CORRECT_POSITION = "VestBack"       # pre-study mapping "correct_back": correct on the back,
HAPTIC_INCORRECT_POSITION = "VestFront"    # incorrect on the front


def assembly_seconds(scenario):
    """Assembly time per scenario (shared by the GUI and live_evaluator.py)."""
    return TASK_SECONDS_DEFAULT


LOG_TRAINING_CSV = False
TRAINING_MARKER_PREFIX = "TRAIN_"

ALL_CONDITIONS = [
    "training",
    "baseline",
    "audio",
    "haptic",
    "audio_haptic",
]
