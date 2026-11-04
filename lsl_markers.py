"""LabStreamingLayer marker outlet (events sent to the recording system)."""

from pylsl import StreamInfo, StreamOutlet

from config import TRAINING_MARKER_PREFIX
from state import state


marker_outlet = None


def init_lsl():
    global marker_outlet
    info = StreamInfo('ParadigmMarkers', 'Markers', 1, 0, 'string', 'pyqt_paradigm_123')
    marker_outlet = StreamOutlet(info)
    print("LSL Marker Outlet initialized.")


def send_marker(marker_string):
    if state.training_active:
        marker_string = TRAINING_MARKER_PREFIX + marker_string
    if marker_outlet is not None:
        marker_outlet.push_sample([marker_string])
        print(f"Sent marker: {marker_string}")
