"""Real-time video files written by a separate process (used by live_evaluator.py and ximea_recorder.py).

Why a process: encoding a video costs CPU time. Done in the camera / model process it competes with the model
(Python's GIL, cache, threads). Here the caller only copies each frame once into shared memory (about 1 ms for
a 1.3 MP colour frame) and hands over a slot number; a background process at lower priority does the encoding.
If that process falls behind, frames are left out on the caller's side (no waiting, nothing blocks) and the
file gets a repeat of the previous frame instead, so the video always stays in real time.

Real time: frame N of the file belongs to  t0 + N / fps,  t0 = LSL time of the first frame. A frame that arrives
early for its slot is skipped (cheap, it is never copied), a gap is filled by repeating the previous frame.
So a Recording_Start marker stamped with t0 is enough to place every frame on the LSL time line.

    w = BackgroundVideoWriter("mc050", on_closed=print)
    w.start("recordings/s03_audio_mc050_20261125_101500.mp4", 30)
    first = w.add(frame, pylsl.local_clock())     # True for the first frame of the file -> send the start marker
    w.stop()                                       # returns at once; on_closed(info) when the file is complete
    w.close()                                      # at the end of the program (waits for the last file)
"""

import os
import queue
import sys
import threading
import time

VIDEO_FOURCC = "mp4v"
RING_SLOTS = 64                  # frames that can wait for the encoder (~1 s at 60 fps, ~2 s at 30 fps) before frames are left out


def _lower_priority():
    try:
        if sys.platform == "win32":
            import ctypes
            BELOW_NORMAL_PRIORITY_CLASS = 0x4000
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),
                                                    BELOW_NORMAL_PRIORITY_CLASS)
        else:
            os.nice(5)
    except Exception:
        pass


def _writer_main(cmd_q, free_q, done_q):
    """Encoder process. Commands: ("ring", gen, shm_name, slot_bytes) / ("open", path, fps) /
    ("frame", gen, slot, shape, index) / ("close",) / ("quit",)."""
    import numpy as np
    import cv2
    from multiprocessing import shared_memory
    _lower_priority()
    try:
        cv2.setNumThreads(2)
    except Exception:
        pass
    rings = {}
    out = path = last = None
    fps = 30.0
    written = repeated = dropped = 0
    error = ""

    def close_file():
        nonlocal out, path, last, written, repeated, dropped, error
        if path is None:
            return
        if out is not None:
            try:
                out.release()
            except Exception as e:
                error = error or str(e)
        done_q.put({"path": path, "written": written, "repeated": repeated, "dropped": dropped, "fps": fps,
                    "error": error})
        out = path = last = None
        written = repeated = dropped = 0
        error = ""

    while True:
        cmd = cmd_q.get()
        kind = cmd[0]
        if kind == "ring":
            _, gen, name, slot_bytes = cmd
            try:
                rings[gen] = (shared_memory.SharedMemory(name=name), slot_bytes)
            except Exception as e:
                error = f"shared memory: {e}"
        elif kind == "open":
            close_file()
            path, fps = cmd[1], float(cmd[2])
        elif kind == "frame":
            _, gen, slot, shape, index = cmd
            try:
                if path is None or error:
                    continue
                shm, slot_bytes = rings[gen]
                frame = np.ndarray(shape, np.uint8, buffer=shm.buf, offset=slot * slot_bytes)
                if out is None:
                    h, w = shape[:2]
                    out = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*VIDEO_FOURCC), fps, (w, h), len(shape) == 3)
                    if not out.isOpened():
                        raise RuntimeError(f"cannot open the video file {path}")
                if index < written:
                    dropped += 1
                    continue
                while written < index and last is not None:     # gap: repeat the previous frame
                    out.write(last)
                    written += 1
                    repeated += 1
                out.write(frame)
                written += 1
                if last is None or last.shape != frame.shape or last.dtype != frame.dtype:
                    last = frame.copy()                          # the slot is reused once it is freed
                else:
                    np.copyto(last, frame)                       # reuse buffer (no per-frame allocation)
            except Exception as e:
                error = str(e)
            finally:
                free_q.put((gen, slot))
        elif kind == "close":
            close_file()
        elif kind == "quit":
            close_file()
            break
    for shm, _ in rings.values():
        try:
            shm.close()
        except Exception:
            pass


