"""Button-panel rules: problem pools and Stroop layouts. Pure Python, no Qt / audio.

A problem is a list of steps. Each step is (kind, color):
    kind "C" -> press the button whose COLOR is `color`      ("the red button")
    kind "L" -> press the button whose WORD is `color`       ("the button labeled red")
A layout is 3 buttons, one per screen position (0 = Left arrow, 1 = Up arrow, 2 = Right arrow),
each (fill_color, label_color). On every button the word never matches the fill (Stroop).
"""

import random

from config import ALL_CONDITIONS
from radio_script import COLOR_KEYS

POS_KEYS = ["left", "up", "right"]

# Exact composition of every block of 20 experiment problems
BLOCK_COMPOSITION = {"single": 6, "seq2": 7, "seq3": 7}
EXPERIMENT_CONDITIONS = [c for c in ALL_CONDITIONS if c != "training"]
BLOCKS_PER_CONDITION = 3              # 60 problems per condition (4 conditions x 3 blocks = 12 blocks)
EXPERIMENT_BLOCKS = 12                # 12 x 20 = 240 problems (matches pre-generated radio_audio clips)
POOL_SEED = 20261104
N_INCIDENTS = 8

# Training: easy -> hard (singles first, then pairs, then triples)
TRAINING_SCHEDULE = ["single"] * 4 + ["seq2"] * 5 + ["seq3"] * 6


# ---------------------------------------------------------------------------
# Layouts
# ---------------------------------------------------------------------------
def random_layout(rng):
    fills = rng.sample(COLOR_KEYS, 3)
    while True:
        labels = rng.sample(COLOR_KEYS, 3)
        if all(f != l for f, l in zip(fills, labels)):
            return list(zip(fills, labels))


def match_layout(rng):
    """Hard-mode match round: exactly one button whose word matches its color. -> (layout, pos)"""
    fills = rng.sample(COLOR_KEYS, 3)
    target = rng.randrange(3)
    while True:
        labels = rng.sample(COLOR_KEYS, 3)
        if all((l == f) == (i == target) for i, (f, l) in enumerate(zip(fills, labels))):
            return list(zip(fills, labels)), target


def resolve_targets(layout, steps):
    """Screen position for each step, or None if a step is ambiguous / missing."""
    targets = []
    for kind, color in steps:
        attr = 0 if kind == "C" else 1
        hits = [i for i, btn in enumerate(layout) if btn[attr] == color]
        if len(hits) != 1:
            return None
        targets.append(hits[0])
    if len(set(targets)) != len(targets):     # every step must be a different button
        return None
    return targets


def lure_count(layout, steps):
    """How many steps have a Stroop lure (same color word on the other attribute of another button)."""
    n = 0
    for kind, color in steps:
        other = 1 if kind == "C" else 0
        if any(btn[other] == color for btn in layout):
            n += 1
    return n


def layout_for(steps, rng, tries=400):
    """A valid layout for `steps`, preferring ones where every step has a lure."""
    best, best_score = None, -1
    for _ in range(tries):
        layout = random_layout(rng)
        if resolve_targets(layout, steps) is None:
            continue
        score = lure_count(layout, steps) + rng.random() * 0.5   # random tie-break
        if score > best_score:
            best, best_score = layout, score
    return best


# ---------------------------------------------------------------------------
# Problems
# ---------------------------------------------------------------------------
def _draw_steps(rng, ptype):
    n = {"single": 1, "seq2": 2, "seq3": 3}[ptype]
    while True:
        kinds = [rng.choice("CL") for _ in range(n)]
        used = {"C": set(), "L": set()}
        steps = []
        for k in kinds:
            color = rng.choice([c for c in COLOR_KEYS if c not in used[k]])
            used[k].add(color)
            steps.append((k, color))
        if layout_for(steps, random.Random(0), tries=600) is not None:   # feasibility check
            return steps


def _make_problem(pid, ptype, rng):
    return {"id": pid, "type": ptype, "steps": _draw_steps(rng, ptype),
            "incident": rng.randrange(N_INCIDENTS)}


def build_pool():
    """Experiment pool (blocks of 20 with identical composition) + training pool. Deterministic."""
    rng = random.Random(POOL_SEED)
    blocks = []
    k = 0
    for _ in range(EXPERIMENT_BLOCKS):
        block = []
        for ptype, count in BLOCK_COMPOSITION.items():
            for _ in range(count):
                block.append(_make_problem(f"e{k:03d}", ptype, rng))
                k += 1
        blocks.append(block)
    training = [_make_problem(f"t{i:02d}", ptype, rng) for i, ptype in enumerate(TRAINING_SCHEDULE)]
    return blocks, training


def condition_blocks(condition):
    """Block indices owned by `condition`. Every condition owns its own blocks, so no instruction
    sentence is ever heard in two different conditions."""
    shuffled = random.Random(f"{POOL_SEED}-assignment").sample(range(EXPERIMENT_BLOCKS), EXPERIMENT_BLOCKS)
    i = EXPERIMENT_CONDITIONS.index(condition)
    return sorted(shuffled[i * BLOCKS_PER_CONDITION:(i + 1) * BLOCKS_PER_CONDITION])


def problem_order(condition, blocks, training):
    """Problems for one condition, in a fixed order (same for every participant and language).
    If a participant needs more, the game reuses this same list (never another condition's)."""
    if condition == "training":
        return list(training)
    if condition not in EXPERIMENT_CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}: add it to ALL_CONDITIONS in config.py "
                         f"and re-run generate_radio_audio.py")
    rng = random.Random(f"order-{condition}")
    order = [p for bi in condition_blocks(condition) for p in blocks[bi]]
    rng.shuffle(order)
    return order


def all_problems():
    blocks, training = build_pool()
    return [p for b in blocks for p in b] + training


def steps_to_str(steps):
    return "|".join(f"{k}-{c}" for k, c in steps)


def layout_to_str(layout):
    return "|".join(f"{f}:{l.upper()}" for f, l in layout)
