"""Pre-train: learn the feedback cues before the training (adapted from pre_study/validating_cues.py).

A cue is played, the participant answers  <-  = it meant CORRECT,  ->  = it meant INCORRECT.
SPACE / R plays the cue again. One block per cue modality (config.PRETRAIN_BLOCKS, in that order), each
PRETRAIN_BLOCK_SECONDS long. The cues are exactly those of the main paradigm (feedback_cues.play_feedback):
no choice of patterns, mapping or modality as in the pre-study.

Saves logs/pretrain/sXX_pretrain.csv (one row per cue; a repeated pre-train overwrites the file).
ESC (researcher) stops early, saves what was answered and goes back to the menu.
"""

import csv
import os
import random
import time

from PyQt5.QtCore import QRectF, QTimer, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QWidget

from config import (
    PRETRAIN_BLOCK_SECONDS,
    PRETRAIN_BLOCKS,
    PRETRAIN_FEEDBACK_MS,
    PRETRAIN_HIT_POINTS,
    PRETRAIN_WRONG_PENALTY,
    base_dir,
)
from feedback_cues import channels_for, play_feedback
from lsl_markers import send_marker
from sequences import subject_tag
from texts import block_name

PRETRAIN_DIR = os.path.join(base_dir, "logs", "pretrain")
W, H = 1920.0, 1080.0

TXT = {
    "title": {"en": "Learn the feedback cues", "es": "Aprende las señales de retroalimentación",
              "de": "Lerne die Feedback-Signale"},
    "intro": {
        "en": "In the experiment the system tells you whether each battery you place is right or wrong.\n\n"
              "Here you learn these signals. After each signal press:\n"
              "     ←   if it means  RIGHT\n"
              "     →   if it means  WRONG\n\n"
              "SPACE plays the signal again. There are {n} short blocks of {s} seconds:\n{blocks}",
        "es": "En el experimento el sistema te dice si cada batería que colocas está bien o mal.\n\n"
              "Aquí aprendes estas señales. Después de cada señal presiona:\n"
              "     ←   si significa  BIEN\n"
              "     →   si significa  MAL\n\n"
              "ESPACIO repite la señal. Hay {n} bloques cortos de {s} segundos:\n{blocks}",
        "de": "Im Experiment sagt dir das System, ob jede Batterie, die du einsetzt, richtig oder falsch ist.\n\n"
              "Hier lernst du diese Signale. Drücke nach jedem Signal:\n"
              "     ←   wenn es  RICHTIG  bedeutet\n"
              "     →   wenn es  FALSCH  bedeutet\n\n"
              "LEERTASTE spielt das Signal noch einmal. Es gibt {n} kurze Blöcke mit je {s} Sekunden:\n{blocks}"},
    "block": {"en": "Block {i} of {n}: {name}", "es": "Bloque {i} de {n}: {name}", "de": "Block {i} von {n}: {name}"},
    "where": {"audio": {"en": "You hear the signals in your headphones.", "es": "Escuchas las señales en tus audífonos.",
                        "de": "Du hörst die Signale in deinen Kopfhörern."},
              "haptic": {"en": "You feel the signals on the vest.", "es": "Sientes las señales en el chaleco.",
                         "de": "Du spürst die Signale an der Weste."},
              "audio_haptic": {"en": "You hear the signals and feel them on the vest.",
                               "es": "Escuchas las señales y las sientes en el chaleco.",
                               "de": "Du hörst die Signale und spürst sie an der Weste."}},
    "press_enter": {"en": "Press ENTER to start", "es": "Presiona ENTER para empezar", "de": "Drücke ENTER zum Starten"},
    "ask": {"en": "Signal given: was it RIGHT or WRONG?", "es": "Señal dada: ¿era BIEN o MAL?",
            "de": "Signal gegeben: war es RICHTIG oder FALSCH?"},
    "hit": {"en": "Correct!  +{p}", "es": "¡Correcto!  +{p}", "de": "Richtig erkannt!  +{p}"},
    "miss_right": {"en": "Not quite: that was the RIGHT signal  -{p}", "es": "No: esa era la señal de BIEN  -{p}",
                   "de": "Nicht ganz: das war das Signal RICHTIG  -{p}"},
    "miss_wrong": {"en": "Not quite: that was the WRONG signal  -{p}", "es": "No: esa era la señal de MAL  -{p}",
                   "de": "Nicht ganz: das war das Signal FALSCH  -{p}"},
    "right": {"en": "RIGHT", "es": "BIEN", "de": "RICHTIG"},
    "wrong": {"en": "WRONG", "es": "MAL", "de": "FALSCH"},
    "right_sub": {"en": "the battery is right", "es": "la batería está bien", "de": "die Batterie ist richtig"},
    "wrong_sub": {"en": "the battery is wrong", "es": "la batería está mal", "de": "die Batterie ist falsch"},
    "keys": {"en": "[←] right   |   [→] wrong   |   [SPACE] play again",
             "es": "[←] bien   |   [→] mal   |   [ESPACIO] repetir",
             "de": "[←] richtig   |   [→] falsch   |   [LEERTASTE] nochmal"},
    "done": {"en": "Well done!", "es": "¡Muy bien!", "de": "Gut gemacht!"},
    "done_body": {"en": "You have finished learning the signals.\nPlease tell the researcher.",
                  "es": "Terminaste de aprender las señales.\nPor favor, avisa al investigador.",
                  "de": "Du hast die Signale gelernt.\nBitte sag der Versuchsleitung Bescheid."},
    "score": {"en": "SCORE", "es": "PUNTOS", "de": "PUNKTE"},
    "time": {"en": "TIME", "es": "TIEMPO", "de": "ZEIT"},
}

