"""Generate the battery-task sequences in log_files/ (sXX_<condition>.txt) and a PDF answer key.

    python generate_log_files.py                  # s01..s25, all conditions, + PDF answer key
    python generate_log_files.py --subjects 30    # s01..s30
    python generate_log_files.py --no-pdf

Every file has the same format as the original logs (tab separated):

    piece   sum   instruction               answer
    1       18    Use 1 Blue and 2 Green    Green, Blue, Green

Rules (identical to the original files):
  * a piece always uses 3 batteries: 2 of one color + 1 of another color (12 color combos, 36 orders)
  * sum = slot1 * 1 + slot2 * 2 + slot3 * 3 with Blue=1, Red=2, Yellow=3, Green=4
  * for these combos the sum always identifies exactly one order, so "answer" is unambiguous
  * the instruction names the colors from low to high value ("Use 2 Red and 1 Yellow")
Extra rules for the new files: no answer repeats inside a file and two consecutive pieces
never share the same instruction.

The generator is seeded: running it again with the same --seed rewrites identical files.
"""

import argparse
import itertools
import os
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "log_files")

COLOR_VALUES = {"Blue": 1, "Red": 2, "Yellow": 3, "Green": 4}
SLOT_MULTIPLIERS = (1, 2, 3)

# file-name suffix used by the original logs (s06_haptics.txt, s01_audio_haptics.txt, ...)
CONDITION_FILES = ["audio", "audio_haptics", "baseline", "fast", "haptics", "slow"]
PIECES_PER_FILE = 17
HEADER = ["piece", "sum", "instruction", "answer"]


def slot_sum(order):
    return sum(COLOR_VALUES[c] * m for c, m in zip(order, SLOT_MULTIPLIERS))


def instruction_for(order):
    counts = {}
    for c in order:
        counts[c] = counts.get(c, 0) + 1
    parts = [f"{n} {c}" for c, n in sorted(counts.items(), key=lambda kv: COLOR_VALUES[kv[0]])]
    return "Use " + " and ".join(parts)


def all_answers():
    """The 36 valid orders: two of one color + one of another."""
    answers = []
    for a, b in itertools.permutations(COLOR_VALUES, 2):
        for order in set(itertools.permutations((a, a, b))):
            answers.append(order)
    answers.sort(key=lambda o: [COLOR_VALUES[c] for c in o])
    # sanity: every sum must point to exactly one order of its colors
    for o in answers:
        same_colors = set(itertools.permutations(o))
        assert [slot_sum(p) for p in same_colors].count(slot_sum(o)) == 1
    return answers


def make_sequence(rng, answers, n=PIECES_PER_FILE):
    while True:
        picked = rng.sample(answers, n)
        if all(instruction_for(a) != instruction_for(b) for a, b in zip(picked, picked[1:])):
            return [(i + 1, slot_sum(o), instruction_for(o), ", ".join(o)) for i, o in enumerate(picked)]


def write_files(n_subjects, seed):
    os.makedirs(LOG_DIR, exist_ok=True)
    rng = random.Random(seed)
    answers = all_answers()
    data = {}
    for s in range(1, n_subjects + 1):
        subj = f"s{s:02d}"
        for cond in CONDITION_FILES:
            rows = make_sequence(rng, answers)
            data[(subj, cond)] = rows
            path = os.path.join(LOG_DIR, f"{subj}_{cond}.txt")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("\t".join(HEADER) + "\n")
                for row in rows:
                    f.write("\t".join(str(v) for v in row) + "\n")
    print(f"Wrote {len(data)} files to {LOG_DIR}")
    return data


def write_pdf(data, path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepInFrame, PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

    styles = getSampleStyleSheet()
    cell_colors = {"Blue": "#1D4ED8", "Red": "#C81E1E", "Yellow": "#8A6100", "Green": "#15803D"}

    def colored(answer):
        return ", ".join(f'<font color="{cell_colors[c]}"><b>{c}</b></font>' for c in answer.split(", "))

    small = styles["BodyText"].clone("small", fontSize=7.5, leading=8.5)
    page = landscape(A4)
    doc = SimpleDocTemplate(path, pagesize=page, leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=8 * mm, bottomMargin=10 * mm,
                            title="Battery task answer key", author="generate_log_files.py")
    story = [
        Paragraph("Battery task answer key", styles["Title"]),
        Paragraph(
            "Subjects s01 to s%02d, one page per subject. Values: Blue = 1, Red = 2, Yellow = 3, Green = 4. "
            "Sum = slot 1 x1 + slot 2 x2 + slot 3 x3. Answer is the order from slot 1 (left) to slot 3 (right). "
            "The GUI uses the first %d pieces of each file (one per round)."
            % (max(int(s[1:]) for s, _ in data), 8),
            styles["BodyText"]),
        PageBreak(),
    ]
    subjects = sorted({s for s, _ in data})
    width = (doc.width - 8 * mm) / 3
    col_w = [8 * mm, 9 * mm, 37 * mm, width - 54 * mm]
    for i, subj in enumerate(subjects):
        page_items = [Paragraph(f"Subject {subj.upper()}", styles["Heading2"])]
        blocks = []
        for cond in CONDITION_FILES:
            rows = data[(subj, cond)]
            table_rows = [[Paragraph(f"<b>{h}</b>", small) for h in ("#", "Sum", "Instruction", "Answer")]]
            for piece, total, instr, ans in rows:
                table_rows.append([str(piece), str(total), Paragraph(instr, small), Paragraph(colored(ans), small)])
            t = Table(table_rows, colWidths=col_w, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F4F4F")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("BACKGROUND", (0, 1), (-1, 8), colors.HexColor("#E3EDFF")),   # pieces used by the GUI
                ("ROWBACKGROUNDS", (0, 9), (-1, -1), [colors.white, colors.HexColor("#F7F9FA")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ]))
            title = Paragraph(f"<b>{cond.replace('_', ' ').title()}</b> &nbsp;<font size=7 color='#64748B'>"
                              f"{subj}_{cond}.txt</font>", styles["BodyText"])
            blocks.append([title, t])
        # three tables side by side, two rows of tables: one page per subject
        grid = [blocks[0:3], blocks[3:6]]
        g = Table(grid, colWidths=[width + 4 * mm] * 3)
        g.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        page_items.append(g)
        page_items.append(Paragraph("<font size=7 color='#64748B'>Blue rows (pieces 1-8) are the ones shown in the "
                               "8 rounds of a condition (round N = piece N).</font>", styles["BodyText"]))
        story.append(KeepInFrame(doc.width, doc.height, page_items, mode="shrink"))  # one page per subject
        if i < len(subjects) - 1:
            story.append(PageBreak())

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawRightString(page[0] - 10 * mm, 5 * mm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"Wrote {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subjects", type=int, default=25)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args()
    data = write_files(args.subjects, args.seed)
    if not args.no_pdf:
        write_pdf(data, os.path.join(LOG_DIR, f"Answer_Key_s01-s{args.subjects:02d}.pdf"))


if __name__ == "__main__":
    main()
