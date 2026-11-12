"""Questionnaire screen: NASA-TLX after a condition, and the experience questionnaire ("sus").

One custom-painted page type for both (drawn on a 1920x1080 canvas that is scaled to the window):
    kind "tlx"      six scales with 21 gradations (click / drag, or arrow keys)
    kind "likert"   statements with 5 answer circles (click, arrow keys, or number keys 1-5)
    kind "message"  text only (intro / thank you)
"""

import os

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QWidget

import questionnaires as q
from lsl_markers import send_marker
from sequences import subject_tag

W, H = 1920.0, 1080.0
LEFT, RIGHT = 70.0, 1850.0
LIKERT_X0, LIKERT_DX = 1330.0, 112.0           # first answer circle, distance between circles
TLX_X0, TLX_X1 = 1000.0, 1800.0                # ends of the 21-gradation scale
BUTTON = QRectF(1570, 1010, 280, 54)


def _font(px, bold=False):
    f = QFont("Helvetica")
    f.setPixelSize(int(px))          # pixel sizes: same layout on every screen DPI
    f.setBold(bold)
    return f


class QuestionnaireScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(False)
        self.page = None             # dict describing what is on screen
        self.answers = []
        self.current = 0
        self._on_page_done = None
        self._finish_cb = None
        self._drag_row = None

    # ------------------------------------------------------------------ flows
    def start_nasatlx(self, subject, condition, language, game_mode, finish_cb):
        """NASA-TLX for the condition that just ended; saves sXX_<condition>_nasatlx.csv, then finish_cb()."""
        self._finish_cb = finish_cb
        send_marker(f"NasaTLX_Started_{condition}")

        def done(steps):
            path = q.save_nasatlx(subject, condition, steps, language, game_mode)
            raw = sum(steps) * 100 / (q.TLX_STEPS - 1) / len(steps)
            send_marker(f"NasaTLX_Saved_{condition}_Raw_{raw:.1f}")
            print(f"NASA-TLX saved: {path}")
            self._finish()

        self._show({
            "kind": "tlx", "lang": language,
            "step": q.qt("tlx_step", language, s=subject_tag(subject)[1:], c=condition),
            "title": q.qt("tlx_title", language),
            "bar": self._bar_text(condition, language), "bar_color": q.CONDITION_LABELS[condition]["color"],
            "sub": q.qt("tlx_sub", language),
            "rows": [{"title": q.loc(it["title"], language), "text": q.loc(it["question"], language),
                      "low": q.loc(it["low"], language), "high": q.loc(it["high"], language)}
                     for it in q.NASA_TLX],
        }, done)

    def start_sus(self, subject, language, finish_cb):
        """Experience questionnaire for every condition, then the per-subject summary files, then finish_cb()."""
        self._finish_cb = finish_cb
        conditions = list(q.QUESTIONNAIRE_CONDITIONS)
        send_marker(f"SUS_Started_Subj_{subject}")

        def show_condition(i):
            if i >= len(conditions):
                return show_done()
            condition = conditions[i]
            items = q.sus_items_for(condition)

            def done(values):
                q.save_sus(subject, condition, {it["id"]: v for it, v in zip(items, values)}, language)
                send_marker(f"SUS_Saved_{condition}")
                show_condition(i + 1)

            self._show({
                "kind": "likert", "lang": language,
                "step": q.qt("sus_step", language, s=subject_tag(subject)[1:], i=i + 1, n=len(conditions)),
                "title": q.qt("sus_title", language),
                "bar": self._bar_text(condition, language), "bar_color": q.CONDITION_LABELS[condition]["color"],
                "sub": q.qt("sus_sub", language),
                "rows": [{"text": q.loc(it["text"], language)} for it in items],
            }, done)

        def show_done():
            result = q.build_summaries(subject)
            send_marker(f"SUS_Finished_Subj_{subject}")
            notes = ["Files: " + ", ".join(os.path.basename(p) for p in result["files"])]
            for kind, missing in result["missing"].items():
                if missing:
                    notes.append(f"No {kind} file for: {', '.join(missing)}")
            notes += result["warnings"]
            print("\n".join(notes))
            self._show({
                "kind": "message", "lang": language,
                "step": q.qt("intro_step", language, s=subject_tag(subject)[1:]),
                "title": q.qt("done_title", language), "body": q.qt("done_body", language),
                "notes": notes,
            }, lambda _: self._finish())

        names = "\n".join(f"     -  {q.loc(q.CONDITION_LABELS[c], language)}" for c in conditions)
        self._show({
            "kind": "message", "lang": language,
            "step": q.qt("intro_step", language, s=subject_tag(subject)[1:]),
            "title": q.qt("intro_title", language),
            "body": q.qt("intro_body", language, n=len(conditions), list=names),
        }, lambda _: show_condition(0))

    @staticmethod
    def _bar_text(condition, language):
        return f"{q.loc(q.CONDITION_LABELS[condition], language)}     {q.qt('condition_tag', language, c=condition)}"

    def _show(self, page, on_done):
        self.page = page
        self.answers = [None] * len(page.get("rows", []))
        self.current = 0
        self._on_page_done = on_done
        self.setFocus()
        self.update()

    def _finish(self):
        self.page = None
        if self._finish_cb is not None:
            self._finish_cb()

    # ------------------------------------------------------------------ geometry
    def _transform(self):
        s = min(self.width() / W, self.height() / H) or 1.0
        return s, (self.width() - W * s) / 2, (self.height() - H * s) / 2

    def _rows_geometry(self):
        """(top of the first row, row height) for the current page."""
        n = max(1, len(self.page["rows"]))
        if self.page["kind"] == "tlx":
            return 262.0, min(124.0, (H - 262 - 84) / n)
        return 322.0, min(70.0, (H - 322 - 90) / n)

    def _points(self):
        return q.TLX_STEPS if self.page["kind"] == "tlx" else q.LIKERT_POINTS

    def _point_x(self, k):
        """x of answer k (0-based) on the scale."""
        if self.page["kind"] == "tlx":
            return TLX_X0 + k * (TLX_X1 - TLX_X0) / (q.TLX_STEPS - 1)
        return LIKERT_X0 + k * LIKERT_DX

    def _value_of(self, k):
        return k if self.page["kind"] == "tlx" else k + 1          # tlx 0..20, likert 1..5

    def _index_of(self, value):
        return value if self.page["kind"] == "tlx" else value - 1

    def _complete(self):
        return all(a is not None for a in self.answers)

    # ------------------------------------------------------------------ input
    def _answer_at(self, pos, need_row=None):
        """Mouse position -> (row, value) or None."""
        s, ox, oy = self._transform()
        x, y = (pos.x() - ox) / s, (pos.y() - oy) / s
        top, rh = self._rows_geometry()
        row = int((y - top) // rh)
        if need_row is not None:
            row = need_row
        elif not (0 <= row < len(self.answers)) or y < top:
            return None
        step = self._point_x(1) - self._point_x(0)
        if not (self._point_x(0) - step * 0.6 <= x <= self._point_x(self._points() - 1) + step * 0.6):
            return None
        k = max(0, min(self._points() - 1, int(round((x - self._point_x(0)) / step))))
        return row, self._value_of(k)

    def mousePressEvent(self, event):
        if self.page is None or event.button() != Qt.LeftButton:
            return
        s, ox, oy = self._transform()
        logical = QPointF((event.x() - ox) / s, (event.y() - oy) / s)
        if BUTTON.contains(logical):
            self._try_continue()
            return
        if self.page["kind"] == "message":
            return
        hit = self._answer_at(event.pos())
        self._drag_row = hit[0] if hit else None
        if hit:
            self.current, self.answers[hit[0]] = hit[0], hit[1]
            self.update()

    def mouseMoveEvent(self, event):
        # drag along a NASA-TLX scale
        if self.page is None or self.page["kind"] != "tlx" or self._drag_row is None:
            return
        hit = self._answer_at(event.pos(), need_row=self._drag_row)
        if hit:
            self.answers[hit[0]] = hit[1]
            self.update()

    def mouseReleaseEvent(self, event):
        self._drag_row = None

    def keyPressEvent(self, event):
        if self.page is None:
            return
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if not event.isAutoRepeat():
                self._try_continue()
            return
        if self.page["kind"] == "message" or not self.answers:
            return
        n = len(self.answers)
        if key == Qt.Key_Down:
            self.current = min(n - 1, self.current + 1)
        elif key == Qt.Key_Up:
            self.current = max(0, self.current - 1)
        elif key in (Qt.Key_Left, Qt.Key_Right):
            value = self.answers[self.current]
            if value is None:
                k = (self._points() - 1) // 2                     # first press: start in the middle
            else:
                k = self._index_of(value) + (1 if key == Qt.Key_Right else -1)
            self.answers[self.current] = self._value_of(max(0, min(self._points() - 1, k)))
        elif self.page["kind"] == "likert" and Qt.Key_1 <= key <= Qt.Key_5:
            self.answers[self.current] = key - Qt.Key_0
            self.current = min(n - 1, self.current + 1)
        else:
            super().keyPressEvent(event)
            return
        self.update()

    def _try_continue(self):
        if self.page["kind"] != "message" and not self._complete():
            self.current = self.answers.index(None)               # jump to the first open line
            self.update()
            return
        done, answers = self._on_page_done, list(self.answers)
        done(answers)

    # ------------------------------------------------------------------ painting
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.fillRect(self.rect(), QColor("#F1F5F9"))
        if self.page is None:
            return
        s, ox, oy = self._transform()
        p.translate(ox, oy)
        p.scale(s, s)
        page, lang = self.page, self.page["lang"]

        p.setPen(QColor("#475467"))
        p.setFont(_font(21, True))
        p.drawText(QRectF(LEFT, 36, 1780, 30), Qt.AlignVCenter | Qt.AlignLeft, page["step"])
        p.setPen(QColor("#111827"))
        p.setFont(_font(40, True))
        p.drawText(QRectF(LEFT, 76, 1780, 56), Qt.AlignVCenter | Qt.AlignLeft, page["title"])

        if page["kind"] == "message":
            self._paint_message(p, page)
        else:
            p.setBrush(QColor(page["bar_color"]))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(LEFT, 142, 1780, 64), 12, 12)
            p.setPen(QColor("white"))
            p.setFont(_font(29, True))
            p.drawText(QRectF(LEFT + 24, 142, 1740, 64), Qt.AlignVCenter | Qt.AlignLeft, page["bar"])
            p.setPen(QColor("#475467"))
            p.setFont(_font(20))
            p.drawText(QRectF(LEFT, 214, 1200, 40), Qt.AlignVCenter | Qt.AlignLeft, page["sub"])
            if page["kind"] == "tlx":
                self._paint_tlx(p, page)
            else:
                self._paint_likert(p, page, lang)

        # footer: key hint + continue button
        p.setPen(QColor("#475467"))
        p.setFont(_font(20))
        hint = q.qt("keys_enter" if page["kind"] == "message" else "keys", lang)
        p.drawText(QRectF(LEFT, 1010, 1480, 54), Qt.AlignVCenter | Qt.AlignLeft, hint)
        ok = page["kind"] == "message" or self._complete()
        p.setBrush(QColor("#16A34A" if ok else "#CBD5E1"))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(BUTTON, 10, 10)
        p.setPen(QColor("white"))
        p.setFont(_font(23, True))
        done = sum(1 for a in self.answers if a is not None)
        p.drawText(BUTTON, Qt.AlignCenter,
                   q.qt("continue", lang) if ok else q.qt("answered", lang, d=done, n=len(self.answers)))

    def _row_frame(self, p, i, y, rh):
        if i == self.current:
            p.setBrush(QColor("#E0F2FE"))
            p.setPen(QPen(QColor("#0284C7"), 3))
        else:
            p.setBrush(QColor("white"))
            p.setPen(QPen(QColor("#E2E8F0"), 1))
        p.drawRoundedRect(QRectF(LEFT, y, 1780, rh - 8), 10, 10)

    def _paint_likert(self, p, page, lang):
        p.setFont(_font(17, True))
        p.setPen(QColor("#334155"))
        for k in range(q.LIKERT_POINTS):
            x = self._point_x(k)
            label = q.qt("disagree", lang) if k == 0 else q.qt("agree", lang) if k == q.LIKERT_POINTS - 1 else ""
            p.drawText(QRectF(x - 90, 246, 180, 46), Qt.AlignCenter, label)
            p.drawText(QRectF(x - 60, 292, 120, 22), Qt.AlignCenter, str(k + 1))
        top, rh = self._rows_geometry()
        for i, row in enumerate(page["rows"]):
            y = top + i * rh
            self._row_frame(p, i, y, rh)
            p.setPen(QColor("#64748B"))
            p.setFont(_font(20, True))
            p.drawText(QRectF(LEFT + 18, y, 44, rh - 8), Qt.AlignVCenter, str(i + 1))
            p.setPen(QColor("#111827"))
            p.setFont(_font(22))
            p.drawText(QRectF(LEFT + 64, y, 1100, rh - 8), Qt.AlignVCenter | Qt.TextWordWrap, row["text"])
            cy = y + (rh - 8) / 2
            p.setPen(QPen(QColor("#CBD5E1"), 3))
            p.drawLine(QPointF(self._point_x(0), cy), QPointF(self._point_x(q.LIKERT_POINTS - 1), cy))
            for k in range(q.LIKERT_POINTS):
                selected = self.answers[i] == k + 1
                p.setPen(QPen(QColor("#0F766E" if selected else "#94A3B8"), 3))
                p.setBrush(QColor("#14B8A6") if selected else QColor("white"))
                p.drawEllipse(QPointF(self._point_x(k), cy), 17, 17)

    def _paint_tlx(self, p, page):
        top, rh = self._rows_geometry()
        for i, row in enumerate(page["rows"]):
            y = top + i * rh
            self._row_frame(p, i, y, rh)
            inner = rh - 8
            p.setPen(QColor("#111827"))
            p.setFont(_font(26, True))
            p.drawText(QRectF(LEFT + 24, y + 10, 860, 34), Qt.AlignVCenter | Qt.AlignLeft, row["title"])
            p.setPen(QColor("#334155"))
            p.setFont(_font(21))
            p.drawText(QRectF(LEFT + 24, y + 46, 860, inner - 52), Qt.AlignTop | Qt.TextWordWrap, row["text"])

            base = y + inner * 0.42                              # scale baseline, ticks go up from it
            p.setPen(QPen(QColor("#111827"), 2))
            p.drawLine(QPointF(TLX_X0, base), QPointF(TLX_X1, base))
            for k in range(q.TLX_STEPS):
                x = self._point_x(k)
                tall = 34 if k == (q.TLX_STEPS - 1) // 2 else 22  # the middle tick is taller, like the paper form
                p.drawLine(QPointF(x, base), QPointF(x, base - tall))
            if self.answers[i] is not None:
                x = self._point_x(self.answers[i])
                p.setPen(QPen(QColor("#0F766E"), 3))
                p.setBrush(QColor("#14B8A6"))
                p.drawEllipse(QPointF(x, base - 11), 13, 13)
            # number under every gradation = the score that is saved (0, 5, ... 100)
            for k in range(q.TLX_STEPS):
                chosen = self.answers[i] == k
                p.setPen(QColor("#0F766E" if chosen else "#475569"))
                p.setFont(_font(17 if chosen else 15, chosen))
                p.drawText(QRectF(self._point_x(k) - 20, base + 3, 40, 22), Qt.AlignCenter,
                           str(k * 100 // (q.TLX_STEPS - 1)))
            p.setPen(QColor("#334155"))
            p.setFont(_font(19))
            p.drawText(QRectF(TLX_X0 - 20, base + 27, 300, 28), Qt.AlignVCenter | Qt.AlignLeft, row["low"])
            p.drawText(QRectF(TLX_X1 - 280, base + 27, 300, 28), Qt.AlignVCenter | Qt.AlignRight, row["high"])

    def _paint_message(self, p, page):
        p.setBrush(QColor("white"))
        p.setPen(QPen(QColor("#E2E8F0"), 1))
        p.drawRoundedRect(QRectF(LEFT, 170, 1780, 790), 14, 14)
        p.setPen(QColor("#111827"))
        p.setFont(_font(31))
        p.drawText(QRectF(LEFT + 60, 220, 1660, 600), Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap, page["body"])
        notes = page.get("notes")
        if notes:                                                  # small researcher info (files written)
            p.setPen(QColor("#64748B"))
            p.setFont(_font(17))
            p.drawText(QRectF(LEFT + 60, 800, 1660, 150), Qt.AlignBottom | Qt.AlignLeft | Qt.TextWordWrap,
                       "\n".join(notes))
