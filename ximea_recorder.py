"""Video recorder for the third PC: the second XIMEA camera (MQ013) + a face webcam, synchronised with LSL.

Only records video: no model, no detection. XIMEA settings come from old_code/3CAM_Stream (MQ013 preset).

    python ximea_recorder.py                 # records every condition / training block automatically
    python ximea_recorder.py --manual        # only R starts / stops a recording
    python ximea_recorder.py --fps 25        # other frame rate (cameras and videos, default 30)
    python ximea_recorder.py --webcam 1      # the face webcam is camera 1 (default 0)
    python ximea_recorder.py --no-webcam     # XIMEA only
    python ximea_recorder.py --out D:\\videos

Both cameras start and stop together, and live_evaluator.py on the camera PC starts / stops its own video at the
same moment (it follows this program's LSL markers), so the three videos of a condition belong together:
    <out>/sXX_<condition>_mq013_<stamp>.mp4     (this PC)
    <out>/sXX_<condition>_webcam_<stamp>.mp4    (this PC)
    recordings/sXX_<condition>_mc050_<stamp>.mp4   (camera PC, live_evaluator.py; same <stamp>)

Synchronisation (LSL)
  * One marker stream "ximeasync_mq013" (strings), recorded by LabRecorder with the GUI markers; LSL corrects
    the clock offset between the PCs:
        Recording_Session_Start_<label>_<stamp>     a recording starts (the evaluator starts its video on it)
        Recording_Start_<file>                      per video, stamped with the capture time of its first frame
        Recording_Stop_<file>_Frames_<n>_Seconds_<s>   per video, stamped with the end of its last frame
        Recording_Session_Stop_<label>_<stamp>      the recording ends (the evaluator stops its video)
    The evaluator sends Eval_Recording_Start_<file> / Eval_Recording_Stop_... the same way on its own stream.
  * Every video keeps real time: frame N was captured at  start + N / fps.  If a camera skips a frame (or the
    PC cannot keep up) the previous frame is repeated; a frame that arrives early is dropped. So the start
    marker is enough to place every frame on the LSL time line.
  * Only if a camera drops out: Camera_Lost / Camera_Restored, Webcam_Lost / Webcam_Restored (the video shows
    the last frame meanwhile).

Recording control
  * Automatic (default): follows the GUI over LSL ("ParadigmMarkers"). Starts at Condition_Start_<condition>
    (training: every block), stops at Condition_Complete / back to the menu / GUI closed.
  * R starts / stops a manual recording at any time. Q / Esc stops cleanly and quits.
  * The window shows both cameras live while they record (red dot = recording).

Performance: the XIMEA camera runs in its own process (restarted if no frame arrives for 3 s, XIMEA error 10 /
USB problem; the recording continues in the same file), the webcam in its own thread, and each video is
encoded by its own background process (video_writer.py), so encoding never delays the capture.
"""

import argparse
import os
import queue
import re
import sys
import threading
import time
from datetime import datetime

from video_writer import BackgroundVideoWriter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ================= CAMERA SETTINGS (from old_code/3CAM_Stream) =================
CAMERA_PRESETS = {
    "MQ013": {                       # the camera this recorder is for
        "name_match": "MQ013", "id": "mq013",
        "exposure": 25000, "gain": 8.0, "gammaY": 0.47, "wb_kr": 1.00, "wb_kb": 2.05, "binning": False,
        "lsl_stream_name": "ximeasync_mq013", "lsl_source_id": "cam_sync_mq013",
    },
    "MC050": {                       # the evaluator camera (camera PC) - only if you ever need to record it here
        "name_match": "MC050", "id": "mc050",
        "exposure": 32000, "gain": 10.0, "gammaY": 0.47, "wb_kr": 1.50, "wb_kb": 2.80, "binning": True,
        "lsl_stream_name": "ximeasync_mc050", "lsl_source_id": "cam_sync_mc050",
    },
}
DEFAULT_CAMERA = "MQ013"
FPS = 60.0                           # camera + video frame rate (--fps); XIMEA: acq_timing_mode = FRAME_RATE
XIMEA_API_PATH = r"C:\XIMEA\API\Python\v3"
RECORDINGS_DIR = os.path.join(BASE_DIR, "recordings")
VIDEO_EXT = ".mp4"
WEBCAM_INDEX = 1                     # face webcam (--webcam N); 0 = first camera Windows finds
WEBCAM_SIZE = "1280x960"             # --webcam-size
PREVIEW_FPS = 15                     # preview window refresh
GUI_MARKER_STREAM = "ParadigmMarkers"
TRAINING_PREFIX = "TRAIN_"
FRAME_TIMEOUT_MS = 1000
RESTART_SECONDS = 3.0                # no frame this long -> camera process restarted
OPEN_SECONDS = 20.0
SHM_BYTES = 32 * 1024 * 1024
# ===============================================================================


