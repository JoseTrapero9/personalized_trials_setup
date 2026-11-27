"""Questionnaires: NASA-TLX (after each condition) and the experience questionnaire ("sus" in the
condition menu). Text in EN / ES / DE, saving and per-subject summary files. No Qt in this module.

Files (logs/questionnaires/):
    sXX_<condition>_nasatlx.csv        one row; written after the condition, overwritten on a repeat
    sXX_<condition>_sus.csv            one row; written when that condition's page is finished
    sXX_nasatlx_all_conditions.csv / .xlsx     all conditions of the subject (built at the end of "sus")
    sXX_sus_all_conditions.csv / .xlsx
"""

import csv
import os
import time

from config import base_dir
from sequences import subject_tag

QUESTIONNAIRE_DIR = os.path.join(base_dir, "logs", "questionnaires")
SUS_MENU_ITEM = "sus"                                                    # entry in the setup condition menu
QUESTIONNAIRE_CONDITIONS = ["baseline", "audio", "haptic", "audio_haptic"]   # robot_fast / robot_slow excluded

# ---------------------------------------------------------------------------
# NASA-TLX (raw TLX: six scales, 21 gradations each, no pairwise weighting)
# ---------------------------------------------------------------------------
TLX_STEPS = 21          # gradation 0..20 -> score 0..100 in steps of 5

NASA_TLX = [
    {"id": "mental_demand",
     "title": {"en": "Mental Demand"},
     "question": {"en": "How mentally demanding was the task?"},
     "low": {"en": "Very Low"},
     "high": {"en": "Very High"}},
    {"id": "physical_demand",
     "title": {"en": "Physical Demand"},
     "question": {"en": "How physically demanding was the task?"},
     "low": {"en": "Very Low"},
     "high": {"en": "Very High"}},
    {"id": "temporal_demand",
     "title": {"en": "Temporal Demand"},
     "question": {"en": "How hurried or rushed was the pace of the task?"},
     "low": {"en": "Very Low"},
     "high": {"en": "Very High"}},
    {"id": "performance",
     "title": {"en": "Performance"},
     "question": {"en": "How successful were you in accomplishing what you were asked to do?"},
     "low": {"en": "Perfect"},
     "high": {"en": "Failure"}},
    {"id": "effort",
     "title": {"en": "Effort"},
     "question": {"en": "How hard did you have to work to accomplish your level of performance?"},
     "low": {"en": "Very Low"},
     "high": {"en": "Very High"}},
    {"id": "frustration",
     "title": {"en": "Frustration"},
     "question": {"en": "How insecure, discouraged, irritated, stressed, and annoyed were you?"},
     "low": {"en": "Very Low"},
     "high": {"en": "Very High"}},
]

# ---------------------------------------------------------------------------
# Experience questionnaire ("sus"): 10 statements, 1 = strongly disagree ... 5 = strongly agree
#   scope "all": asked in every condition;  "feedback": not asked in baseline (left empty in the files)
#   negative: negatively worded (a high answer is the bad end) - keep in mind for the analysis
# ---------------------------------------------------------------------------
LIKERT_POINTS = 5

SUS_ITEMS = [
    {"id": "q01_noticed_mistakes", "scope": "all", "negative": False, "text": {"en": "I noticed quickly when I had made a mistake in the battery task."}},
    {"id": "q02_attention_on_radio", "scope": "all", "negative": False, "text": {"en": "I could keep my attention on the radio game while assembling the batteries."}},
    {"id": "q03_in_control", "scope": "all", "negative": False, "text": {"en": "I felt in control of the task."}},
    {"id": "q04_rushed_stressed", "scope": "all", "negative": True, "text": {"en": "I felt rushed or stressed while working."}},
    {"id": "q05_feedback_clear", "scope": "feedback", "negative": False, "text": {"en": "The feedback was easy to perceive and understand."}},
    {"id": "q06_feedback_distracting", "scope": "feedback", "negative": True, "text": {"en": "The feedback distracted me from what I was doing."}},
    {"id": "q07_changed_way_of_working", "scope": "feedback", "negative": False, "text": {"en": "I changed the way I worked because of the feedback."}},
    {"id": "q08_trusted_feedback", "scope": "feedback", "negative": False, "text": {"en": "I trusted the feedback."}},
    {"id": "q09_confident_correct", "scope": "all", "negative": False, "text": {"en": "I felt confident that my assemblies were correct."}},
    {"id": "q10_work_this_way_again", "scope": "all", "negative": False, "text": {"en": "I would like to work this way again."}},
]

