import cv2
from ximea import xiapi
from pylsl import StreamInfo, StreamOutlet
from datetime import datetime

# setup lsl stream info and outlet for frame numbers
info = StreamInfo('ximeasync', 'Markers', 1, 0, 'int32', 'cam_sync_1')
outlet = StreamOutlet(info)

# instantiate and open the ximea camera
cam = xiapi.Camera()
cam.open_device()

# --- Hardware Image Quality Configuration ---
cam.set_imgdataformat('XI_RGB24')

# Values calibrated from your tuner
cam.set_exposure(31000)
cam.set_gain(8.0)
cam.set_gammaY(0.47)
cam.set_param('wb_kr', 1.00)
cam.set_param('wb_kb', 1.90)

# start data acquisition
cam.start_acquisition()

# create an image object to store the payload
img = xiapi.Image()

# capture an initial frame to determine video dimensions
cam.get_image(img)
initial_frame = img.get_image_data_numpy()
height, width, _ = initial_frame.shape

# generate a timestamped filename to prevent overwriting
current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"ximea_recording_{current_time}.mp4"

# configure the video writer
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
fps = 30.0
out = cv2.VideoWriter(filename, fourcc, fps, (width, height))

# setup display parameters
display_scale = 0.5
display_frame_skip = 2
loop_counter = 0

try:
    while True:
        # retrieve the latest image directly
        cam.get_image(img)
        frame = img.get_image_data_numpy()

        # extract and push hardware frame number
        current_frame = img.nframe
        outlet.push_sample([current_frame])

        # Write and display the frame directly (identical to calibration tool)
        out.write(frame)

        if loop_counter % display_frame_skip == 0:
            display_frame = cv2.resize(frame, (0, 0), fx=display_scale, fy=display_scale)
            cv2.imshow('ximea stream', display_frame)

        loop_counter += 1

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:
    cam.stop_acquisition()
    cam.close_device()
    out.release()
    cv2.destroyAllWindows()