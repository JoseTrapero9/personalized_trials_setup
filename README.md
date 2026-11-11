# Dual-task paradigm: plant radio + battery assembly

## First-time setup (Windows, conda env `paradigm`, Python 3.12)

```powershell
conda activate paradigm
python -m pip install -r requirements.txt
python generate_radio_audio.py --list-voices    # check you have EN, ES (Mexico) and DE voices
python generate_radio_audio.py --lang all        # writes radio_audio/en|es|de (once, ~1-3 min)
python main.py
```

Missing a voice: Windows Settings > Time & language > Speech > Add voices
(Spanish (Mexico), German (Germany)), then re-run the generator.
After editing `radio_script.py`, re-run the generator; it only redoes changed clips.

Folders that must sit next to `main.py`: `audios/`, `log_files/` (see below), `workpieces/`,
`model/` (Vosk), `radio_audio/` (generated) and `robot_sequence.py`.

## The game

* The radio talks all the time (chatter). Suddenly an incident: it says which button(s) to press,
  by **color** ("the red button") or by **word** ("the button labeled red"), single or in order (2-3).
* 3 buttons on screen = keys **← ↑ →** (left / middle / right). Colors and words never match and
  keep changing; they freeze while a problem is active. No text of the instruction is ever shown.
* One wrong key or no answer within `RESPONSE_SECONDS` after the instruction = failed, points lost,
  negative radio reaction, game goes on.
* Checkpoint after `PROBLEMS_PER_CHECKPOINT` problems; problems during the battery task do not count.
* Saying DELIVER pauses the radio; an open problem is held (and its instruction replayed if it was
  cut off), so a pause can't be used to skip a problem.
* Each condition owns 40 instructions that no other condition uses (240 in total, identical
  6 single / 7 pair / 7 triple mix per 20). Fixed order per condition, same for every participant
  and language. Button positions are generated live, so a sentence never implies the keys.
  If someone needs more than 40, the condition reuses its own set (marker `Radio_Problem_Set_Exhausted_...`).

## Game modes (setup screen)

* **Normal**: as above.
* **Hard**: while no instruction is active, every button change is a *match round*: exactly one
  button's color matches its word. Press it before the next change for `IDLE_HIT_POINTS` (+30, half of
  a hard one-button instruction). Missing costs nothing; one try per change (wrong press uses it up).
  Radio instructions pay double and cost double. Checkpoints still count only radio instructions.
  A press within `LATE_PRESS_SECONDS` of a change counts for the previous round; presses in the first
  `PRESS_GRACE_SECONDS` of an instruction are ignored. Markers `Radio_Match_*`, CSV rows of type `match`.
  Separate leaderboards (`arcade_scores_<condition>_hard.json`).
* Hard mode banner: FIND THE MATCH! / WAIT FOR YOUR INSTRUCTION! / ANSWER NOW!. While the radio speaks
  an instruction the buttons spin (random faces) and the arrows are locked (`Radio_Press_Blocked_*`);
  the real buttons appear at ANSWER NOW (= `Radio_Instruction_End_*`). `ROULETTE_DURING_INSTRUCTION`
  in config.py also enables this for normal mode.

## Files

| file | what |
|---|---|
| `main.py` | entry point |
| `config.py` | all settings (game timing, points, audio) |
| `radio_script.py` | every spoken line in EN / ES / DE |
| `panel_logic.py` | problem pool, Stroop layouts |
| `generate_radio_audio.py` | offline TTS -> `radio_audio/` |
| `radio.py` | radio playback on the participant headphones |
| `game.py` | the radio button game (left panel) |
| `texts.py` | participant screen text in EN / ES / DE |
| `screens/` | setup (incl. language), tutorial, start, dual task, scoreboard |
| `sequences.py` | loads `log_files/sXX_<condition>.txt` |
| `questionnaires.py` | NASA-TLX + experience questionnaire: text (EN/ES/DE), saving, subject summary files |
| `generate_log_files.py` | makes `log_files/` + answer-key PDF |
| `live_evaluator.py` | camera PC: YOLO tray check, follows the GUI over LSL, sends verdicts |
| `evaluator_link.py` | GUI side: receives the camera verdicts |

## Battery sequences (`log_files/`)

* `log_files/sXX_<condition>.txt` (s01-s25): 17 pieces each, tab separated `piece sum instruction answer`.
  File names: `audio`, `audio_haptics`, `baseline`, `fast`, `haptics`, `slow`
  (GUI conditions `audio`, `audio_haptic`, `baseline`, `robot_fast`, `haptic`, `robot_slow`).
* The GUI loads the file of the chosen subject + condition (round N = piece N, first 8 pieces used) and
  sends the marker `Sequence_File_<name>`. Missing file -> fallback `s06_haptics.txt` (`Sequence_File_fallback`).
* `log_files/Answer_Key_s01-s25.pdf`: every subject and condition with the answers (one page per subject).
* `python generate_log_files.py [--subjects 30] [--seed 2026]` rebuilds all files + the PDF (seeded:
  the same seed gives the same files). Needs `reportlab` for the PDF.

## Camera evaluator on a second PC (`live_evaluator.py`)

Runs on the camera PC with the YOLO model (`live_test.py` settings). The window shows the camera
next to the answer table of the log file (like the PDF): every battery gets a check or a cross as soon
as the camera sees it. Marks are **green while the evaluation is active** and turn **black** once the
row is evaluated. The Result column shows OK / MISTAKE.

