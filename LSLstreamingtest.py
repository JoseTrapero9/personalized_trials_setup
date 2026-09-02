import pyzed.sl as sl
import threading
import cv2
import numpy as np
import time
from pylsl import StreamInfo, StreamOutlet, StreamInlet, resolve_streams
import os

# Global variables for cross-thread communication
shared_data = {
    "image": None,
    "bodies": [],
    "capture_fps": 0.0,
    "is_recording": False,     
    "toggle_recording": False  
}
data_lock = threading.Lock()
is_running = True

# Configuration
MAX_PERSONS = 1
RECORDING_FILENAME = "c:/Users/fabia/PROJECTWORK/measurement_session.svo"
MARKER_LOG_FILENAME = "c:/Users/fabia/PROJECTWORK/measurement_session_markers.csv"

def gui_marker_listener_thread():
    """
    Background thread that listens for markers sent by the PyQt GUI over the network.
    It logs them to a CSV file ONLY when the ZED camera is also recording.
    """
    global is_running, shared_data
    
    print("\n[LSL INLET] Looking for 'ParadigmMarkers' stream from the GUI over the network...")
    # This will block until the GUI application is started and broadcasting LSL
    # Note: Corrected 'resolve_stream' to 'resolve_streams' based on pylsl import
    streams = resolve_streams('name', 'ParadigmMarkers')
    
    if not streams:
        print("[LSL INLET] Stream not found. Exiting listener.")
        return
        
    inlet = StreamInlet(streams[0])
    print("[LSL INLET] Successfully connected to GUI markers!\n")
    
    # Write CSV header if file doesn't exist or we want a fresh start
    with open(MARKER_LOG_FILENAME, "w") as f:
        f.write("local_system_time,lsl_timestamp,marker\n")
    
    while is_running:
        # Pull sample with a short timeout so the thread can gracefully exit when is_running becomes False
        sample, timestamp = inlet.pull_sample(timeout=0.5)
        
        if sample:
            marker_str = sample[0]
            print(f"[GUI MARKER] {marker_str}")
            
            # Check if we are currently recording
            recording_active = False
            with data_lock:
                recording_active = shared_data["is_recording"]
                
            # If SVO recording is active, save the marker to the CSV
            if recording_active:
                with open(MARKER_LOG_FILENAME, "a") as f:
                    f.write(f"{time.time()},{timestamp},{marker_str}\n")


def zed_capture_thread():
    global shared_data, is_running
    
    zed = sl.Camera()
    init_params = sl.InitParameters()
    init_params.camera_resolution = sl.RESOLUTION.HD1080
    init_params.camera_fps = 30
    init_params.depth_mode = sl.DEPTH_MODE.NEURAL 
    init_params.coordinate_units = sl.UNIT.METER
    
    if zed.open(init_params) != sl.ERROR_CODE.SUCCESS:
        print("Failed to open ZED Camera")
        is_running = False
        return
        
    #LSL SETUP 
    # 1 Frame Counter + (1 Person * 38 Points * 3 Coordinates) = 115 Channels
    channel_count = 1 + (MAX_PERSONS * 38 * 3)
    lsl_info = StreamInfo(name='ZED_Kinematics', 
                          type='MoCap', 
                          channel_count=channel_count, 
                          nominal_srate=60, 
                          channel_format='float32', 
                          source_id='zed_4050_tracker')
    lsl_outlet = StreamOutlet(lsl_info)
    
    body_params = sl.BodyTrackingParameters()
    body_params.enable_tracking = True
    body_params.enable_body_fitting = False 
    body_params.body_format = sl.BODY_FORMAT.BODY_38
    body_params.detection_model = sl.BODY_TRACKING_MODEL.HUMAN_BODY_FAST
    
    if zed.enable_body_tracking(body_params) != sl.ERROR_CODE.SUCCESS:
        print("Failed to enable Body Tracking")
        zed.close()
        is_running = False
        return
        
    runtime_params = sl.BodyTrackingRuntimeParameters()
    bodies = sl.Bodies()
    image_mat = sl.Mat()
    
    frames_captured = 0
    start_time = time.time()
    current_fps = 0.0
    
    recording_active = False
    svo_frame_index = -1 # Stays at -1 when not recording
    
    while is_running:
        # Check for manual recording triggers
        do_toggle = False
        with data_lock:
            do_toggle = shared_data["toggle_recording"]
            shared_data["toggle_recording"] = False 
            
        if do_toggle:
            if not recording_active:
                recording_param = sl.RecordingParameters(RECORDING_FILENAME, sl.SVO_COMPRESSION_MODE.H265)
                err = zed.enable_recording(recording_param)
                if err == sl.ERROR_CODE.SUCCESS:
                    recording_active = True
                    svo_frame_index = 0 # Reset frame counter exactly as SVO starts
                    print("\n[ZED] Recording STARTED.")
                else:
                    print(f"\n[ZED] Failed to start recording: {err}")
            else:
                zed.disable_recording()
                recording_active = False
                svo_frame_index = -1 # Reset to -1 when stopped
                print("\n[ZED] Recording STOPPED and file saved.")
        
        # Grab frame
        if zed.grab() == sl.ERROR_CODE.SUCCESS:
            
            # Increment frame counter ONLY if actively writing to SVO
            if recording_active:
                svo_frame_index += 1
                
            zed.retrieve_bodies(bodies, runtime_params)
            zed.retrieve_image(image_mat, sl.VIEW.LEFT)
            
            frames_captured += 1
            elapsed_time = time.time() - start_time
            if elapsed_time >= 1.0:
                current_fps = frames_captured / elapsed_time
                frames_captured = 0
                start_time = time.time()
            
            image_cv = image_mat.get_data()
            extracted_bodies = []
            
            # Initialize array with zeros
            lsl_sample = np.zeros(channel_count, dtype=np.float32)
            
            # Set Channel 0 to the current SVO frame number
            lsl_sample[0] = svo_frame_index
            
            for i, body in enumerate(bodies.body_list[:MAX_PERSONS]):
                if body.tracking_state == sl.OBJECT_TRACKING_STATE.OK:
                    keypoints_2d = body.keypoint_2d.copy()
                    keypoints_3d = body.keypoint.copy()
                    
                    flat_kp = keypoints_3d.flatten()
                    
                    # FIX: Changed from 102 to 114 to support 38 keypoints (38 * 3)
                    start_idx = 1 + (i * 114)
                    end_idx = start_idx + 114
                    lsl_sample[start_idx:end_idx] = flat_kp
                    
                    extracted_bodies.append({
                        'id': body.id,
                        'keypoints_2d': keypoints_2d,
                        'keypoints_3d': keypoints_3d
                    })
            
            # Push payload to LSL
            lsl_outlet.push_sample(lsl_sample.tolist())
            
            with data_lock:
                shared_data["image"] = image_cv.copy()
                shared_data["bodies"] = extracted_bodies
                shared_data["capture_fps"] = current_fps
                shared_data["is_recording"] = recording_active

    if recording_active:
        zed.disable_recording()
    zed.disable_body_tracking()
    zed.close()

