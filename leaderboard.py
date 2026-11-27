"""General leaderboard: every participant's points are added up over all conditions.

logs/leaderboard_general.json
    {"subjects": {"4": {"initials": "ABC", "conditions": {"baseline": 1180, "audio": 940}, "updated": "..."}}}

* A condition's score is stored when its scoreboard opens; running a condition again REPLACES its score
  (nothing is counted twice). Training is not part of it.
* During a condition the radio score starts at the points of the subject's other conditions, so the score on
  screen keeps growing over the session (carried_score()).
* Initials are asked once per subject (the first scoreboard, training included) and reused afterwards.
"""

import json
import os
import time

from config import base_dir

FILE = os.path.join(base_dir, "logs", "leaderboard_general.json")


def _load():
    try:
        with open(FILE, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data.get("subjects"), dict):
            return data
    except Exception:
        pass
    return {"subjects": {}}


def _save(data):
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, FILE)                  # never a half-written file


def _entry(data, subject):
    return data["subjects"].setdefault(str(subject), {"initials": "", "conditions": {}, "updated": ""})


def carried_score(subject, condition):
    """Points of the subject's OTHER conditions (the start value of the score in `condition`)."""
    e = _load()["subjects"].get(str(subject))
    if not e:
        return 0
    return sum(int(v) for c, v in e["conditions"].items() if c != condition)


def save_condition_score(subject, condition, score):
    """Store (or replace) one condition's points. Returns the subject's new total."""
    data = _load()
    e = _entry(data, subject)
    e["conditions"][condition] = int(score)
    e["updated"] = time.strftime("%Y-%m-%d %H:%M")
    _save(data)
    return sum(int(v) for v in e["conditions"].values())


def total(subject):
    e = _load()["subjects"].get(str(subject))
    return sum(int(v) for v in e["conditions"].values()) if e else 0


def initials(subject):
    e = _load()["subjects"].get(str(subject))
    return (e or {}).get("initials", "")


def set_initials(subject, value):
    data = _load()
    _entry(data, subject)["initials"] = value
    _save(data)


def ranking():
    """[(rank, initials, total, subject)] best first; subjects without points yet are left out."""
    rows = []
    for subj, e in _load()["subjects"].items():
        if e["conditions"]:
            rows.append((e.get("initials") or "???", sum(int(v) for v in e["conditions"].values()), subj))
    rows.sort(key=lambda r: r[1], reverse=True)
    return [(i, name, pts, subj) for i, (name, pts, subj) in enumerate(rows, start=1)]
