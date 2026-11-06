"""Check the 'deliver' voice trigger without the GUI or the camera.

    python voice_check.py                # Windows default microphone
    python voice_check.py --mic Bose     # microphone whose name contains "Bose"
    python voice_check.py --list         # only list the microphones

It checks the packages and the Vosk model, opens the microphone with the same code as the GUI and
the evaluator (voice.py), then for 30 s shows a volume bar, every word Vosk hears and each DELIVER.
"""

import argparse
import os
import sys
import time


def step(ok, text, fix=""):
    print(f"  [{'OK' if ok else 'FAIL'}] {text}" + (f"\n         -> {fix}" if (fix and not ok) else ""))
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mic", help="part of the microphone name (default: config.VOICE_INPUT_KEYWORD / Windows default)")
    ap.add_argument("--list", action="store_true", help="only list the microphones")
    ap.add_argument("--seconds", type=int, default=30)
    args = ap.parse_args()

    print("1) Packages")
    try:
        import sounddevice as sd
        step(True, "sounddevice")
    except Exception as e:
        step(False, f"sounddevice: {e}", "pip install sounddevice")
        return 1
    try:
        import vosk  # noqa: F401
        step(True, "vosk")
    except Exception as e:
        step(False, f"vosk: {e}", "pip install vosk")
        return 1
    try:
        import PyQt5  # noqa: F401
        step(True, "PyQt5")
    except Exception as e:
        step(False, f"PyQt5: {e}", "pip install PyQt5")
        return 1

    print("\n2) Microphones (input devices)")
    try:
        default_in = sd.default.device[0]
    except Exception:
        default_in = None
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            api = sd.query_hostapis(d["hostapi"])["name"]
            mark = "  <- Windows default" if i == default_in else ""
            print(f"  {i:3d}  {d['name']}  [{api}, {int(d['default_samplerate'])} Hz]{mark}")
    if args.list:
        return 0

    from config import DELIVER_WORDS, VOICE_INPUT_KEYWORD, VOSK_MODEL_DIR
    print("\n3) Vosk model")
    if not step(os.path.isdir(os.path.join(VOSK_MODEL_DIR, "am")), VOSK_MODEL_DIR,
                "the model/ folder must contain the unzipped Vosk model (am/, conf/, graph/ ...)"):
        return 1

    print("\n4) Opening the microphone (voice.py)")
    from voice import VoiceDeliverListener
    mic = args.mic or VOICE_INPUT_KEYWORD
    listener = VoiceDeliverListener(input_keyword=mic)
    if not step(listener.vosk_ready, listener.status or "model loaded"):
        return 1

    level = [0.0]
    heard = []
    delivers = []
    original_callback = listener._audio_callback

    def callback(indata, frames, time_info, status):
        level[0] = max(level[0] * 0.8, float(abs(indata).max()) / 32768.0)
        original_callback(indata, frames, time_info, status)

    listener._audio_callback = callback
    listener.on_text = lambda text, final: heard.append(text) if final else None
    listener._emit_deliver = lambda: delivers.append(time.time())
    listener.set_enabled(True)
    if not step(listener.stream is not None, listener.status,
                "pick another microphone with --mic (see the list above), or set the Bose as the Windows "
                "default input in Settings > System > Sound > Input"):
        return 1

    print(f"\n5) Speak now: say {' / '.join(w.upper() for w in DELIVER_WORDS)} a few times "
          f"({args.seconds} s, Ctrl+C to stop)\n")
    shown_heard, shown_del = 0, 0
    loudest = 0.0
    end = time.time() + args.seconds
    try:
        while time.time() < end:
            loudest = max(loudest, level[0])
            bar = "#" * int(min(1.0, level[0] * 4) * 40)
            sys.stdout.write(f"\r  volume |{bar:<40}|  delivers: {len(delivers)}   ")
            sys.stdout.flush()
            while shown_heard < len(heard):
                print(f"\n  heard: \"{heard[shown_heard]}\"")
                shown_heard += 1
            while shown_del < len(delivers):
                print("\n  >>> DELIVER detected <<<")
                shown_del += 1
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    listener.stop()

    print("\n\nResult")
    if delivers:
        print(f"  Voice works: {len(delivers)} deliver(s) detected on '{listener.device_name}'.")
        if mic:
            print(f"  Use it in the evaluator test with:  python live_evaluator.py --test --mic \"{mic}\"")
    elif loudest < 0.02:
        print("  The microphone stayed silent: wrong microphone, muted, or Windows blocks microphone access")
        print("  (Settings > Privacy & security > Microphone > let desktop apps access your microphone).")
    elif not heard:
        print("  Sound arrived but nothing was recognised: speak closer / louder, in English, one word at a time.")
    else:
        print("  Words were heard but not 'deliver': say DELIVER clearly as a single word.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