# ---------------------------------------------------------------------------
# Camera process
# ---------------------------------------------------------------------------
def _camera_worker(preset, fps, sys_path, shm_name, meta_i, meta_f, lock, new_frame, status_q):
    """Own process: opens the camera, copies each frame + its LSL arrival time into shared memory."""
    import numpy as np
    from multiprocessing import shared_memory
    sys.path[:] = sys_path
    if XIMEA_API_PATH not in sys.path:
        sys.path.append(XIMEA_API_PATH)
    shm = shared_memory.SharedMemory(name=shm_name)

    def say(text):
        try:
            status_q.put_nowait(text)
        except Exception:
            pass

    try:
        import pylsl
        from ximea import xiapi
    except Exception as e:
        say(f"CAMERA: cannot load the XIMEA API / pylsl ({e})")
        return

    def open_camera():
        probe = xiapi.Camera()
        for i in range(probe.get_number_devices()):
            cam = xiapi.Camera(dev_id=i)
            cam.open_device()
            raw = cam.get_param("device_name")
            name = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            if preset["name_match"] not in name:
                cam.close_device()
                continue
            cam.set_imgdataformat("XI_RGB24")
            if preset.get("binning", False):
                try:
                    cam.set_param("downsampling_type", "XI_BINNING")
                    cam.set_param("downsampling", "XI_DWN_2x2")
                except Exception:
                    try:
                        cam.set_param("downsampling", "XI_DWN_2x2")
                    except Exception:
                        pass
            cam.set_exposure(preset["exposure"])
            cam.set_gain(preset["gain"])
            cam.set_gammaY(preset["gammaY"])
            cam.set_param("wb_kr", preset["wb_kr"])
            cam.set_param("wb_kb", preset["wb_kb"])
            try:
                cam.set_param("acq_timing_mode", "XI_ACQ_TIMING_MODE_FRAME_RATE")
                cam.set_param("framerate", float(fps))
            except Exception:
                try:
                    cam.set_param("framerate", float(fps))
                except Exception:
                    pass
            cam.start_acquisition()
            return cam, name
        raise RuntimeError(f"no camera matching '{preset['name_match']}' found")

    cam = None
    while cam is None:
        try:
            cam, name = open_camera()
            say(f"OPENED {name}")
        except Exception as e:
            say(f"CAMERA NOT FOUND - check the USB cable ({e})")
            time.sleep(2.0)
    img = xiapi.Image()
    while True:
        try:
            cam.get_image(img, timeout=FRAME_TIMEOUT_MS)
        except xiapi.Xi_error as err:
            say(f"CAMERA: no frames (XIMEA error {getattr(err, 'status', '?')})")
            continue
        t_lsl = pylsl.local_clock()                       # arrival time on this PC's LSL clock
        frame = np.ascontiguousarray(img.get_image_data_numpy())
        if frame.ndim == 2:
            frame = frame[:, :, None]
        if frame.nbytes > shm.size:
            say("CAMERA: frame larger than the shared buffer")
            continue
        cam_ts = getattr(img, "tsSec", 0) + getattr(img, "tsUSec", 0) / 1e6
        with lock:
            np.ndarray(frame.shape, np.uint8, buffer=shm.buf)[:] = frame
            meta_i[1], meta_i[2], meta_i[3] = frame.shape
            meta_i[4] = int(getattr(img, "nframe", 0))
            meta_f[0], meta_f[1] = t_lsl, cam_ts
            meta_i[0] += 1
        new_frame.set()


