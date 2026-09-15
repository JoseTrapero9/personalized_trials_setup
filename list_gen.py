import random
import itertools
import csv
import os

# configuration: total number of workpieces and cycle length
NUM_WORKPIECES = 40
LOOP_LENGTH    = 4

# mapping of image index → correct color order
image_answers = {
    1: ["Red",   "Blue",   "Red"],
    2: ["Blue",  "Yellow",  "Blue"],
    3: ["Yellow","Green",  "Yellow"],
    4: ["Green", "Red",    "Green"],
    5: ["Yellow","Blue",   "Blue"],
    6: ["Green", "Red", "Red"],
    7: ["Red",   "Green",  "Green"],
    8: ["Blue",  "Blue",    "Green"],
}

# pre-generate all (sum, instruction, ordering) triples
colors = [("Blue",1), ("Red",2), ("Yellow",3), ("Green",4)]
slot_multipliers = [1,2,3]
text_solutions = []
for (name1, v1), (name2, v2) in itertools.combinations(colors, 2):
    # two of color1, one of color2
    items1 = [v1, v1, v2]
    instr1 = f"Use 2 {name1} and 1 {name2}"
    for p in set(itertools.permutations(items1)):
        s = sum(item*m for item,m in zip(p, slot_multipliers))
        ordering = tuple(name1 if val==v1 else name2 for val in p)
        text_solutions.append((s, instr1, ordering))
    # one of color1, two of color2
    items2 = [v1, v2, v2]
    instr2 = f"Use 1 {name1} and 2 {name2}"
    for p in set(itertools.permutations(items2)):
        s = sum(item*m for item,m in zip(p, slot_multipliers))
        ordering = tuple(name1 if val==v1 else name2 for val in p)
        text_solutions.append((s, instr2, ordering))

text_solutions = sorted(set(text_solutions))

# ensure output directory exists
os.makedirs("log_files", exist_ok=True)

# define conditions: (code_digit, name, text_only_positions)
conditions = [
    ("1", "no_llm", {3,4}),  # no-LLM condition: text-only at positions 3 & 4
    ("2", "llm",   set()),  # LLM condition: no text-only
]

# loop over subjects and conditions
for subj in range(1, 21):
    for code_digit, cond_name, TEXT_ONLY_POSITIONS in conditions:
        # pick seed = subject digit then condition digit, e.g. 11,12,21,...
        seed_code = int(f"{subj}{code_digit}")
        random.seed(seed_code)

        # collect all trials
        records = []
        for piece in range(1, NUM_WORKPIECES+1):
            cycle_pos = ((piece-1) % LOOP_LENGTH) + 1
            if cycle_pos not in TEXT_ONLY_POSITIONS:
                # image trial
                idx   = random.randint(1, 8)
                fname = f"workpiece_{idx}.png"
                ans   = ", ".join(image_answers[idx])
                records.append({
                    "piece": piece,
                    "mode":  "image",
                    "param1": fname,
                    "param2": "",
                    "answer": ans
                })
            else:
                # text trial
                s, instr, ordering = random.choice(text_solutions)
                ans = ", ".join(ordering)
                records.append({
                    "piece": piece,
                    "mode":  "text",
                    "param1": s,
                    "param2": instr,
                    "answer": ans
                })

        # filenames
        subj_str = f"s{subj:02d}_{cond_name}"
        seq_path = os.path.join("log_files", f"{subj_str}_sequence.txt")
        ans_path = os.path.join("log_files", f"{subj_str}_answers.txt")

        # write full sequence file
        with open(seq_path, "w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(["piece", "mode", "param1", "param2"])
            for r in records:
                writer.writerow([r["piece"], r["mode"], r["param1"], r["param2"]])

        # write answers-only file
        with open(ans_path, "w", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            writer.writerow(["answer"])
            for r in records:
                writer.writerow([r["answer"]])

        print(f"wrote {seq_path} and {ans_path}")
