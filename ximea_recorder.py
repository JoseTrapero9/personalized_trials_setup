"""Video recorder for the second XIMEA camera (MQ013) on a third PC, synchronised with LSL.

Only records video: no model, no detection. Settings come from old_code/3CAM_Stream (MQ013 preset).

    python ximea_recorder.py                 # records every condition / training block automatically
    python ximea_recorder.py --manual        # only R starts / stops a recording
    python ximea_recorder.py --out D:\\videos

Synchronisation (LSL)
  * Stream "ximeasync_mq013" (2 channels, int32): one sample per camera frame, stamped with the LSL clock
    at the moment the frame arrived from the camera:
        [video_frame, camera_nframe]
    video_frame = index of the frame inside the open video file (0, 1, 2 ...), -1 when not recording.
    LabRecorder records it together with the GUI markers; LSL corrects the clock offset between the PCs.
  * Stream "ximeasync_mq013_markers" (strings): Recording_Start_<file>, Recording_Stop_<file>_Frames_<n>,
    Camera_Lost / Camera_Restored.
  * Next to every video: <video>_frames.csv with video_frame, lsl_time, camera_nframe, camera_time_s
    (the same timestamps, so a video frame can be matched to the markers even without the XDF file).
  Every captured frame is written exactly once (no frames duplicated or dropped to fake a constant rate),
  so row N of the CSV is frame N of the video. Frames the PC could not save fast enough are counted.

Recording control
  * Automatic (default): follows the GUI over LSL ("ParadigmMarkers"). Starts at Condition_Start_<condition>
    (training: every block), stops at Condition_Complete / back to the menu / GUI closed.
    File: <out>/sXX_<condition>_mq013_<YYYYmmdd_HHMMSS>.mp4
  * R starts / stops a manual recording at any time. Q / Esc stops cleanly and quits.

Camera: runs in its own process; if no frame arrives for 3 s (XIMEA error 10, USB problem) that process is
restarted and the camera reopened. A recording keeps going in the same file; the gap is visible in the CSV
and as Camera_Lost / Camera_Restored markers.
"""