CSV_COLUMNS = ["subject", "timestamp", "language", "audio_cue_mode", "block", "block_modality", "trial",
               "cue", "audio_file", "haptic_pattern", "haptic_location", "response", "identified_correctly",
               "reaction_time_s", "replays", "score_after"]


def _font(px, bold=False):
    f = QFont("Helvetica")
    f.setPixelSize(int(px))
    f.setBold(bold)
    return f


def pretrain_path(subject):
    return os.path.join(PRETRAIN_DIR, f"{subject_tag(subject)}_pretrain.csv")


class PretrainScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.rng = random.Random()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.finish_cb = None
        self.page = "idle"
        self._reset_session("1", "en", "voice")

    # ------------------------------------------------------------------ flow
    def start(self, subject, language, audio_cue_mode, finish_cb):
        self.finish_cb = finish_cb
        self._reset_session(subject, language, audio_cue_mode)
        self.page = "intro"
        send_marker(f"Pretrain_Start_Subj_{subject}_Lang_{language}_AudioMode_{audio_cue_mode}")
        self.timer.start(50)
        self.setFocus()
        self.update()

    def _reset_session(self, subject, language, audio_cue_mode):
        self.subject, self.lang, self.audio_cue_mode = subject, language if language in ("en", "es", "de") else "en", audio_cue_mode
        self.block = 0
        self.score = 0
        self.records = []
        self.bag = []
        self.trial = 0
        self.cue_correct = None        # True = the RIGHT cue was played
        self.played = {}
        self.replays = 0
        self.waiting = False
        self.cue_time = 0.0
        self.block_end = 0.0
        self.result = None             # "hit" | "miss"
        self.result_until = 0.0
        self.saved = False

    def _tx(self, key, **kw):
        s = TXT[key][self.lang]
        return s.format(**kw) if kw else s

    def _modality(self):
        return PRETRAIN_BLOCKS[self.block]

    def _start_block(self):
        self.page = "trials"
        self.trial = 0
        self.block_end = time.perf_counter() + PRETRAIN_BLOCK_SECONDS
        send_marker(f"Pretrain_Block_Start_{self.block + 1}_{self._modality()}")
        self._next_cue()

    def _next_cue(self):
        if not self.bag:                               # balanced: 2 right + 2 wrong, shuffled
            self.bag = [True, True, False, False]
            self.rng.shuffle(self.bag)
        self.cue_correct = self.bag.pop()
        self.trial += 1
        self.replays = 0
        self.result = None
        self._play()
        self.cue_time = time.perf_counter()
        self.waiting = True
        send_marker(f"Pretrain_Cue_Block_{self.block + 1}_Trial_{self.trial}_{'correct' if self.cue_correct else 'incorrect'}")

    def _play(self):
        self.played = play_feedback(channels_for(self._modality()), self.cue_correct)

    def _answer(self, said_correct):
        rt = time.perf_counter() - self.cue_time
        right = said_correct == self.cue_correct
        self.score += PRETRAIN_HIT_POINTS if right else -PRETRAIN_WRONG_PENALTY
        self._record("correct" if said_correct else "incorrect", "yes" if right else "no", round(rt, 4))
        send_marker(f"Pretrain_Response_Block_{self.block + 1}_Trial_{self.trial}_"
                    f"{'correct' if said_correct else 'incorrect'}_{'hit' if right else 'miss'}_RT_{int(rt * 1000)}")
        self.waiting = False
        self.result = "hit" if right else "miss"
        self.result_until = time.perf_counter() + PRETRAIN_FEEDBACK_MS / 1000

    def _record(self, response, identified, rt):
        self.records.append({
            "subject": self.subject, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "language": self.lang,
            "audio_cue_mode": self.audio_cue_mode, "block": self.block + 1, "block_modality": self._modality(),
            "trial": self.trial, "cue": "correct" if self.cue_correct else "incorrect",
            "audio_file": self.played.get("audio_file", ""), "haptic_pattern": self.played.get("haptic_pattern", ""),
            "haptic_location": self.played.get("haptic_location", ""), "response": response,
            "identified_correctly": identified, "reaction_time_s": rt, "replays": self.replays,
            "score_after": self.score})

    def _end_block(self):
        if self.waiting:                                # time ran out before the answer
            self._record("", "no_response", "")
            self.waiting = False
        rows = [r for r in self.records if r["block"] == self.block + 1 and r["identified_correctly"] != "no_response"]
        hits = sum(r["identified_correctly"] == "yes" for r in rows)
        send_marker(f"Pretrain_Block_End_{self.block + 1}_{self._modality()}_Hits_{hits}_of_{len(rows)}")
        self.block += 1
        if self.block < len(PRETRAIN_BLOCKS):
            self.page = "block_intro"
        else:
            self._save()
            send_marker(f"Pretrain_Finished_Subj_{self.subject}_Score_{self.score}")
            self.page = "done"

    def _save(self):
        if self.saved:
            return
        os.makedirs(PRETRAIN_DIR, exist_ok=True)
        path = pretrain_path(self.subject)
        with open(path, "w", newline="", encoding="utf-8") as f:     # a repeated pre-train overwrites
            w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            w.writeheader()
            w.writerows(self.records)
        self.saved = True
        print(f"Pre-train saved: {path}")

    def _leave(self):
        self.timer.stop()
        self.page = "idle"
        if self.finish_cb is not None:
            self.finish_cb()

    def _tick(self):
        now = time.perf_counter()
        if self.page == "trials":
            if now >= self.block_end and (self.waiting or self.result is None or now >= self.result_until):
                self._end_block()
            elif self.result is not None and now >= self.result_until:
                self._next_cue()
        self.update()

    # ------------------------------------------------------------------ keys
    def keyPressEvent(self, event):
        if event.isAutoRepeat():
            return
        key = event.key()
        if key == Qt.Key_Escape:                        # researcher: stop early, keep what was answered
            if self.page in ("trials", "block_intro", "intro"):
                if self.waiting:
                    self._record("", "no_response", "")
                    self.waiting = False
                if self.records:
                    self._save()
                send_marker(f"Pretrain_Aborted_Subj_{self.subject}")
            self._leave()
            return
        enter = key in (Qt.Key_Return, Qt.Key_Enter)
        if self.page == "intro" and enter:
            self.page = "block_intro"
        elif self.page == "block_intro" and enter:
            self._start_block()
        elif self.page == "done" and enter:
            self._leave()
        elif self.page == "trials" and self.waiting:
            if key in (Qt.Key_Left, Qt.Key_Right):
                self._answer(key == Qt.Key_Left)
            elif key in (Qt.Key_Space, Qt.Key_R):
                self.replays += 1
                self._play()
                send_marker(f"Pretrain_Replay_Block_{self.block + 1}_Trial_{self.trial}")
        self.update()

    # ------------------------------------------------------------------ painting
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.fillRect(self.rect(), QColor("#0B1220"))
        s = min(self.width() / W, self.height() / H) or 1.0
        p.translate((self.width() - W * s) / 2, (self.height() - H * s) / 2)
        p.scale(s, s)
        {"intro": self._paint_intro, "block_intro": self._paint_block_intro,
         "trials": self._paint_trials, "done": self._paint_done}.get(self.page, lambda _p: None)(p)

    def _header(self, p, text):
        p.setPen(QColor("#94A3B8"))
        p.setFont(_font(22, True))
        p.drawText(QRectF(70, 30, 1780, 40), Qt.AlignVCenter | Qt.AlignLeft,
                   f"{subject_tag(self.subject).upper()}   -   Pre-train")
        p.setPen(QColor("#F8FAFC"))
        p.setFont(_font(46, True))
        p.drawText(QRectF(70, 80, 1780, 70), Qt.AlignVCenter | Qt.AlignLeft, text)

    def _panel(self, p, rect, text, px=34, color="#E2E8F0"):
        p.setPen(QPen(QColor("#334155"), 2))
        p.setBrush(QColor("#111A2E"))
        p.drawRoundedRect(rect, 16, 16)
        p.setPen(QColor(color))
        p.setFont(_font(px))
        p.drawText(rect.adjusted(60, 50, -60, -50), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, text)

    def _footer(self, p, text):
        p.setPen(QColor("#94A3B8"))
        p.setFont(_font(26, True))
        p.drawText(QRectF(70, 990, 1780, 60), Qt.AlignCenter, text)

    def _paint_intro(self, p):
        self._header(p, self._tx("title"))
        blocks = "\n".join(f"     {i}. {block_name(m, self.lang)}" for i, m in enumerate(PRETRAIN_BLOCKS, start=1))
        self._panel(p, QRectF(70, 180, 1780, 790),
                    self._tx("intro", n=len(PRETRAIN_BLOCKS), s=PRETRAIN_BLOCK_SECONDS, blocks=blocks))
        self._footer(p, self._tx("press_enter"))

    def _paint_block_intro(self, p):
        mod = self._modality()
        self._header(p, self._tx("block", i=self.block + 1, n=len(PRETRAIN_BLOCKS), name=block_name(mod, self.lang)))
        self._panel(p, QRectF(70, 180, 1780, 790),
                    TXT["where"][mod][self.lang] + "\n\n" + self._tx("keys"), px=40)
        self._footer(p, self._tx("press_enter"))

    def _paint_trials(self, p):
        now = time.perf_counter()
        mod = self._modality()
        # HUD
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#0F172A"))
        p.drawRoundedRect(QRectF(40, 30, 1840, 90), 14, 14)
        p.setPen(QColor("#F8FAFC"))
        p.setFont(_font(32, True))
        p.drawText(QRectF(80, 30, 900, 90), Qt.AlignVCenter | Qt.AlignLeft,
                   f"{self._tx('score')}: {self.score:04d}")
        p.drawText(QRectF(560, 30, 800, 90), Qt.AlignCenter,
                   self._tx("block", i=self.block + 1, n=len(PRETRAIN_BLOCKS), name=block_name(mod, self.lang)))
        left = max(0, int(self.block_end - now + 0.999))
        p.setPen(QColor("#38BDF8"))
        p.drawText(QRectF(1000, 30, 840, 90), Qt.AlignVCenter | Qt.AlignRight, f"{self._tx('time')}: {left} s")
        # researcher line: vest connection
        if "haptic" in channels_for(mod):
            from haptics import player
            ok = player.connected
            p.setPen(QColor("#4ADE80" if ok else "#F87171"))
            p.setFont(_font(18, True))
            p.drawText(QRectF(40, 122, 1840, 26), Qt.AlignCenter, "VEST: OK" if ok else "VEST: NOT CONNECTED (bHaptics Player)")
        # banner
        banner = QRectF(160, 160, 1600, 100)
        if self.result is None:
            p.setPen(QPen(QColor("#38BDF8"), 3))
            p.setBrush(QColor("#1E293B"))
            text, color = self._tx("ask"), "#F8FAFC"
        elif self.result == "hit":
            p.setPen(QPen(QColor("#22C55E"), 3))
            p.setBrush(QColor("#14532D"))
            text, color = self._tx("hit", p=PRETRAIN_HIT_POINTS), "#BBF7D0"
        else:
            p.setPen(QPen(QColor("#EF4444"), 3))
            p.setBrush(QColor("#7F1D1D"))
            key = "miss_right" if self.cue_correct else "miss_wrong"
            text, color = self._tx(key, p=PRETRAIN_WRONG_PENALTY), "#FECACA"
        p.drawRoundedRect(banner, 14, 14)
        p.setPen(QColor(color))
        p.setFont(_font(38, True))
        p.drawText(banner, Qt.AlignCenter, text)
        # answer cards
        for x, arrow, word, sub, edge, fill, txt in (
                (160, "←", self._tx("right"), self._tx("right_sub"), "#22C55E", "#0F3D24", "#4ADE80"),
                (980, "→", self._tx("wrong"), self._tx("wrong_sub"), "#EF4444", "#4A1414", "#F87171")):
            card = QRectF(x, 300, 780, 640)
            p.setPen(QPen(QColor(edge), 5 if self.waiting else 2))
            p.setBrush(QColor(fill))
            p.drawRoundedRect(card, 20, 20)
            p.setPen(QColor(txt))
            p.setFont(_font(150, True))
            p.drawText(QRectF(x, 340, 780, 220), Qt.AlignCenter, arrow)
            p.setFont(_font(78, True))
            p.drawText(QRectF(x, 580, 780, 110), Qt.AlignCenter, word)
            p.setPen(QColor("#E2E8F0"))
            p.setFont(_font(32))
            p.drawText(QRectF(x, 700, 780, 60), Qt.AlignCenter, sub)
        self._footer(p, self._tx("keys"))

    def _paint_done(self, p):
        self._header(p, self._tx("done"))
        lines = [self._tx("done_body"), ""]
        for i, mod in enumerate(PRETRAIN_BLOCKS, start=1):
            rows = [r for r in self.records if r["block"] == i and r["identified_correctly"] != "no_response"]
            hits = sum(r["identified_correctly"] == "yes" for r in rows)
            lines.append(f"{i}. {block_name(mod, self.lang)}:   {hits} / {len(rows)}")
        lines += ["", f"{self._tx('score')}: {self.score}"]
        self._panel(p, QRectF(70, 180, 1780, 790), "\n".join(lines), px=40)
        p.setPen(QColor("#64748B"))
        p.setFont(_font(20))
        p.drawText(QRectF(70, 990, 1780, 60), Qt.AlignCenter,
                   f"Saved: logs/pretrain/{os.path.basename(pretrain_path(self.subject))}   -   ENTER = main menu")