# What the participant is told the condition was (coloured bar on top of the page)
CONDITION_LABELS = {
    "baseline": {"color": "#475569", "en": "NO FEEDBACK"},
    "audio": {"color": "#1D4ED8", "en": "SOUND FEEDBACK"},
    "haptic": {"color": "#7C3AED", "en": "VIBRATION VEST FEEDBACK"},
    "audio_haptic": {"color": "#0F766E", "en": "SOUND + VIBRATION VEST FEEDBACK"},
}

# Screen text
QT = {
    "tlx_step": {"en": "Subject {s}   -   NASA Task Load Index   -   condition: {c}"},
    "tlx_title": {"en": "How was the task you just finished?"},
    "tlx_sub": {"en": "Mark one point on each of the six scales. Think only about the rounds you just did."},
    "sus_step": {"en": "Subject {s}   -   Experience questionnaire   -   condition {i} of {n}"},
    "sus_title": {"en": "Your experience in this condition"},
    "sus_sub": {"en": "Think only about the rounds you did with what is named in the coloured bar."},
    "condition_tag": {"en": "(condition: {c})"},
    "intro_step": {"en": "Subject {s}   -   Experience questionnaire"},
    "intro_title": {"en": "A few last questions"},
    "intro_body": {"en": "You worked in {n} different ways today:\n\n{list}\n\n"
              "On the next pages you will see some statements about each of them, one page per way of working.\n"
              "Say how much you agree with each statement. There are no right or wrong answers."},
    "done_title": {"en": "Thank you!"},
    "done_body": {"en": "You have finished the questionnaire.\nPlease tell the researcher."},
    "disagree": {"en": "Strongly\ndisagree"},
    "agree": {"en": "Strongly\nagree"},
    "keys": {"en": "Mouse: click on the scale        Keys:  [UP / DOWN] choose line    [LEFT / RIGHT] answer    [ENTER] continue"},
    "keys_enter": {"en": "[ENTER] continue"},
    "continue": {"en": "CONTINUE"},
    "answered": {"en": "{d} / {n} answered"},
}


def qt(key, lang, **kw):
    s = QT[key].get(lang) or QT[key]["en"]
    return s.format(**kw) if kw else s


def loc(entry, lang):
    return entry.get(lang) or entry["en"]


def sus_items_for(condition):
    """The statements asked for this condition (baseline has no feedback statements)."""
    return [it for it in SUS_ITEMS if it["scope"] == "all" or condition != "baseline"]


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
TLX_COLUMNS = ["subject", "condition", "timestamp", "language", "game_mode"] + \
              [it["id"] for it in NASA_TLX] + ["raw_tlx"]
SUS_COLUMNS = ["subject", "condition", "timestamp", "language"] + [it["id"] for it in SUS_ITEMS]


def _path(subject, name):
    return os.path.join(QUESTIONNAIRE_DIR, f"{subject_tag(subject)}_{name}")


def nasatlx_path(subject, condition):
    return _path(subject, f"{condition}_nasatlx.csv")


def sus_path(subject, condition):
    return _path(subject, f"{condition}_sus.csv")


