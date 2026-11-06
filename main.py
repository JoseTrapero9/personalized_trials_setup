"""Entry point: python main.py"""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from audio import audio_sys
from controller import paradigmcontroller
from haptics import shutdown_haptics, start_haptic_thread
from lsl_markers import init_lsl, send_marker
from robot import stop_robot_process
from state import state


def cleanup_resources():
    send_marker("Application_Closing")

    if state.controller is not None:
        state.controller.dual_task_screen.flush_pending_log()
        state.controller.dual_task_screen.voice_listener.stop()
        state.controller.dual_task_screen.game_widget.shutdown()
        if state.controller.evaluator_link is not None:
            state.controller.evaluator_link.stop()

    stop_robot_process()
    shutdown_haptics()


def run_paradigm():
    init_lsl()
    start_haptic_thread()

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.aboutToQuit.connect(cleanup_resources)

    audio_sys.setup_devices(participant_keyword="Trekz", researcher_keyword="Realtek(R) Audio")

    state.controller = paradigmcontroller()
    window = state.controller

    screens = app.screens()
    if len(screens) > 1:
        second_screen = screens[1]
        window.move(second_screen.geometry().topLeft())
        window.show()
        if window.windowHandle():
            window.windowHandle().setScreen(second_screen)
        window.showFullScreen()
    else:
        window.showFullScreen()

    sys.exit(app.exec_())


if __name__ == "__main__":
    run_paradigm()