class CameraSource:
    """Camera in a separate process, restarted when frames stop. Frames arrive in .frames as
    (frame, lsl_time, camera_nframe, camera_time_s); .status is '' while frames arrive."""

    def __init__(self, preset, fps, on_event=None):
        import multiprocessing as mp
        from multiprocessing import shared_memory
        self.preset, self.fps, self.on_event = preset, fps, on_event or (lambda e: None)
        self.ctx = mp.get_context("spawn")
        self.shm = shared_memory.SharedMemory(create=True, size=SHM_BYTES)
        self.frames = queue.Queue(maxsize=4)
        self.status = "CAMERA: starting"
        self.restarts = 0
        self.running = True
        self.proc = None
        self.thread = threading.Thread(target=self._supervise, daemon=True)

    def start(self):
        self.thread.start()

    def _spawn(self):
        self.meta_i = self.ctx.Array("q", 5, lock=False)
        self.meta_f = self.ctx.Array("d", 2, lock=False)
        self.lock = self.ctx.Lock()
        self.new_frame = self.ctx.Event()
        self.status_q = self.ctx.Queue()
        self.proc = self.ctx.Process(target=_camera_worker, daemon=True, args=(
            self.preset, self.fps, list(sys.path), self.shm.name, self.meta_i, self.meta_f, self.lock,
            self.new_frame, self.status_q))
        self.proc.start()
        self.seen, self.last_frame, self.opened, self.spawned = 0, None, None, time.monotonic()

    def _kill(self):
        proc, self.proc = self.proc, None
        if proc is not None:
            try:
                proc.terminate()
                proc.join(2.0)
                if proc.is_alive():
                    proc.kill()
                    proc.join(2.0)
            except Exception:
                pass

    def _supervise(self):
        import numpy as np
        self._spawn()
        lost = False
        while self.running:
            got = self.new_frame.wait(0.1)
            now = time.monotonic()
            try:
                while True:
                    msg = self.status_q.get_nowait()
                    if msg.startswith("OPENED"):
                        print(f"[CAMERA] {msg[7:]} opened")
                        self.opened = now
                    elif msg != self.status:
                        print(f"[CAMERA] {msg}")
                        self.status = msg
            except queue.Empty:
                pass
            if got:
                self.new_frame.clear()
                item = None
                if self.lock.acquire(timeout=0.5):
                    try:
                        if self.meta_i[0] != self.seen:
                            self.seen = self.meta_i[0]
                            shape = (self.meta_i[1], self.meta_i[2], self.meta_i[3])
                            frame = np.ndarray(shape, np.uint8, buffer=self.shm.buf).copy()
                            item = (frame if shape[2] != 1 else frame[:, :, 0], self.meta_f[0],
                                    int(self.meta_i[4]), self.meta_f[1])
                    finally:
                        self.lock.release()
                if item is not None:
                    if lost:
                        self.on_event("Camera_Restored")
                        lost = False
                    if self.status:
                        print("[CAMERA] frames are arriving")
                    self.status, self.last_frame = "", now
                    try:
                        self.frames.put_nowait(item)
                    except queue.Full:                      # main loop busy: newest frame wins
                        try:
                            self.frames.get_nowait()
                        except queue.Empty:
                            pass
                        self.frames.put_nowait(item)
                    continue
            if self.last_frame is not None or self.opened is not None:
                since = now - (self.last_frame if self.last_frame is not None else self.opened)
                stalled = since > RESTART_SECONDS
                if since > 1.0 and not self.status:
                    self.status = "CAMERA: no frames"
            else:
                stalled = now - self.spawned > OPEN_SECONDS and not self.status.startswith("CAMERA NOT FOUND")
            if stalled or not self.proc.is_alive():
                self.restarts += 1
                if not lost:
                    self.on_event("Camera_Lost")
                    lost = True
                print(f"[CAMERA] no frames - restarting the camera (restart {self.restarts})")
                self.status = f"CAMERA LOST - restarting the camera (restart {self.restarts})"
                self._kill()
                time.sleep(0.5)
                if self.running:
                    self._spawn()

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(3.0)
        self._kill()
        try:
            self.shm.close()
            self.shm.unlink()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Webcam (face camera)
