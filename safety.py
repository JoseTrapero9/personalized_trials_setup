"""Crash safety net: an error inside the program is logged and the session keeps running.

Without this, PyQt5 aborts the whole program on any unhandled error inside a button / timer / signal
handler (it calls qFatal), losing the running condition. With install():
  * the traceback is appended to logs/errors.log (with subject, condition and round),
  * an LSL marker Program_Error_<ErrorType> is sent, so it is visible in the recording,
  * the program continues. The same error repeating (e.g. inside a timer) is logged once per minute.
Errors in background threads go to the same log.
"""

import os
import sys
import threading
import time
import traceback

from config import base_dir
from state import state

ERROR_LOG = os.path.join(base_dir, "logs", "errors.log")
REPEAT_SECONDS = 60.0

_last_logged = {}        # (error type, file, line) -> time it was last written
_suppressed = {}         # same key -> repeats not written since


def _where(tb):
    frames = traceback.extract_tb(tb) if tb is not None else []
    return (os.path.basename(frames[-1].filename), frames[-1].lineno) if frames else ("?", 0)


def handle_error(exc_type, exc, tb, origin="main"):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    state.error_count += 1
    file, line = _where(tb)
    key = (exc_type.__name__, file, line)
    now = time.monotonic()
    if now - _last_logged.get(key, -1e9) < REPEAT_SECONDS:
        _suppressed[key] = _suppressed.get(key, 0) + 1
        return
    repeats = _suppressed.pop(key, 0)
    _last_logged[key] = now
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    header = (f"===== {time.strftime('%Y-%m-%d %H:%M:%S')}  {origin}  subject {state.subject_number}  "
              f"condition {state.current_condition}  error #{state.error_count}"
              + (f"  (+{repeats} repeats of this error not written)" if repeats else "") + " =====\n")
    try:
        os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(header + text + "\n")
    except Exception:
        pass
    try:
        sys.stderr.write(f"\n[PROGRAM ERROR - session continues, see {ERROR_LOG}]\n{text}")
    except Exception:
        pass
    try:
        from lsl_markers import send_marker
        send_marker(f"Program_Error_{exc_type.__name__}_{file}_{line}")
    except Exception:
        pass


def install():
    sys.excepthook = handle_error            # PyQt5 then calls this instead of aborting
    threading.excepthook = lambda a: handle_error(a.exc_type, a.exc_value, a.exc_traceback,
                                                  origin=f"thread {a.thread.name if a.thread else '?'}")
