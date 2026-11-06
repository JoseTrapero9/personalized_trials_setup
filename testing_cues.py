import sys
import os
import json
import time
import random
import threading
import websocket
from PyQt5.QtCore import QPointF, QRectF, QTimer, Qt, QUrl
from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QDialog, QFormLayout, QHBoxLayout,
    QLabel, QPushButton, QVBoxLayout, QWidget
)
from PyQt5.QtMultimedia import QSoundEffect

COLOR_HEX = {
    "red": "#E53935",
    "blue": "#1E5BD8",
    "green": "#1E9E4A",
    "yellow": "#F5C518",
    "purple": "#8E44C9"
}
LABELS = {
    "red": "RED",
    "blue": "BLUE",
    "green": "GREEN",
    "yellow": "YELLOW",
    "purple": "PURPLE"
}
KEY_GLYPHS = ["←", "↑", "→"]

# game parameters
SHUFFLE_SECONDS = 2.5
LATE_PRESS_SECONDS = 0.25
IDLE_HIT_POINTS = 10
IDLE_WRONG_PENALTY = 5

# x16 motor group definitions (mapped across the 0-19 coordinate grid)
BACK_ALL = list(range(20))
BACK_LOWER = [4, 5, 6, 7, 12, 13, 14, 15, 16, 17, 18, 19]
BACK_UPPER = [0, 1, 2, 3, 8, 9, 10, 11]
BACK_CENTER = [1, 2, 5, 6, 9, 10, 13, 14, 17, 18]
BACK_OUTER = [0, 3, 4, 7, 8, 11, 12, 15, 16, 19]

FRONT_ALL = list(range(20))
FRONT_LEFT = [0, 1, 4, 5, 8, 9, 12, 13, 16, 17]
FRONT_RIGHT = [2, 3, 6, 7, 10, 11, 14, 15, 18, 19]


