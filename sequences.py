"""Workpiece / battery sequences and instruction helpers."""

import csv
import itertools
import os
import random
import re

from config import base_dir


def load_synch_sequence(path=os.path.join(base_dir, "log_files", "s06_haptics.txt")):
    sequence = []
    if not os.path.exists(path):
        print(f"Warning: File not found at {path}. Using fallback sequence.")
        for _ in range(1, 41):
            sequence.append(("text", random.choice([6, 7, 8, 9]), "Use 2 red and 1 blue"))
        return sequence

    with open(path, "r", encoding="utf-8-sig") as f:
        raw_lines = [line.strip() for line in f if line.strip()]

    for line in raw_lines:
        lower_line = line.lower()
        if lower_line.startswith(("piece", "mode", "trial")):
            continue

        if "\t" in line:
            tokens = [t.strip() for t in line.split("\t") if t.strip()]
        elif "," in line and not re.search(r'\s{2,}', line):
            tokens = [t.strip() for t in next(csv.reader([line])) if t.strip()]
        else:
            tokens = [t.strip() for t in re.split(r'\s{2,}', line) if t.strip()]

        if not tokens:
            continue

        if tokens[0].lower() == "image" and len(tokens) >= 2:
            sequence.append(("image", tokens[1], None))
            continue
        elif len(tokens) >= 3 and tokens[1].lower() == "image":
            sequence.append(("image", tokens[2], None))
            continue

        if tokens[0].lower() == "text" and len(tokens) >= 3:
            try:
                sequence.append(("text", int(tokens[1]), tokens[2]))
                continue
            except ValueError:
                pass

        if len(tokens) >= 3:
            try:
                target_sum = int(tokens[1])
                instruction_text = tokens[2]
                sequence.append(("text", target_sum, instruction_text))
                continue
            except ValueError:
                pass

        match = re.match(r'^\s*(\d+)\s+(\d+)\s+(.+?)(?:\s{2,}|\t)(.+)$', line)
        if match:
            try:
                target_sum = int(match.group(2))
                instruction_text = match.group(3).strip()
                sequence.append(("text", target_sum, instruction_text))
                continue
            except ValueError:
                pass

    return sequence


WORKPIECE_SEQUENCE = load_synch_sequence()
COLOR_NAMES = {1: "Blue", 2: "Red", 3: "Yellow", 4: "Green"}


def format_battery_instruction(colors):
    counts = {}
    for c in colors:
        counts[c] = counts.get(c, 0) + 1
    parts = [f"{n} {COLOR_NAMES[c].lower()}" for c, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    if len(parts) == 1:
        return f"Use {parts[0]}"
    return "Use " + ", ".join(parts[:-1]) + " and " + parts[-1]


def slot_sum(order):
    return sum(v * (i + 1) for i, v in enumerate(order))


def build_training_sequence(n_tasks=12, seed=None):
    path = os.path.join(base_dir, "log_files", "training.txt")
    if os.path.exists(path):
        seq = load_synch_sequence(path)
        if seq:
            return seq

    rng = random.Random(seed)
    pool = []
    for combo in itertools.combinations_with_replacement(range(1, 5), 3):
        orders = set(itertools.permutations(combo))
        sums = [slot_sum(o) for o in orders]
        for o in orders:
            if sums.count(slot_sum(o)) == 1 and len(orders) > 1:
                pool.append((combo, slot_sum(o)))

    seq, last = [], None
    while len(seq) < n_tasks:
        combo, total = rng.choice(pool)
        if combo == last:
            continue
        last = combo
        seq.append(("text", total, format_battery_instruction(combo)))
    return seq
