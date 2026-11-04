"""Generate the plant-radio audio with the offline Windows voices (run once per language).

    pip install pywin32
    python generate_radio_audio.py --list-voices          # which voices this PC has
    python generate_radio_audio.py --lang all             # en + es + de
    python generate_radio_audio.py --lang es --voice Sabina
    python generate_radio_audio.py --lang de --rate -1    # slower (-10 .. 10)

Output: radio_audio/<lang>/<clip>.wav + manifest.json. Only missing or changed clips are made
(use --force to redo everything). Re-run after editing radio_script.py.

Missing a language? Windows Settings > Time & language > Speech > Add voices
(Spanish (Mexico) and German (Germany)). Voices installed there are "OneCore" voices; this
script also looks for those, so you usually do not need any registry tricks.
"""

import argparse
import json
import os
import sys
import tempfile
import time

import numpy as np
import soundfile as sf

from panel_logic import all_problems
from radio_script import LANGUAGES, all_clips, clips_hash, validate

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(BASE_DIR, "radio_audio")

# Windows LCIDs: preferred first, then any voice of the same primary language
LCID_PREFERENCE = {
    "en": ([0x409, 0x809], 0x09),           # en-US, en-GB
    "es": ([0x80A, 0x540A, 0xC0A], 0x0A),   # es-MX, es-US (Latin America), es-ES last
    "de": ([0x407, 0xC07, 0x807], 0x07),    # de-DE, de-AT, de-CH
}
PART_PAUSE_MS = 280          # pause between incident and command
TARGET_RMS_DB = -20.0        # same loudness for every clip and language
PEAK_LIMIT = 0.89


# ---------------------------------------------------------------------------
# Windows SAPI (desktop + OneCore voices)
# ---------------------------------------------------------------------------
class SapiEngine:
    ONECORE_KEY = r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices"

    def __init__(self):
        try:
            import win32com.client
        except ImportError:
            sys.exit("pywin32 is missing:  pip install pywin32   (Windows only)")
        self.client = win32com.client
        self.voice = win32com.client.Dispatch("SAPI.SpVoice")

    def voices(self):
        """[(name, lcids, source, token)]"""
        out = []
        sources = [("desktop", lambda: self.voice.GetVoices())]

        def onecore():
            cat = self.client.Dispatch("SAPI.SpObjectTokenCategory")
            cat.SetId(self.ONECORE_KEY, False)
            return cat.EnumerateTokens()
        sources.append(("onecore", onecore))

        seen = set()
        for source, getter in sources:
            try:
                tokens = getter()
            except Exception:
                continue
            for i in range(tokens.Count):
                tok = tokens.Item(i)
                try:
                    name = tok.GetDescription()
                    lang_attr = tok.GetAttribute("Language") or ""
                except Exception:
                    continue
                if name in seen:
                    continue
                seen.add(name)
                lcids = []
                for part in lang_attr.split(";"):
                    try:
                        lcids.append(int(part, 16))
                    except ValueError:
                        pass
                out.append((name, lcids, source, tok))
        return out

    def pick_voice(self, lang, name_hint=None):
        voices = self.voices()
        if name_hint:
            for v in voices:
                if name_hint.lower() in v[0].lower():
                    return v
            return None
        preferred, primary = LCID_PREFERENCE[lang]
        for lcid in preferred:
            for v in voices:
                if lcid in v[1]:
                    return v
        for v in voices:
            if any((l & 0x3FF) == primary for l in v[1]):
                return v
        return None

    def synth(self, token, rate, parts, path):
        from xml.sax.saxutils import escape
        xml = f'<silence msec="{PART_PAUSE_MS}"/>'.join(escape(p) for p in parts)
        fmt = self.client.Dispatch("SAPI.SpAudioFormat")
        fmt.Type = 22                                   # SAFT22kHz16BitMono
        stream = self.client.Dispatch("SAPI.SpFileStream")
        stream.Format = fmt
        stream.Open(path, 3, False)                     # SSFMCreateForWrite
        self.voice.Voice = token
        self.voice.Rate = rate
        self.voice.AudioOutputStream = stream
        try:
            self.voice.Speak(xml, 8)                    # SVSFIsXML, synchronous
        finally:
            stream.Close()
            self.voice.AudioOutputStream = None


class DummyEngine:
    """No speech: writes quiet tones with a realistic length. For testing on non-Windows PCs."""

    def voices(self):
        return [("Dummy " + l, [], "dummy", l) for l in LANGUAGES]

    def pick_voice(self, lang, name_hint=None):
        return ("Dummy " + lang, [], "dummy", lang)

    def synth(self, token, rate, parts, path):
        fs = 22050
        dur = max(1.0, sum(len(p) for p in parts) / 15.0)
        t = np.arange(int(fs * dur)) / fs
        x = 0.2 * np.sin(2 * np.pi * 220 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 3 * t))
        sf.write(path, x.astype(np.float32), fs, subtype="PCM_16")