class FeedbackController:
    """manages persistent bhaptics player websocket connection, stimulus variants, and wav playback."""

    def __init__(self, base_dir=".", pos_mode="positive_1", neg_mode="negative_1"):
        self.pos_mode = pos_mode
        self.neg_mode = neg_mode
        self.ws_app = None
        self.connected = False
        self._start_bhaptics_client()

        # initialize low-latency wav players
        self.snd_correct = QSoundEffect()
        self.snd_incorrect = QSoundEffect()

        correct_path = os.path.join(base_dir, "audios/correct_answer.wav")
        incorrect_path = os.path.join(base_dir, "audios/incorrect_answer.wav")

        if os.path.exists(correct_path):
            self.snd_correct.setSource(QUrl.fromLocalFile(os.path.abspath(correct_path)))
            self.snd_correct.setVolume(0.9)
        else:
            print(f"warning: audio file not found at {correct_path}")

        if os.path.exists(incorrect_path):
            self.snd_incorrect.setSource(QUrl.fromLocalFile(os.path.abspath(incorrect_path)))
            self.snd_incorrect.setVolume(0.9)
        else:
            print(f"warning: audio file not found at {incorrect_path}")

    def set_modes(self, pos_mode, neg_mode):
        self.pos_mode = pos_mode
        self.neg_mode = neg_mode

    def _start_bhaptics_client(self):
        url = "ws://127.0.0.1:15881/v2/feedbacks?app_id=stroop_x16&app_name=Stroop_Haptic_Game"

        def on_open(ws):
            self.connected = True
            print("connected to bhaptics player.")

        def on_close(ws, close_status_code, close_msg):
            self.connected = False

        def on_error(ws, error):
            self.connected = False

        def on_message(ws, message):
            pass

        self.ws_app = websocket.WebSocketApp(
            url,
            on_open=on_open,
            on_close=on_close,
            on_error=on_error,
            on_message=on_message
        )

        def run_loop():
            while True:
                try:
                    self.ws_app.run_forever(ping_interval=5, ping_timeout=2)
                except Exception:
                    pass
                time.sleep(2.0)

        threading.Thread(target=run_loop, daemon=True).start()

    def _send_dot_frame(self, key, position, motor_tuples, duration_ms):
        if not self.connected or self.ws_app is None:
            return
        dots = [{"index": int(idx), "intensity": int(val)} for idx, val in motor_tuples]
        payload = {
            "Submit": [
                {
                    "Type": "frame",
                    "Key": key,
                    "Frame": {
                        "position": position,
                        "dotPoints": dots,
                        "durationMillis": int(duration_ms),
                        "pathPoints": []
                    }
                }
            ]
        }
        try:
            self.ws_app.send(json.dumps(payload))
        except Exception as e:
            print(f"bhaptics send error: {e}")

    def trigger_correct(self, mode_override=None):
        if self.snd_correct.isLoaded():
            self.snd_correct.play()
        mode = mode_override or self.pos_mode
        target_map = {
            "positive_1": self._pos_1_1p4hz,
            "positive_2": self._pos_2_upward_wave,
            "positive_3": self._pos_3_warm_swell
        }
        fn = target_map.get(mode, self._pos_1_1p4hz)
        threading.Thread(target=fn, daemon=True).start()

    def trigger_incorrect(self, mode_override=None):
        if self.snd_incorrect.isLoaded():
            self.snd_incorrect.play()
        mode = mode_override or self.neg_mode
        target_map = {
            "negative_1": self._neg_1_0p5hz,
            "negative_2": self._neg_2_sharp_staccato,
            "negative_3": self._neg_3_chest_jitter
        }
        fn = target_map.get(mode, self._neg_1_0p5hz)
        threading.Thread(target=fn, daemon=True).start()

    # ------------------------------------------------------------------ positive patterns (back, < 1s)
    def _pos_1_1p4hz(self):
        # 1.4 hz modulation -> period is ~714 ms between pulse onsets
        # pulse 1 at t = 0 ms (soft ramp up and down over 200 ms)
        self._send_dot_frame("p1_a", "VestBack", [(i, 35) for i in BACK_ALL], 80)
        time.sleep(0.07)
        self._send_dot_frame("p1_b", "VestBack", [(i, 60) for i in BACK_ALL], 130)
        # wait until t = 714 ms for the second 1.4 hz cycle
        time.sleep(0.644)
        # pulse 2 at t = 714 ms (200 ms duration -> total 914 ms)
        self._send_dot_frame("p1_c", "VestBack", [(i, 35) for i in BACK_ALL], 80)
        time.sleep(0.07)
        self._send_dot_frame("p1_d", "VestBack", [(i, 60) for i in BACK_ALL], 130)

    def _pos_2_upward_wave(self):
        # smooth upward spatial wave from lower back to upper back (total ~600 ms)
        self._send_dot_frame("p2_low", "VestBack", [(i, 35) for i in BACK_LOWER], 220)
        time.sleep(0.18)
        self._send_dot_frame("p2_mid", "VestBack", [(i, 50) for i in BACK_ALL], 200)
        time.sleep(0.18)
        self._send_dot_frame("p2_high", "VestBack", [(i, 65) for i in BACK_UPPER], 240)

    def _pos_3_warm_swell(self):
        # gentle gaussian-like envelope expanding from spine outward (total ~800 ms)
        self._send_dot_frame("p3_1", "VestBack", [(i, 25) for i in BACK_CENTER], 200)
        time.sleep(0.18)
        self._send_dot_frame("p3_2", "VestBack", [(i, 55) for i in BACK_ALL], 350)
        time.sleep(0.32)
        self._send_dot_frame("p3_3", "VestBack", [(i, 25) for i in BACK_OUTER], 300)

    # ------------------------------------------------------------------ negative patterns (front, < 1s)
    def _neg_1_0p5hz(self):
        # 0.5 hz modulation -> 2.0 s full period (active half-cycle = 950 ms heavy thud within 1s cap)
        # heavy sustained chest compression that builds and cuts off abruptly
        self._send_dot_frame("n1_a", "VestFront", [(i, 95) for i in FRONT_ALL], 450)
        time.sleep(0.43)
        self._send_dot_frame("n1_b", "VestFront", [(i, 100) for i in FRONT_ALL], 500)

    def _neg_2_sharp_staccato(self):
        # 3 rapid 100% intensity rectangular alarm bursts (~4 hz burst rate, total 620 ms)
        front_max = [(i, 100) for i in FRONT_ALL]
        for step in range(3):
            self._send_dot_frame(f"n2_{step}", "VestFront", front_max, 120)
            if step < 2:
                time.sleep(0.25)

    def _neg_3_chest_jitter(self):
        # jarring left-right alternating high-intensity buzz across the front (total 700 ms)
        left_max = [(i, 100) for i in FRONT_LEFT]
        right_max = [(i, 100) for i in FRONT_RIGHT]
        for step in range(5):
            pattern = left_max if step % 2 == 0 else right_max
            self._send_dot_frame(f"n3_{step}", "VestFront", pattern, 130)
            if step < 4:
                time.sleep(0.14)

    def close(self):
        if self.ws_app is not None:
            try:
                self.ws_app.close()
            except Exception:
                pass


