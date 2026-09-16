import sounddevice as sd
import numpy as np
import time

# set audio parameters for realtek compatibility
duration = 1.0 
sample_rate = 48000
frequency = 440.0 

# generate a mono sine wave for the beep
t = np.linspace(0, duration, int(sample_rate * duration), False)
beep_mono = np.sin(frequency * t * 2 * np.pi)

# convert mono to stereo by duplicating the channel
beep_stereo = np.column_stack((beep_mono, beep_mono))

# assign exact directsound device indices
headphone_id = 10
speaker_id = 11

# play beep on headphones
print("playing beep on headphones...")
try:
    sd.play(beep_stereo, samplerate=sample_rate, device=headphone_id)
    sd.wait()
except Exception as e:
    print(f"error on headphones: {e}")

# pause briefly between sounds
time.sleep(0.5)

# play beep on laptop speakers
print("playing beep on laptop speakers...")
try:
    sd.play(beep_stereo, samplerate=sample_rate, device=speaker_id)
    sd.wait()
except Exception as e:
    print(f"error on speakers: {e}")