# ---------------------------------------------------------------------------
class WebcamSource(threading.Thread):
    """A normal USB webcam (face camera) read in its own thread. Each frame is stamped with the LSL clock
    when it arrives and given to on_frame(frame, lsl_time). Reopened automatically if it stops delivering."""

    def __init__(self, index, fps, size=None, on_frame=None, on_event=None):
        super().__init__(daemon=True)
        self.index, self.fps, self.size = index, fps, size
        self.on_frame = on_frame or (lambda f, t: None)
        self.on_event = on_event or (lambda e: None)
        self.status = "WEBCAM: starting"
        self.latest = None
        self.fps_now = 0.0
        self.running = True

    def _open(self, cv2):
        api = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.index, api)
        if not cap.isOpened():
            cap.release()
            return None
        if self.size:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.size[0])
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.size[1])
        cap.set(cv2.CAP_PROP_FPS, float(self.fps))
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[WEBCAM] camera {self.index} opened: {w}x{h}, {cap.get(cv2.CAP_PROP_FPS):g} fps reported")
        return cap

    def run(self):
        import cv2
        import pylsl
        cap, lost, fails, count, t_fps = None, False, 0, 0, time.monotonic()
        while self.running:
            if cap is None:
                cap = self._open(cv2)
                if cap is None:
                    if self.status != "WEBCAM NOT FOUND - check the USB cable":
                        self.status = "WEBCAM NOT FOUND - check the USB cable"
                        print(f"[WEBCAM] {self.status} (index {self.index})")
                    time.sleep(2.0)
                    continue
            ok, frame = cap.read()
            if not ok or frame is None:
                fails += 1
                if fails > 30:                               # about 1-3 s without a frame: reopen it
                    if not lost:
                        self.on_event("Webcam_Lost")
                        lost = True
                    self.status = "WEBCAM LOST - reopening"
                    print(f"[WEBCAM] {self.status}")
                    cap.release()
                    cap, fails = None, 0
                time.sleep(0.03)
                continue
            t = pylsl.local_clock()
            fails = 0
            if lost:
                self.on_event("Webcam_Restored")
                lost = False
            self.status = ""
            self.latest = frame
            self.on_frame(frame, t)
            count += 1
            now = time.monotonic()
            if now - t_fps >= 1.0:
                self.fps_now, count, t_fps = count / (now - t_fps), 0, now
        if cap is not None:
            cap.release()

    def stop(self):
        self.running = False
        self.join(3.0)


# ---------------------------------------------------------------------------
# GUI markers (automatic start / stop)
# ---------------------------------------------------------------------------
class GuiMarkerListener(threading.Thread):
    def __init__(self, out_q):
        super().__init__(daemon=True)
        self.out_q, self.running, self.connected = out_q, True, False

    def run(self):
        import pylsl
        lost_error = getattr(pylsl, "LostError", None) or pylsl.util.LostError
        while self.running:
            streams = pylsl.resolve_byprop("name", GUI_MARKER_STREAM, 1, 1.0)
            if not streams:
                continue
            inlet = pylsl.StreamInlet(streams[0], max_buflen=60, recover=False)
            print(f"[LSL] Connected to GUI markers on {streams[0].hostname()}")
            self.connected = True
            try:
                while self.running:
                    sample, _ = inlet.pull_sample(timeout=0.2)
                    if sample:
                        self.out_q.put(str(sample[0]))
            except lost_error:
                print("[LSL] GUI marker stream lost - waiting for it to come back...")
            finally:
                self.connected = False


def subject_tag(subject):
    try:
        return f"s{int(subject):02d}"
    except (TypeError, ValueError):
        return f"s_{subject}"