class StimulusConfigDialog(QDialog):
    """startup selector allowing the experimenter to preview and pick haptic conditions."""

    def __init__(self, feedback_ctrl):
        super().__init__()
        self.feedback = feedback_ctrl
        self.setWindowTitle("Select Haptic Stimulus Conditions")
        self.setMinimumWidth(440)
        self.setStyleSheet("""
            QDialog { background-color: #0F172A; color: #F8FAFC; }
            QLabel { color: #E2E8F0; font-size: 14px; font-weight: bold; }
            QComboBox {
                background-color: #1E293B; color: #F8FAFC; border: 1px solid #475569;
                border-radius: 6px; padding: 6px; font-size: 13px;
            }
            QPushButton {
                background-color: #334155; color: #F8FAFC; border: 1px solid #64748B;
                border-radius: 6px; padding: 7px 14px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #475569; }
            QPushButton#startBtn {
                background-color: #16A34A; border-color: #22C55E; font-size: 15px; padding: 10px;
            }
            QPushButton#startBtn:hover { background-color: #15803D; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        form = QFormLayout()
        form.setSpacing(14)

        # positive selector + preview button
        pos_row = QHBoxLayout()
        self.pos_combo = QComboBox()
        self.pos_combo.addItem("positive_1  (1.4 Hz Rhythmic Pulse - Back)", "positive_1")
        self.pos_combo.addItem("positive_2  (Upward Spatial Wave - Back)", "positive_2")
        self.pos_combo.addItem("positive_3  (Warm Gaussian Swell - Back)", "positive_3")
        btn_test_pos = QPushButton("Test")
        btn_test_pos.clicked.connect(lambda: self.feedback.trigger_correct(self.pos_combo.currentData()))
        pos_row.addWidget(self.pos_combo, stretch=1)
        pos_row.addWidget(btn_test_pos)
        form.addRow(QLabel("Correct (Back):"), pos_row)

        # negative selector + preview button
        neg_row = QHBoxLayout()
        self.neg_combo = QComboBox()
        self.neg_combo.addItem("negative_1  (0.5 Hz Heavy Thud - Front)", "negative_1")
        self.neg_combo.addItem("negative_2  (4 Hz Sharp Staccato - Front)", "negative_2")
        self.neg_combo.addItem("negative_3  (5 Hz Left/Right Jitter - Front)", "negative_3")
        btn_test_neg = QPushButton("Test")
        btn_test_neg.clicked.connect(lambda: self.feedback.trigger_incorrect(self.neg_combo.currentData()))
        neg_row.addWidget(self.neg_combo, stretch=1)
        neg_row.addWidget(btn_test_neg)
        form.addRow(QLabel("Incorrect (Front):"), neg_row)

        layout.addLayout(form)

        # start button
        btn_start = QPushButton("Start Stroop Game")
        btn_start.setObjectName("startBtn")
        btn_start.clicked.connect(self.accept)
        layout.addWidget(btn_start)

    def get_selections(self):
        return self.pos_combo.currentData(), self.neg_combo.currentData()


def generate_stroop_round(rng):
    """returns a 3-button layout where exactly one button has matching fill and label."""
    colors = list(COLOR_HEX.keys())
    target_pos = rng.randrange(3)
    layout = []

    for pos in range(3):
        if pos == target_pos:
            c = rng.choice(colors)
            layout.append((c, c))
        else:
            fill = rng.choice(colors)
            label = rng.choice([c for c in colors if c != fill])
            layout.append((fill, label))

    return layout, target_pos


class StroopHapticGame(QWidget):
    def __init__(self, feedback_ctrl):
        super().__init__()
        self.feedback = feedback_ctrl
        self.setWindowTitle(
            f"Stroop Task - bHaptics X16 [{self.feedback.pos_mode} | {self.feedback.neg_mode}]"
        )
        self.setMinimumSize(640, 480)
        self.setFocusPolicy(Qt.StrongFocus)

        self.rng = random.Random()
        self.score = 0
        self.round_n = 0
        self.current_round = None
        self.prev_round = None
        self.layout = [("red", "blue"), ("green", "yellow"), ("purple", "red")]

        self.flash = None
        self.key_flash = [0.0, 0.0, 0.0]
        self.popups = []
        self.next_shuffle_at = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.start()

    def start(self):
        now = time.perf_counter()
        self.score = 0
        self.round_n = 0
        self._new_round(now)
        self.timer.start(30)

    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return
        if event.key() == Qt.Key_Left:
            self.press(0)
        elif event.key() == Qt.Key_Up:
            self.press(1)
        elif event.key() == Qt.Key_Right:
            self.press(2)
        elif event.key() == Qt.Key_Escape:
            self.close()

    def press(self, pos):
        now = time.perf_counter()
        self.key_flash[pos] = now

        if not self._check_late_press(pos, now):
            if self.current_round is not None:
                self._evaluate_answer(self.current_round, pos, now)

        self.update()

    def _new_round(self, now):
        if self.current_round is not None:
            self.current_round["closed_at"] = now
            self.prev_round = self.current_round

        self.layout, target = generate_stroop_round(self.rng)
        self.round_n += 1
        self.current_round = {
            "n": self.round_n,
            "layout": self.layout,
            "target": target,
            "shown_at": now,
            "answered": False
        }
        self.next_shuffle_at = now + SHUFFLE_SECONDS

    def _check_late_press(self, pos, now):
        pr = self.prev_round
        if pr is not None and not pr["answered"] and (now - pr["closed_at"]) <= LATE_PRESS_SECONDS:
            self._evaluate_answer(pr, pos, now)
            return True
        return False

    def _evaluate_answer(self, rnd, pos, now):
        if rnd["answered"]:
            return
        rnd["answered"] = True

        if pos == rnd["target"]:
            self.score += IDLE_HIT_POINTS
            self.flash = ("correct", now)
            self.popups.append((pos, f"+{IDLE_HIT_POINTS}", "#4ADE80", now))
            self.feedback.trigger_correct()
        else:
            self.score = max(0, self.score - IDLE_WRONG_PENALTY)
            self.flash = ("wrong", now)
            self.popups.append((pos, f"-{IDLE_WRONG_PENALTY}", "#F87171", now))
            self.feedback.trigger_incorrect()

    def _tick(self):
        now = time.perf_counter()
        if now >= self.next_shuffle_at:
            self._new_round(now)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        now = time.perf_counter()

        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0, QColor("#0B1220"))
        bg.setColorAt(1, QColor("#111A2E"))
        painter.fillRect(0, 0, w, h, QBrush(bg))

        if self.flash is not None and now - self.flash[1] < 0.5:
            col = QColor("#22C55E") if self.flash[0] == "correct" else QColor("#EF4444")
            painter.setPen(QPen(col, 8))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(4, 4, w - 8, h - 8), 14, 14)

        # top hud with live vest status and selected modes
        hud = QRectF(16, 16, w - 32, 56)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(15, 23, 42, 220))
        painter.drawRoundedRect(hud, 10, 10)
        painter.setFont(QFont("Helvetica", 18, QFont.Bold))
        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(hud.adjusted(16, 0, -16, 0), Qt.AlignLeft | Qt.AlignVCenter, f"SCORE: {self.score:04d}")

        vest_status = "VEST: OK" if self.feedback.connected else "VEST: DISCONNECTED"
        mode_label = f"{vest_status}  ({self.feedback.pos_mode} | {self.feedback.neg_mode})"
        painter.setFont(QFont("Helvetica", 11, QFont.Bold))
        painter.setPen(QColor("#4ADE80") if self.feedback.connected else QColor("#F87171"))
        painter.drawText(hud, Qt.AlignCenter, mode_label)

        painter.setFont(QFont("Helvetica", 18, QFont.Bold))
        painter.setPen(QColor("#38BDF8"))
        painter.drawText(hud.adjusted(16, 0, -16, 0), Qt.AlignRight | Qt.AlignVCenter, f"ROUND: {self.round_n}")

        # status banner
        srect = QRectF(w * 0.12, 92, w * 0.76, 46)
        col = QColor("#4ADE80")
        painter.setPen(QPen(col, 2))
        bgc = QColor(col)
        bgc.setAlpha(35)
        painter.setBrush(bgc)
        painter.drawRoundedRect(srect, 12, 12)
        painter.setFont(QFont("Helvetica", 16, QFont.Black))
        painter.setPen(col)
        painter.drawText(srect, Qt.AlignCenter, "PRESS THE MATCHING COLOR & WORD")

        # 3 stroop buttons
        top = srect.bottom() + 40
        gap = w * 0.04
        bw = (w - 2 * w * 0.06 - 2 * gap) / 3
        bh = min(bw * 0.9, h - top - 110)

        for pos, (fill, label) in enumerate(self.layout):
            x = w * 0.06 + pos * (bw + gap)
            rect = QRectF(x, top, bw, bh)
            painter.setPen(QPen(QColor("#E2E8F0"), 3))
            painter.setBrush(QColor(COLOR_HEX[fill]))
            painter.drawRoundedRect(rect, 18, 18)

            if now - self.key_flash[pos] < 0.15:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(255, 255, 255, 90))
                painter.drawRoundedRect(rect, 18, 18)

            self._draw_label(painter, rect, LABELS[label])

            cap = QRectF(rect.center().x() - 34, rect.bottom() + 16, 68, 52)
            painter.setPen(QPen(QColor("#64748B"), 2))
            painter.setBrush(QColor("#1E293B"))
            painter.drawRoundedRect(cap, 10, 10)
            painter.setPen(QColor("#E2E8F0"))
            painter.setFont(QFont("Helvetica", 24, QFont.Bold))
            painter.drawText(cap, Qt.AlignCenter, KEY_GLYPHS[pos])

        # floating score popups
        self.popups = [pp for pp in self.popups if now - pp[3] < 0.8]
        for pos, text, color, t0 in self.popups:
            age = (now - t0) / 0.8
            x = w * 0.06 + pos * (bw + gap)
            c = QColor(color)
            c.setAlpha(int(255 * (1 - age)))
            painter.setPen(QPen(c, 5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(x, top, bw, bh), 18, 18)
            painter.setPen(c)
            painter.setFont(QFont("Helvetica", 28, QFont.Black))
            painter.drawText(QRectF(x, top - 45 - 25 * age, bw, 40), Qt.AlignCenter, text)

    def _draw_label(self, painter, rect, text):
        size = int(rect.height() * 0.24)
        font = QFont("Helvetica", size, QFont.Black)
        while size > 10 and QFontMetrics(font).horizontalAdvance(text) > rect.width() * 0.84:
            size -= 1
            font.setPointSize(size)
        fm = QFontMetrics(font)
        path = QPainterPath()
        x = rect.center().x() - fm.horizontalAdvance(text) / 2
        y = rect.center().y() + (fm.ascent() - fm.descent()) / 2
        path.addText(QPointF(x, y), font, text)
        painter.setPen(QPen(QColor("#0B0F19"), max(3, size // 8), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawPath(path)

    def closeEvent(self, event):
        self.timer.stop()
        self.feedback.close()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    feedback = FeedbackController(base_dir=base_dir)

    # show startup dialog to choose positive_1..3 and negative_1..3
    dialog = StimulusConfigDialog(feedback)
    if dialog.exec_() == QDialog.Accepted:
        pos_choice, neg_choice = dialog.get_selections()
        feedback.set_modes(pos_choice, neg_choice)
        window = StroopHapticGame(feedback)
        window.show()
        sys.exit(app.exec_())
    else:
        feedback.close()
        sys.exit(0)