def _write_single_row(path, columns, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:      # "w": a repeated condition overwrites
        w = csv.writer(f)
        w.writerow(columns)
        w.writerow([row.get(c, "") for c in columns])
    return path


def save_nasatlx(subject, condition, steps, language="en", game_mode=""):
    """steps: one gradation 0..20 per NASA_TLX scale. Saved as 0-100 scores (step * 5) plus the raw TLX mean."""
    scores = [int(s) * 100 // (TLX_STEPS - 1) for s in steps]
    row = {"subject": subject, "condition": condition, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
           "language": language, "game_mode": game_mode, "raw_tlx": round(sum(scores) / len(scores), 2)}
    row.update({it["id"]: sc for it, sc in zip(NASA_TLX, scores)})
    return _write_single_row(nasatlx_path(subject, condition), TLX_COLUMNS, row)


def save_sus(subject, condition, answers, language="en"):
    """answers: {item id: 1..5} for the statements asked in this condition; the others stay empty."""
    row = {"subject": subject, "condition": condition, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
           "language": language}
    row.update(answers)
    return _write_single_row(sus_path(subject, condition), SUS_COLUMNS, row)


def missing_conditions(subject, kind):
    """Conditions of the subject without a saved file. kind: 'nasatlx' | 'sus'."""
    path_of = nasatlx_path if kind == "nasatlx" else sus_path
    return [c for c in QUESTIONNAIRE_CONDITIONS if not os.path.exists(path_of(subject, c))]


def _read_single_row(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else None


def _number(value):
    try:
        f = float(value)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return value


def _write_xlsx(path, sheets):
    """sheets: [(name, columns, rows)]. Returns an error text, or '' when written."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        return "openpyxl is not installed (pip install openpyxl) - only the CSV was written"
    wb = Workbook()
    wb.remove(wb.active)
    for name, columns, rows in sheets:
        ws = wb.create_sheet(name)
        ws.append(columns)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="2F4F4F")
        for row in rows:
            ws.append([_number(v) for v in row])
        for i, col in enumerate(columns, start=1):
            width = max([len(str(col))] + [len(str(r[i - 1])) for r in rows]) + 2
            ws.column_dimensions[get_column_letter(i)].width = min(width, 70)
        ws.freeze_panes = "A2"
    try:
        wb.save(path)
    except OSError as e:
        return f"could not write {os.path.basename(path)} ({e}) - is it open in Excel?"
    return ""


def build_summaries(subject):
    """Collect the subject's per-condition files into one CSV + one Excel file per questionnaire.

    Returns {"files": [paths written], "missing": {"nasatlx": [...], "sus": [...]}, "warnings": [text]}.
    Conditions without a file are simply not in the summary.
    """
    result = {"files": [], "missing": {}, "warnings": []}
    for kind, columns, path_of in (("nasatlx", TLX_COLUMNS, nasatlx_path), ("sus", SUS_COLUMNS, sus_path)):
        result["missing"][kind] = missing_conditions(subject, kind)
        rows = []
        for condition in QUESTIONNAIRE_CONDITIONS:
            path = path_of(subject, condition)
            if not os.path.exists(path):
                continue
            row = _read_single_row(path)
            if row is None:
                result["warnings"].append(f"{os.path.basename(path)} is empty")
                continue
            rows.append([row.get(c, "") for c in columns])
        if not rows:
            continue
        os.makedirs(QUESTIONNAIRE_DIR, exist_ok=True)
        csv_path = _path(subject, f"{kind}_all_conditions.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(columns)
            w.writerows(rows)
        result["files"].append(csv_path)

        sheets = [("answers", columns, rows)]
        if kind == "sus":
            sheets.append(("statements", ["id", "statement", "asked_in", "negatively_worded", "scale"], [
                [it["id"], it["text"]["en"], "all conditions" if it["scope"] == "all" else "not baseline",
                 "yes" if it["negative"] else "no", "1 = strongly disagree ... 5 = strongly agree"]
                for it in SUS_ITEMS]))
        else:
            sheets.append(("scales", ["id", "scale", "question", "0", "100"], [
                [it["id"], it["title"]["en"], it["question"]["en"], it["low"]["en"], it["high"]["en"]]
                for it in NASA_TLX] + [["raw_tlx", "Raw TLX", "Mean of the six scales (no weighting)", "", ""]]))
        xlsx_path = _path(subject, f"{kind}_all_conditions.xlsx")
        error = _write_xlsx(xlsx_path, sheets)
        if error:
            result["warnings"].append(error)
        else:
            result["files"].append(xlsx_path)
    return result
