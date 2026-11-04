"""bHaptics vest: background asyncio thread, trigger and shutdown."""

import asyncio
import threading


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


def start_haptic_thread():
    global haptic_loop
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
