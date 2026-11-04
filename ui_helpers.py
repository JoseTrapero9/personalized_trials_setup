"""Small shared Qt helpers."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QFontMetrics
from PyQt5.QtWidgets import QLabel


def auto_fit_label(label, text, max_size=38, min_size=16, margin=30):
    label.setText(text)
    available_width = label.width()
    if available_width <= 100:
        available_width = 520

    target_width = max(available_width - margin, 100)
    font = label.font()
    for size in range(max_size, min_size - 1, -1):
        font.setPointSize(size)
        fm = QFontMetrics(font)
        text_width = fm.horizontalAdvance(text) if hasattr(fm, 'horizontalAdvance') else fm.width(text)
        if text_width <= target_width:
            break
    label.setFont(font)


def make_training_tag():
    tag = QLabel("TRAINING")
    tag.setAlignment(Qt.AlignCenter)
    tag.setFont(QFont("Helvetica", 15, QFont.Bold))
    tag.setStyleSheet(
        "color: #B85C00; background-color: #FFF1DE; "
        "border-radius: 10px; padding: 4px 14px; letter-spacing: 2px;"
    )
    tag.hide()
    return tag