class Recorder:
    """Ties the cameras, the LSL outlet, the video files and the GUI markers together (used by main()).
    sources: {source_id: label for the file name}, e.g. {"mq013": "mq013", "webcam": "webcam"}."""

    def __init__(self, preset, out_dir, sources, fps=FPS, auto=True):
        import pylsl
        self.preset, self.out_dir, self.auto, self.fps = preset, out_dir, auto, float(fps)
        os.makedirs(out_dir, exist_ok=True)
        info = pylsl.StreamInfo(preset["lsl_stream_name"], "Markers", 1, 0, "string", preset["lsl_source_id"])
        info.desc().append_child_value("camera", preset["name_match"])
        info.desc().append_child_value("cameras", ",".join(sources))
        info.desc().append_child_value("video_fps", f"{self.fps:g}")
        self.outlet = pylsl.StreamOutlet(info)
        self.sources = dict(sources)
        # one encoder process per camera: the two videos are written in parallel and never slow the capture
        self.writers = {sid: BackgroundVideoWriter(sid, on_closed=self._closed) for sid in self.sources}
        self.session = None                 # (label, stamp) of the running recording
        self.subject, self.condition = None, None
        self.fps_now, self._fps_count, self._fps_t = 0.0, 0, time.monotonic()
        self.last_file = ""

    def marker(self, text, timestamp=None):
        if timestamp is None:
            self.outlet.push_sample([text])
        else:
            self.outlet.push_sample([text], timestamp)
        print(f"[MARK] {text}")

    # ---------------- recordings
    def start(self, label):
        self.stop()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session = (label, stamp)
        # tells the other PCs (live_evaluator.py) to start their own video with the same name
        self.marker(f"Recording_Session_Start_{label}_{stamp}")
        for sid, writer in self.writers.items():
            name = f"{label}_{self.sources[sid]}_{stamp}{VIDEO_EXT}"
            writer.start(os.path.join(self.out_dir, name), self.fps)
            print(f"[REC] waiting for the first frame -> {name}")
        self.last_file = f"{label}_*_{stamp}{VIDEO_EXT}"

    def stop(self):
        if self.session is None:
            return
        label, stamp = self.session
        self.session = None
        for writer in self.writers.values():
            if writer.recording and writer.t0 is None:          # no frame arrived at all
                self.marker(f"Recording_Failed_No_Frames_{os.path.basename(writer.path)}")
            writer.stop()                                       # Recording_Stop marker once the file is complete
        self.marker(f"Recording_Session_Stop_{label}_{stamp}")

    def _closed(self, info):
        name = os.path.basename(info["path"])
        if info["t0"] is None:
            return
        self.marker(f"Recording_Stop_{name}_Frames_{info['written']}_Seconds_{info['seconds']:.2f}", info["end_time"])
        if info["repeated"] or info["dropped"] or info["left_out"]:
            print(f"[REC] {name}: {info['repeated']} frame(s) repeated to fill gaps "
                  f"({info['left_out']} left out because the PC was busy), {info['dropped']} early frame(s) skipped")
        if info["error"]:
            print(f"[REC] ERROR in {name}: {info['error']}")

    # ---------------- input
    def on_frame(self, source, frame, lsl_time):
        writer = self.writers.get(source)
        if writer is not None and writer.add(frame, lsl_time):
            # first frame of the file: its capture time is the start of the video
            self.marker(f"Recording_Start_{os.path.basename(writer.path)}", lsl_time)
        if source == "mq013" or source == self.preset["id"]:
            self._fps_count += 1
            now = time.monotonic()
            if now - self._fps_t >= 1.0:
                self.fps_now, self._fps_count, self._fps_t = self._fps_count / (now - self._fps_t), 0, now

    def on_gui_marker(self, marker):
        m = marker[len(TRAINING_PREFIX):] if marker.startswith(TRAINING_PREFIX) else marker
        if (r := re.match(r"^Setup_Complete_Subj_(.+?)_Cond_(.+?)_Lang_", m)):
            self.subject, self.condition = r.group(1), r.group(2)
        elif (r := re.match(r"^Condition_Start_(.+)$", m)):
            self.condition = r.group(1)
            if self.auto:
                self.start(f"{subject_tag(self.subject) if self.subject else 's__'}_{self.condition}")
        elif m.startswith("Condition_Complete_") or m in ("Returned_To_Main_Menu", "Application_Closing"):
            if self.auto:
                self.stop()

    def toggle_manual(self):
        if self.session is not None:
            self.stop()
        else:
            self.start(f"{subject_tag(self.subject) if self.subject else 's__'}_manual")

    def status_lines(self, camera_status, gui_linked, webcam=None):
        lines = [f"{self.preset['name_match']} {self.fps_now:4.1f} fps"
                 + (f" | webcam {webcam.fps_now:4.1f} fps" if webcam is not None else "")
                 + f" | rec {self.fps:g} fps | {'GUI linked' if gui_linked else 'GUI NOT FOUND'}"
                 + f" | {'auto' if self.auto else 'manual'}"]
        if self.session is not None:
            for writer in self.writers.values():
                text = writer.status()
                if text:
                    lines.append(text)
        else:
            lines.append("not recording   R = start" + (f"   (last: {self.last_file})" if self.last_file else ""))
        if camera_status:
            lines.append(camera_status)
        if webcam is not None and webcam.status:
            lines.append(webcam.status)
        return lines

    def close(self):
        self.stop()
        for writer in self.writers.values():
            writer.close()


