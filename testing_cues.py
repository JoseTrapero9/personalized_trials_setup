import sys
import os
import json
import time
import random
import threading
import websocket
from PyQt5.QtCore import QPointF, QRectF, QTimer, Qt, QUrl
from PyQt5.QtGui import QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QApplication, QWidget
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


class FeedbackController:
    """manages persistent bhaptics player websocket connection and wav playback."""

    def __init__(self, base_dir="."):
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

    def _start_bhaptics_client(self):
        # explicit 127.0.0.1 avoids windows ipv6 localhost resolution delays
        url = "ws://127.0.0.1:15881/v2/feedbacks?app_id=stroop_x16&app_name=Stroop_Haptic_Game"

        def on_open(ws):
            self.connected = True
            print("connected to bhaptics player.")

        def on_close(ws, close_status_code, close_msg):
            self.connected = False

        def on_error(ws, error):
            self.connected = False

        def on_message(ws, message):
            # consume incoming status frames from bhaptics player so buffer never blocks
            pass

        self.ws_app = websocket.WebSocketApp(
            url,
            on_open=on_open,
            on_close=on_close,
            on_error=on_error,
            on_message=on_message
        )

        # run the websocket loop in a background daemon thread with auto-reconnect
        def run_loop():
            while True:
                try:
                    self.ws_app.run_forever(ping_interval=5, ping_timeout=2)
                except Exception:
                    pass
                time.sleep(2.0)

        threading.Thread(target=run_loop, daemon=True).start()

    def _send_dot_frame(self, key, position, motor_tuples, duration_ms):
        """sends a dot-mode frame to bhaptics player."""
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

    def trigger_correct(self):
        """plays correct_answer.wav and triggers a positive upward wave on the back (< 1s)."""
        if self.snd_correct.isLoaded():
            self.snd_correct.play()
        threading.Thread(target=self._haptic_correct_pattern, daemon=True).start()

    def trigger_incorrect(self):
        """plays incorrect_answer.wav and triggers a negative double pulse on the front (< 1s)."""
        if self.snd_incorrect.isLoaded():
            self.snd_incorrect.play()
        threading.Thread(target=self._haptic_incorrect_pattern, daemon=True).start()

    def _haptic_correct_pattern(self):
        # vestback has its own 0-19 coordinate space (for x16, top row is 0-3, bottom row is 4-7,
        # plus 8-19 if mapped across the full 5x4 grid; we include both to guarantee x16 activation)
        lower_back = [(i, 40) for i in (4, 5, 6, 7, 12, 13, 14, 15, 16, 17, 18, 19)]
        upper_back = [(i, 65) for i in (0, 1, 2, 3, 8, 9, 10, 11)]

        # step 1: soft lower-back onset (180 ms)
        self._send_dot_frame("pos_wave_1", "VestBack", lower_back, 180)
        time.sleep(0.16)
        # step 2: smooth upward crest on upper back (320 ms) -> total ~480 ms
        self._send_dot_frame("pos_wave_2", "VestBack", upper_back, 320)

    def _haptic_incorrect_pattern(self):
        # vestfront: activate all front motors at 100% in two sharp staccato bursts
        front_all = [(i, 100) for i in range(20)]

        # burst 1 (120 ms) -> gap (100 ms) -> burst 2 (120 ms) -> total 340 ms
        self._send_dot_frame("neg_burst_1", "VestFront", front_all, 120)
        time.sleep(0.22)
        self._send_dot_frame("neg_burst_2", "VestFront", front_all, 120)

    def close(self):
        if self.ws_app is not None:
            try:
                self.ws_app.close()
            except Exception:
                pass


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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Stroop Task - bHaptics X16")
        self.setMinimumSize(640, 480)
        self.setFocusPolicy(Qt.StrongFocus)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.feedback = FeedbackController(base_dir=base_dir)
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

        # top hud with live vest connection status
        hud = QRectF(16, 16, w - 32, 56)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(15, 23, 42, 220))
        painter.drawRoundedRect(hud, 10, 10)
        painter.setFont(QFont("Helvetica", 18, QFont.Bold))
        painter.setPen(QColor("#F8FAFC"))
        painter.drawText(hud.adjusted(16, 0, -16, 0), Qt.AlignLeft | Qt.AlignVCenter, f"SCORE: {self.score:04d}")

        vest_status = "VEST: OK" if self.feedback.connected else "VEST: DISCONNECTED"
        painter.setFont(QFont("Helvetica", 12, QFont.Bold))
        painter.setPen(QColor("#4ADE80") if self.feedback.connected else QColor("#F87171"))
        painter.drawText(hud, Qt.AlignCenter, vest_status)

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
    window = StroopHapticGame()
    window.show()
    sys.exit(app.exec_())