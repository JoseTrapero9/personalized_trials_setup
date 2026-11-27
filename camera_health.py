"""XIMEA camera health: USB link check + bandwidth limit at start, and a log of every camera loss.

Used by live_evaluator.py (MC050) and ximea_recorder.py (MQ013).

Why: at 30 fps the camera sends about 300 Mbit/s (RAW8, the colour image is made on the PC). A USB 3 link
(~3000+ Mbit/s) handles that easily; a USB 2 link (~300-400 Mbit/s in practice: black port, USB 2 cable or hub,
or a USB 3 port that fell back to USB 2) is at its limit -> timeouts (XIMEA error 10) and lost cameras.
"""

import csv
import os
import socket
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EVENT_LOG = os.path.join(BASE_DIR, "logs", "camera_events.csv")

BANDWIDTH_LIMIT_PERCENT = 90      # limit the camera to this share of the measured USB bandwidth (0 = no limit)
USB2_BELOW_MBIT = 1000            # less than this available = the camera runs at USB 2 speed


def usb_check(cam, fps, say, limit_percent=BANDWIDTH_LIMIT_PERCENT):
    """Call after the camera settings and BEFORE start_acquisition(). Reports through say('USB ...')."""
    def get(name):
        try:
            return cam.get_param(name)
        except Exception:
            return None

    avail = get("available_bandwidth")              # Mbit/s, measured by the XIMEA driver
    w, h = get("width"), get("height")
    try:
        avail = float(avail) if avail is not None else None
    except (TypeError, ValueError):
        avail = None
    need = (float(w) * float(h) * 8 * float(fps) / 1e6) if w and h else None   # RAW8 on the cable
    limited = None
    if avail and limit_percent:
        try:
            cam.set_param("limit_bandwidth_mode", "XI_ON")
            limited = int(avail * limit_percent / 100)
            cam.set_param("limit_bandwidth", limited)
        except Exception:
            limited = None
    parts = [f"USB link: {avail:.0f} Mbit/s available" if avail else "USB link: speed unknown"]
    if need:
        parts.append(f"camera needs ~{need:.0f} Mbit/s ({w}x{h} @ {fps:g} fps)")
    if limited:
        parts.append(f"limited to {limited} Mbit/s")
    msg = ", ".join(parts)
    if avail and avail < USB2_BELOW_MBIT:
        msg += (" -> USB 2 SPEED: frames will be lost. Use a blue USB 3 port directly on the PC (no hub, no "
                "extension), the camera's own USB 3 cable, and check that the plug is fully in.")
    elif avail and need and need > 0.7 * avail:
        msg += " -> close to the limit: lower the fps or use another USB controller"
    say("USB " + msg)
    return avail, need


def log_event(camera, event, seconds_without_frames=None, detail="", restarts=0):
    """One line per camera event in logs/camera_events.csv (to see when and how often it happens)."""
    try:
        os.makedirs(os.path.dirname(EVENT_LOG), exist_ok=True)
        new = not os.path.exists(EVENT_LOG)
        with open(EVENT_LOG, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "pc", "camera", "event", "seconds_without_frames", "restarts", "detail"])
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), socket.gethostname(), camera, event,
                        "" if seconds_without_frames is None else round(seconds_without_frames, 1), restarts, detail])
    except Exception:
        pass