def preview_image(ximea_frame, webcam_frame, lines, recording, width=1280):
    """Both cameras side by side (each scaled to the same height) with the status on top."""
    import cv2
    import numpy as np
    tiles = []
    for frame in (ximea_frame, webcam_frame):
        if frame is None:
            continue
        if frame.ndim == 2:
            frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        tiles.append(frame)
    h = 480
    tiles = [cv2.resize(f, (max(1, int(f.shape[1] * h / f.shape[0])), h)) for f in tiles] or \
            [np.zeros((h, 640, 3), np.uint8)]
    view = np.hstack(tiles)
    scale = width / view.shape[1]
    view = cv2.resize(view, (width, int(view.shape[0] * scale)))
    cv2.rectangle(view, (0, 0), (width, 14 + 26 * len(lines)), (0, 0, 0), -1)
    for i, line in enumerate(lines):
        color = (0, 0, 255) if line.startswith(("REC", "CAMERA", "WEBCAM")) else (0, 220, 0)
        cv2.putText(view, line, (12, 28 + 26 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)
    if recording:
        cv2.circle(view, (width - 24, 24), 11, (0, 0, 255), -1)
    return view


def parse_size(text):
    if not text:
        return None
    w, h = text.lower().split("x")
    return int(w), int(h)


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", default=DEFAULT_CAMERA, choices=sorted(CAMERA_PRESETS))
    ap.add_argument("--fps", type=float, default=FPS, help="frame rate of the cameras and the videos (default 30)")
    ap.add_argument("--webcam", type=int, default=WEBCAM_INDEX, metavar="N",
                    help="index of the face webcam (default %(default)s; try 1, 2... if the wrong camera opens)")
    ap.add_argument("--webcam-size", default=WEBCAM_SIZE, metavar="WxH",
                    help="webcam resolution (default %(default)s; the camera may pick the closest it supports)")
    ap.add_argument("--no-webcam", action="store_true", help="record only the XIMEA camera")
    ap.add_argument("--out", default=RECORDINGS_DIR, help="folder for the videos (default: recordings/)")
    ap.add_argument("--manual", action="store_true", help="do not follow the GUI; only R starts / stops")
    ap.add_argument("--no-window", action="store_true", help="no preview window (console only, Ctrl+C stops)")
    args = ap.parse_args()

    preset = CAMERA_PRESETS[args.camera]
    print(f"[INFO] {preset['name_match']}: exposure {preset['exposure']} us, gain {preset['gain']}, "
          f"gamma {preset['gammaY']}, wb {preset['wb_kr']}/{preset['wb_kb']}, "
          f"binning {preset['binning']}, {args.fps:g} fps -> {args.out}")
    sources = {preset["id"]: preset["id"]}
    if not args.no_webcam:
        sources["webcam"] = "webcam"
    recorder = Recorder(preset, args.out, sources, fps=args.fps, auto=not args.manual)
    camera = CameraSource(preset, args.fps, on_event=recorder.marker)
    camera.start()
    webcam = None
    if not args.no_webcam:
        webcam = WebcamSource(args.webcam, args.fps, parse_size(args.webcam_size),
                              on_frame=lambda f, t: recorder.on_frame("webcam", f, t), on_event=recorder.marker)
        webcam.start()
    gui_q = queue.Queue()
    listener = GuiMarkerListener(gui_q)
    if not args.manual:
        listener.start()
    recorder.marker("Recorder_Started")

    cv2 = None
    if not args.no_window:
        import cv2
        cv2.namedWindow("Recorder", cv2.WINDOW_NORMAL)
    last_print, last_view, preview = 0.0, 0.0, None
    try:
        while True:
            while True:
                try:
                    recorder.on_gui_marker(gui_q.get_nowait())
                except queue.Empty:
                    break
            try:
                frame, lsl_time, nframe, cam_ts = camera.frames.get(timeout=0.02)
                recorder.on_frame(preset["id"], frame, lsl_time)
                preview = frame
            except queue.Empty:
                pass
            lines = recorder.status_lines(camera.status, listener.connected, webcam)
            if cv2 is not None:
                now = time.monotonic()
                if now - last_view >= 1.0 / PREVIEW_FPS:         # the preview never slows the recording
                    last_view = now
                    cv2.imshow("Recorder", preview_image(preview, webcam.latest if webcam else None, lines,
                                                         recorder.session is not None))
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), ord("Q"), 27):
                    break
                if key in (ord("r"), ord("R")):
                    recorder.toggle_manual()
            elif time.monotonic() - last_print > 2.0:
                print("[STATUS] " + " | ".join(lines))
                last_print = time.monotonic()
    except KeyboardInterrupt:
        pass
    finally:
        recorder.close()                                  # finishes the video files properly
        recorder.marker("Recorder_Stopped")
        listener.running = False
        if webcam is not None:
            webcam.stop()
        camera.stop()
        if cv2 is not None:
            cv2.destroyAllWindows()
        print("[INFO] Recorder closed.")


if __name__ == "__main__":
    main()
