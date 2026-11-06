import sys
import os
import time
import threading
import queue
import cv2
import torch
from ultralytics import YOLO

# Ensure XIMEA API is accessible
sys.path.append(r"C:\XIMEA\API\Python\v3")
from ximea import xiapi

# ================= CONFIGURATION =================
BASE_DIR = r"C:\Users\karla\Documents\FabThesisVLM"
MODEL_PATH = os.path.join(BASE_DIR, "runs", "detect", "train", "weights", "best.pt")

CONFIDENCE = 0.45
FPS_XIMEA = 30.0

MC050_PRESET = {
    "name_match": "MC050",
    "exposure": 32000,
    "gain": 10.0,
    "gammaY": 0.47,
    "wb_kr": 1.50,
    "wb_kb": 2.80,
    "binning": True
}

# Paradigm Battery Values
BATTERY_VALUES = {
    "Blue": 1,
    "Red": 2,
    "Yellow": 3,
    "Green": 4
}
SLOT_MULTIPLIERS = [1, 2, 3]  # Left (x1), Middle (x2), Right (x3)
# =================================================


class XimeaCaptureThread(threading.Thread):
    """Non-blocking camera acquisition thread to prevent USB Error 10 timeouts."""
    def __init__(self, preset, fps=30.0):
        super().__init__(daemon=True)
        self.preset = preset
        self.fps = fps
        self.frame_queue = queue.Queue(maxsize=2)
        self.running = True
        self.cam = None
        self.device_name = "Unknown"

    def init_camera(self):
        probe = xiapi.Camera()
        num_devices = probe.get_number_devices()

        for i in range(num_devices):
            cam = xiapi.Camera(dev_id=i)
            cam.open_device()

            raw_name = cam.get_param("device_name")
            model_name = raw_name.decode("utf-8") if isinstance(raw_name, bytes) else str(raw_name)

            if self.preset["name_match"] not in model_name:
                cam.close_device()
                continue

            cam.set_imgdataformat("XI_RGB24")

            try:
                cam.set_param("buffer_policy", "XI_BP_SAFE")
                cam.set_param("recent_frame", 1)
            except Exception:
                pass

            if self.preset.get("binning", False):
                try:
                    cam.set_param("downsampling_type", "XI_BINNING")
                    cam.set_param("downsampling", "XI_DWN_2x2")
                except Exception:
                    try:
                        cam.set_param("downsampling", "XI_DWN_2x2")
                    except Exception:
                        pass

            cam.set_exposure(self.preset["exposure"])
            cam.set_gain(self.preset["gain"])
            cam.set_gammaY(self.preset["gammaY"])
            cam.set_param("wb_kr", self.preset["wb_kr"])
            cam.set_param("wb_kb", self.preset["wb_kb"])

            try:
                cam.set_param("acq_timing_mode", "XI_ACQ_TIMING_MODE_FRAME_RATE")
                cam.set_param("framerate", float(self.fps))
            except Exception:
                pass

            cam.start_acquisition()
            self.cam = cam
            self.device_name = model_name
            print(f"[INFO] Initialized camera: {self.device_name}")
            return

        raise RuntimeError("Could not find XIMEA MC050 camera! Check the USB 3.0 connection.")

    def run(self):
        self.init_camera()
        img = xiapi.Image()

        while self.running:
            try:
                self.cam.get_image(img, timeout=5000)
                frame = img.get_image_data_numpy()

                if self.frame_queue.full():
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                self.frame_queue.put(frame)

            except xiapi.Xi_error as err:
                if err.status == 10:  # Timeout recovery
                    print("[WARN] XIMEA Timeout (Error 10) - resetting acquisition...")
                    self.cam.stop_acquisition()
                    time.sleep(0.05)
                    self.cam.start_acquisition()
                    continue
                else:
                    print(f"[ERROR] XIMEA Error: {err}")
                    break

    def stop(self):
        self.running = False
        if self.cam is not None:
            try:
                self.cam.stop_acquisition()
                self.cam.close_device()
            except Exception:
                pass


def evaluate_tray_slots(results, class_names):
    """
    Divides the detected tray into 3 horizontal zones (Left x1, Middle x2, Right x3)
    and calculates the total score if no hand is occluding the workspace.
    """
    tray_box = None
    hand_detected = False
    batteries = []

    for box in results.boxes:
        cls_id = int(box.cls[0].item())
        label = class_names[cls_id]
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        x_center = (x1 + x2) / 2.0
        y_center = (y1 + y2) / 2.0

        if label == "hand":
            hand_detected = True
        elif label == "tray":
            tray_box = (x1, y1, x2, y2)
        elif label in BATTERY_VALUES:
            batteries.append((label, x_center, y_center))

    if hand_detected:
        return "HAND DETECTED - Pausing Evaluation", [None, None, None], 0

    if tray_box is None:
        return "WAITING FOR TRAY...", [None, None, None], 0

    tx1, ty1, tx2, ty2 = tray_box
    tray_width = tx2 - tx1
    slot_width = tray_width / 3.0

    slots = [None, None, None]  # [Left, Middle, Right]

    for color, bx, by in batteries:
        # Check if the battery center is inside the tray bounding box
        if tx1 <= bx <= tx2 and ty1 <= by <= ty2:
            slot_idx = int((bx - tx1) // slot_width)
            slot_idx = max(0, min(2, slot_idx))
            slots[slot_idx] = color

    # Calculate paradigm math: Slot1*1 + Slot2*2 + Slot3*3
    total_score = 0
    for idx, color in enumerate(slots):
        if color in BATTERY_VALUES:
            total_score += BATTERY_VALUES[color] * SLOT_MULTIPLIERS[idx]

    status = f"Slots: [x1: {slots[0]} | x2: {slots[1]} | x3: {slots[2]}] -> Total: {total_score}"
    return status, slots, total_score


def main():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model not found at: {MODEL_PATH}")

    device = 0 if torch.cuda.is_available() else "cpu"
    print(f"[INFO] Loading YOLO model on device={device}: {MODEL_PATH}")
    model = YOLO(MODEL_PATH)
    print(f"[INFO] Classes loaded: {model.names}")

    cam_thread = XimeaCaptureThread(MC050_PRESET, fps=FPS_XIMEA)
    cam_thread.start()

    print("\n[LIVE] Starting real-time detection. Press 'Q' or 'ESC' to exit.")
    prev_time = time.time()

    try:
        while True:
            try:
                frame = cam_thread.frame_queue.get(timeout=2.0)
            except queue.Empty:
                continue

            # Run YOLO11 inference
            results = model.predict(source=frame, conf=CONFIDENCE, device=device, verbose=False)[0]

            # Evaluate slot positions and math
            status_text, _, _ = evaluate_tray_slots(results, model.names)

            # Render YOLO boxes
            annotated = results.plot()

            # Compute FPS
            now = time.time()
            fps = 1.0 / max(now - prev_time, 1e-6)
            prev_time = now

            # Resize for comfortable viewing on screen
            preview = cv2.resize(annotated, (1024, 576))

            # Draw HUD overlay banner
            cv2.rectangle(preview, (0, 0), (1024, 70), (20, 20, 20), -1)
            cv2.putText(
                preview,
                f"FPS: {fps:.1f} | {status_text}",
                (15, 45),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (0, 255, 180),
                2
            )

            cv2.imshow("XIMEA MC050 - YOLO11 Live Paradigm Test", preview)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                break

    finally:
        cam_thread.stop()
        cv2.destroyAllWindows()
        print("[INFO] Camera closed cleanly.")


if __name__ == "__main__":
    main()