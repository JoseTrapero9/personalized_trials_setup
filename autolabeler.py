import os
import shutil
import cv2
from ultralytics import YOLO

# ================= PATH CONFIGURATION =================
BASE_DIR = r"C:\Users\karla\Documents\FabThesisVLM"

# Folder containing your raw images captured with the XIMEA MC050
RAW_DIR = os.path.join(BASE_DIR, "dataset_raw")

# Folder where the Roboflow ZIP was extracted
ROBOFLOW_DIR = os.path.join(BASE_DIR, "dataset")

# Path to your trained YOLO weights
MODEL_PATH = os.path.join(BASE_DIR, "runs", "detect", "train", "weights", "best.pt")

# Output directories
OUT_READY_DIR = os.path.join(BASE_DIR, "auto_labeled", "ready_to_upload")
OUT_PREVIEW_DIR = os.path.join(BASE_DIR, "auto_labeled", "preview")

CONFIDENCE = 0.45
# Set to False to force auto-labeling on ALL images in RAW_DIR
SKIP_ALREADY_LABELED = True  
VALID_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")
# ======================================================


def get_already_labeled_images(roboflow_dir):
    """Reads base image filenames from the Roboflow dataset folder to avoid duplicates."""
    labeled_set = set()
    if not os.path.exists(roboflow_dir):
        return labeled_set

    for root, _, files in os.walk(roboflow_dir):
        for file in files:
            if file.lower().endswith(VALID_EXTENSIONS):
                # Roboflow renames 'frame_0001.jpg' to 'frame_0001_jpg.rf.xxxx.jpg'
                base_name = file.split(".rf.")[0]
                for ext in ("_jpg", "_jpeg", "_png", "_bmp"):
                    if base_name.lower().endswith(ext):
                        base_name = base_name[:-len(ext)]
                        break
                labeled_set.add(base_name)
    return labeled_set


def collect_raw_images(raw_dir):
    """Finds all valid image files inside raw_dir (including subfolders)."""
    image_paths = []
    if not os.path.exists(raw_dir):
        raise FileNotFoundError(
            f"RAW_DIR does not exist: {raw_dir}\n"
            "Check the folder name where your raw XIMEA photos are stored."
        )

    for root, _, files in os.walk(raw_dir):
        for file in sorted(files):
            if file.lower().endswith(VALID_EXTENSIONS):
                image_paths.append(os.path.join(root, file))
    return image_paths


def main():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Trained model not found at: {MODEL_PATH}")

    os.makedirs(OUT_READY_DIR, exist_ok=True)
    os.makedirs(OUT_PREVIEW_DIR, exist_ok=True)

    print(f"[INFO] Loading trained model: {MODEL_PATH}")
    model = YOLO(MODEL_PATH)

    # 1. Save classes.txt and copy data.yaml
    classes_path = os.path.join(OUT_READY_DIR, "classes.txt")
    with open(classes_path, "w", encoding="utf-8") as f:
        for idx in range(len(model.names)):
            f.write(f"{model.names[idx]}\n")

    yaml_src = os.path.join(ROBOFLOW_DIR, "data.yaml")
    if os.path.exists(yaml_src):
        shutil.copy(yaml_src, os.path.join(OUT_READY_DIR, "data.yaml"))

    # 2. Collect raw images and filter already-labeled ones
    all_raw_paths = collect_raw_images(RAW_DIR)
    already_labeled = get_already_labeled_images(ROBOFLOW_DIR) if SKIP_ALREADY_LABELED else set()

    remaining_paths = [
        p for p in all_raw_paths
        if os.path.splitext(os.path.basename(p))[0] not in already_labeled
    ]

    # Fallback: if everything was filtered out, auto-label all raw images anyway
    if len(all_raw_paths) > 0 and len(remaining_paths) == 0:
        print("[WARN] All images in RAW_DIR matched ROBOFLOW_DIR names. Auto-labeling all images in RAW_DIR instead...")
        remaining_paths = all_raw_paths

    print(f"\n[SUMMARY] Total images found in RAW_DIR : {len(all_raw_paths)}")
    print(f"[SUMMARY] Already labeled in Roboflow   : {len(already_labeled)}")
    print(f"[SUMMARY] Images to auto-label now      : {len(remaining_paths)}\n")

    if len(remaining_paths) == 0:
        print(f"[ERROR] No images found inside: {RAW_DIR}")
        print("Please verify the folder path in RAW_DIR.")
        return

    # 3. Run inference and save previews + labels
    for i, img_path in enumerate(remaining_paths, 1):
        filename = os.path.basename(img_path)
        base_name = os.path.splitext(filename)[0]

        results = model.predict(source=img_path, conf=CONFIDENCE, device=0, verbose=False)[0]

        # Copy original image
        shutil.copy(img_path, os.path.join(OUT_READY_DIR, filename))

        # Write YOLO .txt annotation
        txt_path = os.path.join(OUT_READY_DIR, f"{base_name}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            for box in results.boxes:
                cls_id = int(box.cls[0].item())
                x_c, y_c, w, h = box.xywhn[0].tolist()
                f.write(f"{cls_id} {x_c:.6f} {y_c:.6f} {w:.6f} {h:.6f}\n")

        # Save visual preview image with bounding boxes
        annotated_frame = results.plot()
        cv2.imwrite(os.path.join(OUT_PREVIEW_DIR, filename), annotated_frame)

        print(f"[{i}/{len(remaining_paths)}] Auto-labeled: {filename} ({len(results.boxes)} objects)")

    print("\n==================================================")
    print("[DONE] Auto-labeling complete!")
    print(f"1. Visual previews saved to:\n   {OUT_PREVIEW_DIR}")
    print(f"2. Images + YOLO .txt labels saved to:\n   {OUT_READY_DIR}")
    print("==================================================")


if __name__ == "__main__":
    main()