import argparse
import csv
import os
import queue
import re
import sys
import threading
import time
from datetime import datetime

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
FPS = 30.0                           # hardware frame rate (acq_timing_mode = FRAME_RATE)
XIMEA_API_PATH = r"C:\XIMEA\API\Python\v3"
RECORDINGS_DIR = os.path.join(BASE_DIR, "recordings")
VIDEO_FOURCC, VIDEO_EXT = "mp4v", ".mp4"
WRITE_QUEUE_FRAMES = 90              # frames waiting to be written (3 s); beyond that frames are counted as lost
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
# Video file + per-frame CSV
# ---------------------------------------------------------------------------
class Recording:
    """One video file. add() is called for every camera frame and returns the frame's index in the file
    (or -1 if it could not be queued); a writer thread encodes the video and writes the CSV."""

    def __init__(self, path, fps):
        self.path, self.fps = path, fps
        self.csv_path = os.path.splitext(path)[0] + "_frames.csv"
        self.q = queue.Queue(maxsize=WRITE_QUEUE_FRAMES)
        self.next_index = 0
        self.written = 0
        self.lost = 0
        self.error = ""
        self.started = time.time()
        self.thread = threading.Thread(target=self._writer, daemon=True)
        self.thread.start()

    def add(self, frame, lsl_time, nframe, cam_ts):
        try:
            self.q.put_nowait((frame, self.next_index, lsl_time, nframe, cam_ts))
        except queue.Full:
            self.lost += 1
            return -1
        self.next_index += 1
        return self.next_index - 1

    def _writer(self):
        import cv2
        out, f, w = None, None, None
        try:
            f = open(self.csv_path, "w", newline="", encoding="utf-8")
            w = csv.writer(f)
            w.writerow(["video_frame", "lsl_time", "camera_nframe", "camera_time_s"])
            while True:
                item = self.q.get()
                if item is None:
                    break
                frame, index, lsl_time, nframe, cam_ts = item
                if out is None:
                    h, wd = frame.shape[:2]
                    out = cv2.VideoWriter(self.path, cv2.VideoWriter_fourcc(*VIDEO_FOURCC), self.fps, (wd, h),
                                          frame.ndim == 3)
                    if not out.isOpened():
                        raise RuntimeError(f"cannot open the video file {self.path}")
                out.write(frame)
                w.writerow([index, f"{lsl_time:.6f}", nframe, f"{cam_ts:.6f}"])
                self.written += 1
                if self.written % 30 == 0:
                    f.flush()
        except Exception as e:
            self.error = str(e)
            print(f"[REC] ERROR while writing {self.path}: {e}")
        finally:
            if out is not None:
                out.release()
            if f is not None:
                f.close()

    def close(self):
        self.q.put(None)
        self.thread.join(30.0)


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
    """Ties camera, LSL outlets, recordings and the GUI markers together (used by main())."""

    def __init__(self, preset, out_dir, auto=True, clock=None):
        import pylsl
        self.preset, self.out_dir, self.auto = preset, out_dir, auto
        os.makedirs(out_dir, exist_ok=True)
        # irregular rate (0): XDF readers then keep the exact capture timestamps instead of smoothing them
        info = pylsl.StreamInfo(preset["lsl_stream_name"], "VideoFrames", 2, 0, "int32", preset["lsl_source_id"])
        chans = info.desc().append_child("channels")
        for label in ("video_frame", "camera_nframe"):
            chans.append_child("channel").append_child_value("label", label)
        info.desc().append_child_value("camera", preset["name_match"])
        self.frame_outlet = pylsl.StreamOutlet(info)
        minfo = pylsl.StreamInfo(preset["lsl_stream_name"] + "_markers", "Markers", 1, 0, "string",
                                 preset["lsl_source_id"] + "_markers")
        self.marker_outlet = pylsl.StreamOutlet(minfo)
        self.clock = clock or pylsl.local_clock
        self.rec = None
        self.subject, self.condition = None, None
        self.frames_seen = 0
        self.fps_now, self._fps_count, self._fps_t = 0.0, 0, time.monotonic()
        self.last_file = ""

    def marker(self, text):
        self.marker_outlet.push_sample([text])
        print(f"[MARK] {text}")

    # ---------------- recordings
    def start(self, label):
        self.stop()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{label}_{self.preset['id']}_{stamp}{VIDEO_EXT}"
        self.rec = Recording(os.path.join(self.out_dir, name), FPS)
        self.last_file = name
        self.marker(f"Recording_Start_{name}")

    def stop(self):
        rec, self.rec = self.rec, None
        if rec is None:
            return
        rec.close()
        name = os.path.basename(rec.path)
        self.marker(f"Recording_Stop_{name}_Frames_{rec.written}_Lost_{rec.lost}")
        if rec.lost:
            print(f"[REC] {rec.lost} frame(s) could not be saved fast enough (disk / CPU too slow?)")

    # ---------------- input
    def on_frame(self, frame, lsl_time, nframe, cam_ts):
        index = self.rec.add(frame, lsl_time, nframe, cam_ts) if self.rec is not None else -1
        self.frame_outlet.push_sample([index, nframe], lsl_time)       # stamped with the capture time
        self.frames_seen += 1
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
        if self.rec is not None:
            self.stop()
        else:
            self.start(f"{subject_tag(self.subject) if self.subject else 's__'}_manual")

    def status_lines(self, camera_status, gui_linked):
        rec = self.rec
        lines = [f"{self.preset['name_match']}  {self.fps_now:4.1f} fps   "
                 f"{'GUI linked' if gui_linked else 'GUI NOT FOUND'}   "
                 f"{'auto (follows the GUI)' if self.auto else 'manual'}"]
        if rec is not None:
            lines.append(f"REC  {os.path.basename(rec.path)}   {rec.written} frames   "
                         f"{time.time() - rec.started:5.0f} s" + (f"   LOST {rec.lost}" if rec.lost else "")
                         + (f"   ERROR {rec.error}" if rec.error else ""))
        else:
            lines.append("not recording" + (f"   (last: {self.last_file})" if self.last_file else ""))
        if camera_status:
            lines.append(camera_status)
        return lines


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", default=DEFAULT_CAMERA, choices=sorted(CAMERA_PRESETS))
    ap.add_argument("--out", default=RECORDINGS_DIR, help="folder for the videos (default: recordings/)")
    ap.add_argument("--manual", action="store_true", help="do not follow the GUI; only R starts / stops")
    ap.add_argument("--no-window", action="store_true", help="no preview window (console only, Ctrl+C stops)")
    args = ap.parse_args()

    preset = CAMERA_PRESETS[args.camera]
    print(f"[INFO] {preset['name_match']}: exposure {preset['exposure']} us, gain {preset['gain']}, "
          f"gamma {preset['gammaY']}, wb {preset['wb_kr']}/{preset['wb_kb']}, "
          f"binning {preset['binning']}, {FPS:g} fps -> {args.out}")
    recorder = Recorder(preset, args.out, auto=not args.manual)
    camera = CameraSource(preset, FPS, on_event=recorder.marker)
    camera.start()
    gui_q = queue.Queue()
    listener = GuiMarkerListener(gui_q)
    if not args.manual:
        listener.start()
    recorder.marker("Recorder_Started")

    cv2 = None
    if not args.no_window:
        import cv2
        cv2.namedWindow("XIMEA recorder", cv2.WINDOW_NORMAL)
    last_print, preview = 0.0, None
    try:
        while True:
            while True:
                try:
                    recorder.on_gui_marker(gui_q.get_nowait())
                except queue.Empty:
                    break
            try:
                frame, lsl_time, nframe, cam_ts = camera.frames.get(timeout=0.05)
                recorder.on_frame(frame, lsl_time, nframe, cam_ts)
                preview = frame
            except queue.Empty:
                pass
            lines = recorder.status_lines(camera.status, listener.connected)
            if cv2 is not None:
                import numpy as np
                view = np.zeros((540, 960, 3), np.uint8) if preview is None else cv2.resize(preview, (960, 540))
                if view.ndim == 2:
                    view = cv2.cvtColor(view, cv2.COLOR_GRAY2BGR)
                cv2.rectangle(view, (0, 0), (960, 34 + 30 * len(lines)), (0, 0, 0), -1)
                for i, line in enumerate(lines):
                    color = (0, 0, 255) if line.startswith(("REC", "CAMERA")) else (0, 220, 0)
                    cv2.putText(view, line, (12, 32 + 30 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
                if recorder.rec is not None:
                    cv2.circle(view, (930, 25), 11, (0, 0, 255), -1)
                cv2.imshow("XIMEA recorder", view)
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
        recorder.stop()                                   # closes the video file properly
        recorder.marker("Recorder_Stopped")
        listener.running = False
        camera.stop()
        if cv2 is not None:
            cv2.destroyAllWindows()
        print("[INFO] Recorder closed.")


if __name__ == "__main__":
    main()
