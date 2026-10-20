import csv
import itertools
import os
import random

# configuration: total number of workpieces
num_workpieces = 17

# pre-generate all (sum, instruction, ordering) triples for equation tasks
colors = [("Blue", 1), ("Red", 2), ("Yellow", 3), ("Green", 4)]
slot_multipliers = [1, 2, 3]
text_solutions = []

for (name1, v1), (name2, v2) in itertools.combinations(colors, 2):
    # two of color1, one of color2
    items1 = [v1, v1, v2]
    instr1 = f"Use 2 {name1} and 1 {name2}"
    for p in set(itertools.permutations(items1)):
        s = sum(item * m for item, m in zip(p, slot_multipliers))
        ordering = tuple(name1 if val == v1 else name2 for val in p)
        text_solutions.append((s, instr1, ordering))

    # one of color1, two of color2
    items2 = [v1, v2, v2]
    instr2 = f"Use 1 {name1} and 2 {name2}"
    for p in set(itertools.permutations(items2)):
        s = sum(item * m for item, m in zip(p, slot_multipliers))
        ordering = tuple(name1 if val == v1 else name2 for val in p)
        text_solutions.append((s, instr2, ordering))

text_solutions = sorted(set(text_solutions))

# ensure output directory exists
os.makedirs("log_files", exist_ok=True)

# define the six experimental conditions: (code_digit, condition_name)
conditions = [
    ("1", "baseline"),
    ("2", "audio"),
    ("3", "haptics"),
    ("4", "audio_haptics"),
    ("5", "slow"),
    ("6", "fast"),
]

# loop over subjects (1 to 20) and conditions
for subj in range(1, 21):
    for code_digit, cond_name in conditions:
        # seed based on subject number and condition digit
        seed_code = int(f"{subj}{code_digit}")
        random.seed(seed_code)

        # generate equation trials
        records = []
        for piece in range(1, num_workpieces + 1):
            s, instr, ordering = random.choice(text_solutions)
            ans = ", ".join(ordering)
            records.append({
                "piece": piece,
                "sum": s,
                "instruction": instr,
                "answer": ans,
            })

        # construct target filename (e.g., s01_baseline.txt)
        filename = f"s{subj:02d}_{cond_name}.txt"
        file_path = os.path.join("log_files", filename)

        # write trial data and answers into a single condition file
        with open(file_path, "w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(["piece", "sum", "instruction", "answer"])
            for r in records:
                writer.writerow([r["piece"], r["sum"], r["instruction"], r["answer"]])

        print(f"wrote {file_path}")