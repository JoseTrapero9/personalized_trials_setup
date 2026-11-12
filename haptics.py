"""bHaptics vest: background asyncio thread, trigger and shutdown.

Two ways to reach the vest:
  * bhaptics_python (activate_haptic_vest): the manual mistake alert, unchanged.
  * bHaptics Player websocket (play_correct_cue / play_incorrect_cue): the per-battery cues, sent exactly
    like in the pre-study scripts (pre_study/testing_cues.py) so the patterns feel the same.
"""

import asyncio
import json
import threading
import time

from config import (
    HAPTIC_CORRECT_PATTERN,
    HAPTIC_CORRECT_POSITION,
    HAPTIC_INCORRECT_PATTERN,
    HAPTIC_INCORRECT_POSITION,
)

try:
    import websocket          # pip install websocket-client
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    print("WARNING: 'websocket-client' not installed -> per-battery vest cues DISABLED.")


# Third-party: haptic vest (needs Python 3.8-3.12 on Windows x64; vest modes are disabled if missing)
try:
    import bhaptics_python
    BHAPTICS_AVAILABLE = True
except ImportError:
    BHAPTICS_AVAILABLE = False
    print("WARNING: 'bhaptics_python' not installed -> haptic vest DISABLED "
          "(haptic and audio_haptic conditions will have NO vest feedback).")

haptic_loop = None


async def init_haptics():
    app_id = "6a97da355fa17dce7a1e0d7b"
    api_key = "LsHVhykpVUDmGRxVY0FB"
    await bhaptics_python.registry_and_initialize(app_id, api_key, "")
    print("bHaptics background connection established.")


async def trigger_vest_async():
    full_vest_pattern = [0] * 20 + [50] * 20
    await bhaptics_python.play_dot(0, 500, full_vest_pattern)


async def close_haptics():
    await bhaptics_python.stop_all()
    await bhaptics_python.close()
    print("bHaptics background connection closed.")


# ---------------------------------------------------------------------------
# Per-battery cues through the bHaptics Player websocket (same frames as the pre-study)
# ---------------------------------------------------------------------------
ALL_MOTORS = list(range(20))
CENTER_MOTORS = [1, 2, 5, 6, 9, 10, 13, 14, 17, 18]
OUTER_MOTORS = [0, 3, 4, 7, 8, 11, 12, 15, 16, 19]
PLAYER_URL = "ws://127.0.0.1:15881/v2/feedbacks?app_id=assembly_x16&app_name=Dual_Task_Paradigm"


class _PlayerLink:
    def __init__(self):
        self.connected = False
        self.ws_app = None
        self.sent = []            # (key, position, duration) of the last frames, for tests

    def start(self):
        if not WEBSOCKET_AVAILABLE or self.ws_app is not None:
            return

        def set_connected(value):
            if value and not self.connected:
                print("bHaptics Player connected (battery cues).")
            self.connected = value

        self.ws_app = websocket.WebSocketApp(
            PLAYER_URL,
            on_open=lambda ws: set_connected(True),
            on_close=lambda ws, code, msg: set_connected(False),
            on_error=lambda ws, err: set_connected(False),
        )

        def run_loop():
            while True:
                try:
                    self.ws_app.run_forever(ping_interval=5, ping_timeout=2)
                except Exception:
                    pass
                time.sleep(2.0)

        threading.Thread(target=run_loop, daemon=True).start()

    def frame(self, key, position, motors, intensity, duration_ms):
        self.sent.append((key, position, duration_ms))
        del self.sent[:-20]
        if not self.connected or self.ws_app is None:
            return
        payload = {"Submit": [{"Type": "frame", "Key": f"{key}_{time.time_ns()}", "Frame": {
            "position": position,
            "dotPoints": [{"index": int(i), "intensity": int(intensity)} for i in motors],
            "durationMillis": int(duration_ms),
            "pathPoints": []}}]}
        try:
            self.ws_app.send(json.dumps(payload))
        except Exception as e:
            print(f"bHaptics send error: {e}")


player = _PlayerLink()


def _positive_3(position):
    """Warm swell: centre -> whole panel -> outer ring (about 0.5 s)."""
    player.frame("p3_1", position, CENTER_MOTORS, 25, 150)
    time.sleep(0.14)
    player.frame("p3_2", position, ALL_MOTORS, 55, 200)
    time.sleep(0.14)
    player.frame("p3_3", position, OUTER_MOTORS, 25, 200)


def _negative_2(position):
    """Sharp staccato: three full-strength bursts (about 0.5 s)."""
    for step in range(3):
        player.frame(f"n2_{step}", position, ALL_MOTORS, 100, 120 if step == 2 else 100)
        if step < 2:
            time.sleep(0.18)


CUE_PATTERNS = {"positive_3": _positive_3, "negative_2": _negative_2}


def play_correct_cue():
    threading.Thread(target=CUE_PATTERNS[HAPTIC_CORRECT_PATTERN], args=(HAPTIC_CORRECT_POSITION,),
                     daemon=True).start()


def play_incorrect_cue():
    threading.Thread(target=CUE_PATTERNS[HAPTIC_INCORRECT_PATTERN], args=(HAPTIC_INCORRECT_POSITION,),
                     daemon=True).start()


def start_haptic_thread():
    global haptic_loop
    player.start()
    if not BHAPTICS_AVAILABLE:
        return
    haptic_loop = asyncio.new_event_loop()
    t = threading.Thread(target=haptic_loop.run_forever, daemon=True)
    t.start()
    asyncio.run_coroutine_threadsafe(init_haptics(), haptic_loop)


def activate_haptic_vest():
    if haptic_loop is not None:
        asyncio.run_coroutine_threadsafe(trigger_vest_async(), haptic_loop)


def shutdown_haptics():
    if haptic_loop is None:
        return
    future = asyncio.run_coroutine_threadsafe(close_haptics(), haptic_loop)
    try:
        future.result(timeout=2)
    except Exception:
        pass
    haptic_loop.call_soon_threadsafe(haptic_loop.stop)