# ---------------------------------------------------------------------------
# Post-processing: trim silence, equal loudness
# ---------------------------------------------------------------------------
def postprocess(path_in, path_out):
    x, fs = sf.read(path_in, dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if len(x) == 0 or np.max(np.abs(x)) == 0:
        raise RuntimeError("empty audio")
    thr = 0.02 * np.max(np.abs(x))
    idx = np.where(np.abs(x) > thr)[0]
    margin = int(0.04 * fs)
    x = x[max(0, idx[0] - margin): min(len(x), idx[-1] + margin)]
    rms = np.sqrt(np.mean(x ** 2)) + 1e-9
    x = x * (10 ** (TARGET_RMS_DB / 20) / rms)
    peak = np.max(np.abs(x))
    if peak > PEAK_LIMIT:
        x = x * (PEAK_LIMIT / peak)
    fade = int(0.01 * fs)
    x[:fade] *= np.linspace(0, 1, fade)
    x[-fade:] *= np.linspace(1, 0, fade)
    sf.write(path_out, x, fs, subtype="PCM_16")
    return len(x) / fs


# ---------------------------------------------------------------------------
def generate(engine, lang, voice_hint, rate, force):
    voice = engine.pick_voice(lang, voice_hint)
    if voice is None:
        print(f"\n[{lang}] No {LANGUAGES[lang]} voice found."
              f"\n  Install one: Settings > Time & language > Speech > Add voices,"
              f"\n  then run:  python generate_radio_audio.py --list-voices")
        return False
    name, _, source, token = voice
    out_dir = os.path.join(OUT_ROOT, lang)
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "manifest.json")
    old = {}
    if os.path.exists(manifest_path) and not force:
        with open(manifest_path, encoding="utf-8") as f:
            old = json.load(f)
    same_voice = old.get("voice") == name and old.get("rate") == rate

    clips = all_clips(lang, all_problems())
    entries = {}
    made = 0
    print(f"\n[{lang}] voice: {name} ({source}), rate {rate}, {len(clips)} clips")
    tmp_dir = tempfile.mkdtemp(prefix="radio_")
    t0 = time.time()
    for i, (cid, parts) in enumerate(clips.items(), 1):
        wav = os.path.join(out_dir, cid + ".wav")
        prev = old.get("clips", {}).get(cid)
        if same_voice and prev and prev.get("parts") == parts and os.path.exists(wav):
            entries[cid] = prev
            continue
        tmp = os.path.join(tmp_dir, cid + ".wav")
        try:
            engine.synth(token, rate, parts, tmp)
            dur = postprocess(tmp, wav)
        except Exception as e:
            print(f"  ! {cid}: {e}")
            continue
        entries[cid] = {"parts": parts, "duration_s": round(dur, 3)}
        made += 1
        if made % 25 == 0:
            print(f"  {i}/{len(clips)} ...")
    manifest = {
        "language": lang, "voice": name, "voice_source": source, "rate": rate,
        "script_hash": clips_hash(clips), "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "clips": entries,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    missing = len(clips) - len(entries)
    print(f"[{lang}] made {made}, kept {len(entries) - made}, failed {missing} "
          f"({time.time() - t0:.0f} s) -> {out_dir}")
    return missing == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", default="all", choices=list(LANGUAGES) + ["all"])
    ap.add_argument("--voice", help="substring of the voice name (only with a single --lang)")
    ap.add_argument("--rate", type=int, default=0, help="speech rate -10 (slow) .. 10 (fast), default 0")
    ap.add_argument("--force", action="store_true", help="regenerate every clip")
    ap.add_argument("--list-voices", action="store_true")
    ap.add_argument("--engine", default="sapi", choices=["sapi", "dummy"], help=argparse.SUPPRESS)
    args = ap.parse_args()

    issues = validate()
    if issues:
        print("radio_script.py has problems:\n  " + "\n  ".join(issues))
        sys.exit(1)

    engine = SapiEngine() if args.engine == "sapi" else DummyEngine()
    if args.list_voices:
        for name, lcids, source, _ in engine.voices():
            print(f"  {name:45s} {source:8s} " + ",".join(hex(l) for l in lcids))
        return
    langs = list(LANGUAGES) if args.lang == "all" else [args.lang]
    if args.voice and len(langs) > 1:
        sys.exit("--voice needs a single --lang")
    ok = all([generate(engine, l, args.voice, args.rate, args.force) for l in langs])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