if __name__ == "__main__":
    # Start ZED Camera thread
    capture_thread = threading.Thread(target=zed_capture_thread)
    capture_thread.start()
    
    # Start GUI Marker Listener thread
    listener_thread = threading.Thread(target=gui_marker_listener_thread)
    listener_thread.start()
    
    total_channels = 1 + (MAX_PERSONS * 38 * 3)
    
    print(f"Starting tracking... (Max {MAX_PERSONS} persons)")
    print(f"Broadcasting LSL Stream: 'ZED_Kinematics' ({total_channels} Channels)")
    print("Listening for LSL Stream: 'ParadigmMarkers' (GUI)")
    print("--------------------------------------------------")
    print("CONTROLS:")
    print("Press 'R' in the video window to START/STOP recording.")
    print("Press 'ESC' in the video window to EXIT.")
    print("--------------------------------------------------")
    
    display_frames = 0
    display_fps_calc_start = time.time()
    display_fps = 0.0
    
    TARGET_DISPLAY_FPS = 60
    target_frame_time = 1.0 / TARGET_DISPLAY_FPS 
    
    try:
        while is_running:
            loop_start_time = time.time() 
            
            local_image = None
            local_bodies = []
            capture_fps = 0.0
            is_recording_active = False
            
            with data_lock:
                if shared_data["image"] is not None:
                    local_image = shared_data["image"]
                    local_bodies = shared_data["bodies"]
                    capture_fps = shared_data["capture_fps"]
                    is_recording_active = shared_data["is_recording"]
            
            if local_image is not None:
                display_frames += 1
                elapsed_disp = time.time() - display_fps_calc_start
                if elapsed_disp >= 1.0:
                    display_fps = display_frames / elapsed_disp
                    display_frames = 0
                    display_fps_calc_start = time.time()
                
                fps_text = f"Capture: {capture_fps:.1f} FPS | Display: {display_fps:.1f} FPS"
                cv2.rectangle(local_image, (10, 10), (450, 50), (0, 0, 0), -1)
                cv2.putText(local_image, fps_text, (20, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                
                if is_recording_active:
                    h, w = local_image.shape[:2]
                    cv2.circle(local_image, (w - 100, 30), 10, (0, 0, 255), -1)
                    cv2.putText(local_image, "REC", (w - 80, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                
                for person in local_bodies:
                    valid_x = []
                    valid_y = []
                    
                    for kp in person['keypoints_2d']:
                        if not np.isnan(kp[0]) and not np.isnan(kp[1]):
                            x, y = int(kp[0]), int(kp[1])
                            valid_x.append(x)
                            valid_y.append(y)
                            cv2.circle(local_image, (x, y), radius=4, color=(0, 255, 0), thickness=-1)
                    
                    if valid_x and valid_y:
                        min_y = min(valid_y) 
                        avg_x = int(sum(valid_x) / len(valid_x)) 
                        label_text = f"Person {person['id']}"
                        text_pos = (avg_x - 40, max(30, min_y - 20))
                        
                        (w, h_text), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                        cv2.rectangle(local_image, (text_pos[0]-5, text_pos[1]-h_text-5), (text_pos[0]+w+5, text_pos[1]+5), (0, 0, 0), -1)
                        cv2.putText(local_image, label_text, text_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                
                # FIX: Updated Window Title
                cv2.imshow("ZED - 38 Point Tracking", local_image)
            
            processing_time = time.time() - loop_start_time
            remaining_time = target_frame_time - processing_time
            wait_ms = max(1, int(remaining_time * 1000))
            
            key = cv2.waitKey(wait_ms) & 0xFF
            
            if key == 27: 
                is_running = False
                break
            elif key == ord('r'): 
                with data_lock:
                    shared_data["toggle_recording"] = True
                    
    except KeyboardInterrupt:
        is_running = False
        
    print("\nShutting down...")
    cv2.destroyAllWindows()
    capture_thread.join()
    listener_thread.join()