class BackgroundVideoWriter:
    """One encoder process, kept running for the whole program (no start-up delay per file). One file at a time.
    Thread-safe: add() may be called from the camera thread while start() / stop() come from another thread."""

    def __init__(self, name="video", on_closed=None, slots=RING_SLOTS):
        import multiprocessing as mp
        self.name, self.on_closed, self.n_slots = name, on_closed, slots
        self.ctx = mp.get_context("spawn")
        self.cmd_q, self.free_q, self.done_q = self.ctx.Queue(), self.ctx.Queue(), self.ctx.Queue()
        self.proc = self.ctx.Process(target=_writer_main, args=(self.cmd_q, self.free_q, self.done_q),
                                     daemon=True, name=f"video-writer-{name}")
        self.proc.start()
        self._lock = threading.Lock()
        self._rings = []                       # [(gen, SharedMemory)] kept until close()
        self._gen, self._slot_bytes, self._free = 0, 0, []
        self.path = None
        self.fps = 30.0
        self.t0 = None
        self.next_index = 0                    # next file frame still to be filled
        self.left_out = 0                      # frames not handed over because the encoder was behind
        self.started_at = None
        self._t0s = {}                         # path -> t0 (for the stop marker time)
        self._pending = 0                      # files closed but not yet confirmed
        self._waiter = threading.Thread(target=self._wait_done, daemon=True)
        self._waiter.start()

    # ---------------- control
    def start(self, path, fps):
        with self._lock:
            if self.path is not None:
                self._stop_locked()
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            self.path, self.fps, self.t0 = path, float(fps), None
            self.next_index, self.left_out, self.started_at = 0, 0, time.time()
            self.cmd_q.put(("open", path, self.fps))

    def stop(self):
        """Ends the current file. Returns at once; on_closed(info) is called when the encoder has finished it."""
        with self._lock:
            self._stop_locked()

    def _stop_locked(self):
        if self.path is None:
            return
        self._t0s[self.path] = (self.t0, self.left_out)
        self._pending += 1
        self.cmd_q.put(("close",))
        self.path = None

    @property
    def recording(self):
        return self.path is not None

    @property
    def alive(self):
        return self.proc.is_alive()

    # ---------------- frames
    def add(self, frame, t):
        """Hand a frame over (t = LSL time of the frame). Never blocks. True for the first frame of the file."""
        import numpy as np
        with self._lock:
            if self.path is None:
                return False
            first = self.t0 is None
            if first:
                self.t0 = t
            index = int(round((t - self.t0) * self.fps))
            if index < self.next_index:               # early for its slot: skip it without copying
                return first
            if frame.dtype != np.uint8:
                frame = frame.astype(np.uint8)
            if frame.nbytes > self._slot_bytes:
                self._new_ring(frame.nbytes)
            self._collect_free()
            if not self._free:                         # encoder behind: leave it out, a repeat fills the hole
                self.left_out += 1
                return first
            slot = self._free.pop()
            shm = self._rings[-1][1]
            np.ndarray(frame.shape, np.uint8, buffer=shm.buf, offset=slot * self._slot_bytes)[:] = frame
            self.cmd_q.put(("frame", self._gen, slot, tuple(frame.shape), index))
            self.next_index = index + 1
            return first

    def _collect_free(self):
        try:
            while True:
                gen, slot = self.free_q.get_nowait()
                if gen == self._gen:
                    self._free.append(slot)
        except queue.Empty:
            pass

    def _new_ring(self, nbytes):
        from multiprocessing import shared_memory
        self._gen += 1
        self._slot_bytes = nbytes
        shm = shared_memory.SharedMemory(create=True, size=nbytes * self.n_slots)
        self._rings.append((self._gen, shm))
        self._free = list(range(self.n_slots))
        self.cmd_q.put(("ring", self._gen, shm.name, nbytes))

    # ---------------- results
    def _wait_done(self):
        while True:
            try:
                info = self.done_q.get(timeout=0.5)
            except queue.Empty:
                if not self.proc.is_alive() and self.done_q.empty():
                    return
                continue
            except (EOFError, OSError):
                return
            with self._lock:
                t0, left_out = self._t0s.pop(info["path"], (None, 0))
                self._pending = max(0, self._pending - 1)
            info["t0"] = t0
            info["left_out"] = left_out
            info["seconds"] = info["written"] / info["fps"] if info["fps"] else 0.0
            info["end_time"] = None if t0 is None else t0 + info["seconds"]
            if self.on_closed is not None:
                try:
                    self.on_closed(info)
                except Exception as e:
                    print(f"[REC] {e!r}")

    def status(self):
        """Short text for a window: '' when not recording."""
        with self._lock:
            if self.path is None:
                return ""
            secs = time.time() - (self.started_at or time.time())
            text = f"REC {os.path.basename(self.path)}  {secs:4.0f} s"
            if self.t0 is None:
                text += "  (waiting for frames)"
            if self.left_out:
                text += f"  {self.left_out} left out"
        if not self.proc.is_alive():
            text += "  WRITER STOPPED"
        return text

    def close(self, timeout=60.0):
        """Finish the current file and end the encoder process (waits for the file to be complete)."""
        self.stop()
        self.cmd_q.put(("quit",))
        self.proc.join(timeout)
        if self.proc.is_alive():
            self.proc.terminate()
        end = time.time() + 5.0
        while self._pending and time.time() < end and self._waiter.is_alive():
            time.sleep(0.05)
        for _, shm in self._rings:
            try:
                shm.close()
                shm.unlink()
            except Exception:
                pass
