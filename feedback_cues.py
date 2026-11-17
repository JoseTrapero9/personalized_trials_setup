"""The feedback cues of the paradigm, in one place: per-battery cues, the samples on the training slides
and the pre-train all play exactly the same thing.

    play_feedback(("audio", "haptic"), is_correct, radio=None) -> dict describing what was played

Sound: the clip of the audio cue mode chosen on the setup screen (state.audio_cue_mode), cut to
CUE_AUDIO_MAX_SECONDS. If a running radio player is passed, the clip is mixed into its open stream (fast);
otherwise it is played on the participant output.
Vest: HAPTIC_CORRECT_PATTERN on HAPTIC_CORRECT_POSITION / HAPTIC_INCORRECT_PATTERN on HAPTIC_INCORRECT_POSITION.
"""

import os

from audio import audio_sys
from config import (
    BATTERY_CUE_CONDITIONS,
    CUE_AUDIO_MAX_SECONDS,
    HAPTIC_CORRECT_PATTERN,
    HAPTIC_CORRECT_POSITION,
    HAPTIC_INCORRECT_PATTERN,
    HAPTIC_INCORRECT_POSITION,
    get_cue_audio_paths,
)
from haptics import play_correct_cue, play_incorrect_cue
from state import state


def channels_for(condition):
    """("audio",), ("haptic",), ("audio", "haptic") or () for baseline / training without cues."""
    return BATTERY_CUE_CONDITIONS.get(condition, ())


def play_feedback(channels, is_correct, radio=None):
    played = {"audio_file": "", "haptic_pattern": "", "haptic_location": ""}
    if "haptic" in channels:
        if is_correct:
            play_correct_cue()
            played["haptic_pattern"], played["haptic_location"] = HAPTIC_CORRECT_PATTERN, HAPTIC_CORRECT_POSITION
        else:
            play_incorrect_cue()
            played["haptic_pattern"], played["haptic_location"] = HAPTIC_INCORRECT_PATTERN, HAPTIC_INCORRECT_POSITION
    if "audio" in channels:
        pos_wav, neg_wav = get_cue_audio_paths(state.audio_cue_mode)
        path = pos_wav if is_correct else neg_wav
        # fast path: mixed into the radio stream that is already open; otherwise a new stream
        if radio is None or not radio.play_cue(path, CUE_AUDIO_MAX_SECONDS):
            audio_sys.play_participant_clip(path, CUE_AUDIO_MAX_SECONDS)
        played["audio_file"] = os.path.basename(path)
    return played
