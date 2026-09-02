import winsound
import os

# define the exact path to test
test_file = r"C:\Users\jose_trapero\python_local\motion_tracking_setup\correct_answer.wav"

# verify file existence before attempting playback
if os.path.exists(test_file):
    print("file found, attempting to play...")
    
    # play sound synchronously to ensure the script does not close before playback finishes
    winsound.PlaySound(test_file, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
    
    print("playback attempt finished.")
else:
    print("error: file not found at the specified path.")