**Test it now (no GUI):**

```powershell
python live_evaluator.py --test                   # choose the log file in a window
python live_evaluator.py --test s03_audio         # or name it
python live_evaluator.py --test s03_audio --webcam 0   # normal webcam instead of the XIMEA
```

Row 1 starts right away. Say "deliver" (Vosk, same as the GUI) or press D: the row is evaluated and
the next one starts. R = redo the row, Q = quit. Log: `logs/evaluator_test_<file>_<time>.csv`.
Test mode plays feedback on the subject's audio output (Trekz; `--audio-out NAME` for another device,
`--no-sounds` to turn it off): a random `audios/positive_sound1-3.wav` for a correct row, `buzzer.wav` or
`incorrect_answer.wav` for a mistake. Every clip is cut to 1 s with a short fade-out (the files are not changed).
Live mode plays no sounds for now.

**Evaluation rules (test and live):**

* Only the station counts (the model's `Station` class, drawn as EVALUATION AREA): batteries are read
  only inside a tray whose centre is on the station; batteries dropped around it, trays elsewhere and
  hands away from the station are ignored. The station position is remembered while the tray covers it.
  Without a `Station` detection the whole image is used (shown as STATION NOT FOUND).
* Evaluated at the first of: the tray is off the station (0.5 s, no hand at the station, `--tray-gone`),
  "deliver", or the handover. Someone who says deliver after picking the tray up is judged on the tray
  as it was on the station.
* Correct only if all 3 slots match the log file; a slot not seen counts as wrong
  (fewer than 3 batteries in view = mistake).
* A reading counts when it is stable for `STABLE_FRAMES` frames with no hand at the station. The previous
  round's tray does not count until the station was cleared or the tray changed.

**Live, with the GUI:** both PCs on the same network; LSL finds the streams by itself, no IP setup.

```
GUI PC  --LSL "ParadigmMarkers"-->  camera PC   (subject, condition, round, deliver, handover ...)
GUI PC  <--LSL "BatteryEvaluator"--  camera PC  (Eval_Prediction_..., Eval_Verdict_Round_<r>_correct|incorrect_..._Trigger_...)
```

* Mirrors the GUI timers (retrieval, assembly 15/20/25 s, delivery window, overtime) from the markers.
* The table is the subject's log file (rows 1-8 = the 8 rounds). The expected answer is checked
  against the sum + instruction the GUI showed (on a mismatch it uses what the GUI showed).
* The GUI applies the verdict right away (`Assembly_Evaluation_Source_camera_Round_<r>`). While
  `USE_REMOTE_EVALUATOR = True` (config.py) the manual y / c keys are disabled.
* Writes `logs/evaluator_sXX_<condition>_<time>.csv` on the camera PC.

```powershell
python live_evaluator.py                  # camera + YOLO
python live_evaluator.py --no-camera      # test the link: prints the GUI phase/timer it follows
python live_evaluator.py --predict-only   # never send verdicts, only predict and log
python live_evaluator.py --subject 3 --condition audio   # started after the GUI setup screen
```

The camera PC needs this repo (for `log_files/`, `config.py`, `sequences.py`), `pylsl`, and the
`live_test.py` packages (ultralytics, torch, opencv, XIMEA API); for voice in test mode also `vosk`,
`sounddevice`, `PyQt5` and the `model/` folder. Allow Python through the Windows firewall on both PCs
(private network) or LSL cannot see the other PC.

## Questionnaires

* **NASA-TLX after every condition** (baseline, audio, haptic, audio_haptic; not after training,
  robot_fast or robot_slow): scoreboard -> NASA-TLX -> main menu. Six scales, 21 gradations, raw TLX
  (no pairwise weighting). Saved as `logs/questionnaires/sXX_<condition>_nasatlx.csv` (scores 0-100 plus
  `raw_tlx`); running the condition again overwrites the file.
* **`sus` in the condition menu** (once per subject, after all conditions): experience questionnaire with
  10 statements per condition on a 5-point agree scale (baseline: 6, the 4 feedback statements are left
  empty). Saves `sXX_<condition>_sus.csv` after each page, then builds the subject files
  `sXX_nasatlx_all_conditions.csv/.xlsx` and `sXX_sus_all_conditions.csv/.xlsx` (Excel needs `openpyxl`).
  If a condition has no NASA-TLX file, a warning lists the missing conditions: Continue or Go back.
* Answer with the mouse or the keys: UP / DOWN line, LEFT / RIGHT answer (1-5 also work for statements),
  ENTER continue. Every line must be answered. Language = the participant language of the setup screen.
* Text, statements and the list of conditions: `questionnaires.py`. Markers: `NasaTLX_Started|Saved_...`,
  `SUS_Started|Saved|Finished_...`.

## Logs

* LSL markers: `Radio_Problem_Start_<id>_..._Layout_..._Targets_...`, `Radio_Instruction_End_<id>`,
  `Radio_Press_Correct|Wrong|Timeout_...`, `Radio_Problem_Solved|Wrong|Timeout_<id>_RT_..._RTafterInstr_...`,
  `Radio_Problem_Held|Resumed_<id>`, `Radio_Checkpoint_Due`.
* `logs/sXX_<condition>_radio_<time>.csv`: one row per problem (steps, layout, presses, RTs, score).
