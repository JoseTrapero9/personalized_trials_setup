"""Checks shown to the researcher before a condition, the training, the pre-train or the questionnaire
starts (screens/preflight_dialog.py). Plain Python so it can be tested without Qt.

session_checks(...) -> [(level, text)]   level: "info" | "ok" | "warn" | "fail"
"""

import glob
import os

from config import BATTERY_CUE_CONDITIONS, USE_REMOTE_EVALUATOR, base_dir
from questionnaires import QUESTIONNAIRE_CONDITIONS, nasatlx_path, sus_path
from sequences import subject_tag

LOGS = os.path.join(base_dir, "logs")


def _pretrain_path(subject):
    return os.path.join(LOGS, "pretrain", f"{subject_tag(subject)}_pretrain.csv")


def _device_name(index):
    try:
        import sounddevice as sd
        return sd.query_devices(index)["name"]
    except Exception:
        return f"device {index}"


def _uses_vest(kind, condition):
    if kind in ("training", "pretrain"):
        return True
    return "haptic" in BATTERY_CUE_CONDITIONS.get(condition, ())


def session_checks(kind, subject, condition, *, language="en", game_mode="normal", audio_cue_mode="voice",
                   participant_device=None, researcher_device=None, vest_connected=False,
                   vest_supported=True, evaluator_connected=False, lsl_ok=True, error_count=0):
    """kind: "condition" | "training" | "pretrain" | "sus"."""
    tag = subject_tag(subject)
    what = {"training": "training (4 blocks)", "pretrain": "pre-train", "sus": "experience questionnaire"}.get(
        kind, condition)
    rows = [("info", f"Subject {subject} ({tag})  -  {what}"),
            ("info", f"Language {language}  -  game mode {game_mode}  -  audio cues {audio_cue_mode}")]

    # ---------------- subject / files
    if str(subject) == "1":
        rows.append(("warn", "Subject number is 1 (the default). Is that right?"))
    done = [c for c in QUESTIONNAIRE_CONDITIONS if os.path.exists(nasatlx_path(subject, c))]
    if kind in ("condition", "training", "sus"):
        rows.append(("info", f"Conditions finished for {tag} (NASA-TLX found): {', '.join(done) or 'none'}"))
    if kind == "condition":
        runs = glob.glob(os.path.join(LOGS, f"{tag}_{condition}_[0-9]*.csv"))
        if os.path.exists(nasatlx_path(subject, condition)):
            rows.append(("warn", f"{tag} already has a NASA-TLX for {condition}: it will be OVERWRITTEN "
                                 "when this run ends."))
        elif runs:
            rows.append(("warn", f"{tag} already ran {condition} {len(runs)} time(s) (round logs are kept)."))
    if kind == "pretrain" and os.path.exists(_pretrain_path(subject)):
        rows.append(("warn", f"{tag} already has a pre-train file: it will be OVERWRITTEN."))
    if kind == "sus" and any(os.path.exists(sus_path(subject, c)) for c in QUESTIONNAIRE_CONDITIONS):
        rows.append(("warn", f"{tag} already has questionnaire files: they will be OVERWRITTEN."))

    # ---------------- hardware / links
    if kind != "sus":
        if participant_device is None:
            rows.append(("fail", "Participant headphones (Trekz) NOT FOUND: radio and cues would play on the "
                                 "default output."))
        else:
            rows.append(("ok", f"Participant headphones: {_device_name(participant_device)}"))
        if researcher_device is None and kind in ("condition", "training"):
            rows.append(("warn", "Researcher audio output not found: the condition announcement plays on the "
                                 "default output."))
        if _uses_vest(kind, condition):
            if not vest_supported:
                rows.append(("fail", "Vest: websocket-client is not installed, vest cues are disabled "
                                     "(pip install websocket-client)."))
            elif vest_connected:
                rows.append(("ok", "Vest: bHaptics Player connected"))
            else:
                rows.append(("fail", "Vest: bHaptics Player NOT connected: vest cues would be lost. "
                                     "Start the Player and pair the vest."))
    if kind in ("condition", "training"):
        if not USE_REMOTE_EVALUATOR:
            rows.append(("info", "Camera evaluator switched off in config.py: evaluate with y / c."))
        elif evaluator_connected:
            rows.append(("ok", "Camera PC (live_evaluator.py) linked"))
        else:
            rows.append(("fail", "Camera PC NOT linked: no battery cues and no automatic evaluation. "
                                 "Start live_evaluator.py on the camera PC."))
    if not lsl_ok:
        rows.append(("fail", "LSL marker stream not running: nothing would be recorded."))
    if error_count:
        rows.append(("warn", f"{error_count} program error(s) so far in this run: see logs/errors.log."))
    return rows
