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
`radio_audio/` (generated) and `robot_sequence.py`. Delivery is always the **D** key (no speech recognition).

## Safety checks

* **Check before starting**: after *Start Selected Mode* (condition, training, pre-train, sus) a researcher window shows
  subject, condition and settings, files that would be **overwritten** (NASA-TLX, pre-train, questionnaire), the
  conditions already finished for this subject, and whether the participant headphones, the vest (bHaptics Player),
  the camera PC and LSL are ready. It refreshes twice a second. Red lines make *Go back* the default; *Start anyway*
  is still possible. Marker `Preflight_Start|Back_<kind>_<condition>_fail<n>_warn<n>`.
* **Quit** is **Ctrl+Q** (or Alt+F4), always with a confirmation. The single `q` key no longer quits.
* **Program errors** do not stop a session: they are written to `logs/errors.log` (with subject, condition and the
  traceback), sent as marker `Program_Error_<type>_<file>_<line>`, and the program keeps running (`safety.py`).
  The check window shows how many errors happened in this run.
* **Data and git**: `logs/` and Python caches are in `.gitignore`. Back up `logs/` separately (lab drive); it is
  not pushed to GitHub. Files committed earlier (`logs/questionnaires/s01_*`) stay tracked until you remove them
  with `git rm --cached` after copying them somewhere safe.

## The game

* The radio talks all the time (chatter). Suddenly an incident: it says which button(s) to press,
  by **color** ("the red button") or by **word** ("the button labeled red"), single or in order (2-3).
* 3 buttons on screen = keys **← ↓ →** (left / middle / right; the middle button is the DOWN arrow, it was
  the up arrow before). Tutorial slides and scoreboard also take ↓ to go on, so a 3-key pad is enough. Colors and words never match and
  keep changing; they freeze while a problem is active. No text of the instruction is ever shown.
* One wrong key or no answer within `RESPONSE_SECONDS` after the instruction = failed, points lost,
  negative radio reaction, game goes on.
* Checkpoint after `PROBLEMS_PER_CHECKPOINT` problems; problems during the battery task do not count.
* Wrong key combination (`ERROR_CUES`): `incorrect_answer.wav` in the participant's **Trekz** (mixed into the
  radio stream), not on the researcher speakers. All participant sounds (radio, cues, warm-up feedback, handover
  feedback) play in the Trekz; only the condition announcements and the SYSTEM FAILED alarm loop use the
  researcher / alarm speakers.
* DELIVER (D key) pauses the radio: the sentence it was saying freezes mid-word and continues from that
  exact point when the pause ends (nothing is restarted or repeated). An open problem is held with it
  (answer time frozen), so a pause can't be used to skip a problem. Markers `Radio_Audio_Paused_<clip>` /
  `Radio_Audio_Resumed_<clip>`; the radio CSV counts the `pauses` of each problem.
* Each condition owns 40 instructions that no other condition uses (240 in total, identical
  6 single / 7 pair / 7 triple mix per 20). Fixed order per condition, same for every participant
  and language. Button positions are generated live, so a sentence never implies the keys.
  If someone needs more than 40, the condition reuses its own set (marker `Radio_Problem_Set_Exhausted_...`).

## Game mode (always the former "hard" mode)

There is only one game mode now (the setup-screen choice and the normal mode were removed; logs still say
`game_mode = hard`):
* While no instruction is active, every button change is a *match round*: exactly one button's color matches
  its word. Press it before the next change for `IDLE_HIT_POINTS` (+30). Missing costs nothing; one try per
  change (wrong press uses it up). Radio instructions pay `POINTS_PER_STEP` x 2 per button and cost
  `FAIL_PENALTY` x 2. Checkpoints still count only radio instructions. A press within `LATE_PRESS_SECONDS` of
  a change counts for the previous round; presses in the first `PRESS_GRACE_SECONDS` of an instruction are
  ignored. Markers `Radio_Match_*`, CSV rows of type `match`.
* Banner: FIND THE MATCH! / WAIT FOR YOUR INSTRUCTION! / ANSWER NOW!. While the radio speaks an instruction the
  buttons spin (random faces) and the arrows are locked (`Radio_Press_Blocked_*`); the real buttons appear at
  ANSWER NOW (= `Radio_Instruction_End_*`).

## Score and leaderboard

* **General leaderboard** (`leaderboard.py`, `logs/leaderboard_general.json`): a participant's points are added
  up over all conditions. The score on screen starts at the points of the participant's other conditions and
  keeps growing; the scoreboard after a condition shows *this block* and the *total* and ranks everybody by
  total (own row marked `◄ YOU`). Running a condition again replaces its points (never counted twice).
  Initials are asked once per participant (first scoreboard, training included) and reused.
  Training keeps its own practice board (`logs/arcade_scores_training.json`) and does not count.
* **Fake leaderboard messages** (not in training): next to the score, every 25-50 s
  (`FAKE_RANK_INTERVAL_SECONDS`) a message says the participant *moved up to*, *was passed / now at* or
  *is holding* 1st-3rd place (`FAKE_RANK_PLACES`). Invented to keep them engaged; each is logged as
  `Leaderboard_Fake_Message_Place_<n>_<up|down|same>`. `FAKE_RANK_MESSAGES = False` turns them off.
* **Feedback at the handover** (F13 = point 1, F14 = point 2), all conditions and training:
  right point -> **ASSEMBLY CORRECT** (+100, `correct_answer.wav`) or **ASSEMBLY INCORRECT** (loud incorrect
  sound), from the camera verdict. A verdict that came before the button press waits for it; one that comes
  later is shown when it arrives (up to `HANDOVER_FEEDBACK_WAIT_SECONDS`). Training uses the camera's practice
  result (feedback only, no points). Wrong point -> **WRONG POINT: deliver at Point N** + short error sound;
  the handover is not accepted. Markers `Handover_Feedback_Round_<r>_<correct|incorrect>`,
  `Handover_Wrong_Point_Pressed_<p>_Expected_<q>_Round_<r>`. After the last round the screen stays 3 s so the
  feedback is seen.

## Robot (`robot_sequence.py`)

The robot program now follows the GUI instead of alternating left / right by itself: the GUI sends
`go 1` at the start of **every condition and every training block** (round 1 is always point 1), the point
of each handover, then `go <next point>` (or `home` after the last round). Before, the robot program ran one
fixed left/right loop for the whole program run: after a 5-round training block the next block started on
the wrong side, after an interrupted condition the sides were swapped, and after 20 handovers (in the 3rd
condition) the loop ended and the robot stopped. Commands that arrive while the robot moves wait until the
move sequence is finished; switching between the two points always goes through home. Markers
`Robot_Command_<command>` (`_NotRunning` if the robot program is not running).

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
| `screens/` | setup (incl. language), tutorial + cue slides, start, dual task, scoreboard, questionnaires, pre-train |
| `feedback_cues.py` | the feedback cues (sound / vest), used by the battery cues, the training slides and the pre-train |
| `sequences.py` | loads `log_files/sXX_<condition>.txt` |
| `questionnaires.py` | NASA-TLX + experience questionnaire: text (EN/ES/DE), saving, subject summary files |
| `generate_log_files.py` | makes `log_files/` + answer-key PDF |
| `live_evaluator.py` | camera PC: YOLO tray check, follows the GUI over LSL, sends verdicts |
| `evaluator_link.py` | GUI side: receives the camera verdicts |
| `ximea_recorder.py` | third PC: records the MQ013 camera + face webcam, LSL-synchronised |
| `video_writer.py` | real-time video files encoded in a background process (recorder + evaluator) |

## Battery sequences (`log_files/`)

* `log_files/sXX_<condition>.txt` (s01-s25): 17 pieces each, tab separated `piece sum instruction answer`.
  File names: `audio`, `audio_haptics`, `baseline`, `haptics`
  (GUI conditions `audio`, `audio_haptic`, `baseline`, `haptic`). The robot fast / slow conditions were removed;
  the generator still draws their sequences and throws them away, so all other files stay exactly the same.
* The GUI loads the file of the chosen subject + condition (round N = piece N, first 8 pieces used) and
  sends the marker `Sequence_File_<name>`. Missing file -> fallback `s06_haptics.txt` (`Sequence_File_fallback`).
* `log_files/Answer_Key_s01-s25.pdf`: every subject and condition with the answers (one page per subject).
* `log_files/training_<condition>.txt`: the training blocks (see Pre-train and training).
* `python generate_log_files.py [--subjects 30] [--seed 2026]` rebuilds all files + the PDF (seeded:
  the same seed gives the same files). Needs `reportlab` for the PDF.

## Camera evaluator on a second PC (`live_evaluator.py`)

Step-by-step guide for running the GUI and the model together: `Model_GUI_Connection_Guide.pdf`.

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

Row 1 starts right away. Press D (deliver): the row is evaluated and
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
* As soon as **all 3 slots are correct** the round is finished: the cue of the last battery is sent first, then the
  verdict (trigger `all_correct`), and the round is locked; a hand covering a battery or a misread afterwards
  cannot change it (`FINISH_WHEN_ALL_CORRECT`). A tray with a wrong battery stays open so it can still be fixed.
* Otherwise the round is evaluated when the tray leaves the station: the tray is seen **off** the station (carried away)
  for 0.4 s (`TRAY_MOVED_SECONDS`), or no tray is seen at all, with no hand at the station, for 1.5 s
  (`--tray-gone`, `TRAY_GONE_SECONDS`). An arm passing over the tray hides it for less than that, so it no longer
  ends the round. Not when the third battery is placed, not when the clock runs out and not at "deliver";
  batteries can still be changed until the tray is taken away. Safety net in live mode: if the camera never saw
  the tray leave, the handover ends the round. In test mode "deliver" / D still closes an open row.
* The verdict uses the battery each slot had at its latest per-battery cue (these stay up to date while a hand is
  at the station), and the last whole-tray reading only for slots without a cue.
* Correct only if all 3 slots match the log file; a slot not seen counts as wrong
  (fewer than 3 batteries in view = mistake).
* A reading counts when it is stable for `STABLE_FRAMES` frames with no hand at the station. The previous
  round's tray does not count until the station was cleared or the tray changed.

**Fast loop and fixed areas:** the model runs in its own loop, separate from the window (drawn at 12 fps), and
only on a **fixed** area around the station (yellow MODEL AREA box), at the same battery size as in training.
* At the first start the station is measured for 2 s (median of all detections; keep it visible and empty, the
  window says SETTING THE EVALUATION AREA). Then the MODEL AREA and the EVALUATION AREA (station) are locked for
  the whole session: something covering the station no longer shrinks or moves them.
* They are saved in `evaluator_area.json` on the camera PC (not in git) and reused at the next start.
* Keys in the evaluator window: **A** = draw the model area, **E** = draw the evaluation area (mouse, ENTER),
  **C** = measure both again (after moving the camera or the station). `--recalibrate` measures again at start.
* Default model area = station + 10 % left / right / bottom and 40 % on top (the tray stands above the station),
  `ROI_MARGINS`. `--roi-scale` changes the detail, `--no-roi` runs the model on the full frame (areas stay fixed). `--exposure` (microseconds) and `--fps`
override the camera settings of `live_test.py`. The window footer shows the model rate and time per frame.

**Per-battery cues:** a battery in a slot fires its cue on the first frame when the model is at least
`CUE_FAST_CONFIDENCE` (0.75) sure, otherwise after `CUE_STABLE_FRAMES` frames in a row (default 2, `--cue-frames`).
The evaluator sends `Eval_Battery_Round_<r>_Slot_<k>_correct|incorrect_..._CamMs_<ms>`.
A hand at the station does not block this. A battery that is taken out and put in again (same colour or another)
gets a new cue every time; "taken out" = slot empty for 0.15 s with no hand at the station, or 0.4 s while a hand
is there (`SLOT_EMPTY_SECONDS`, `RECUE_EMPTY_SECONDS`). The GUI answers during the assembly with the cue of the
condition; sounds are mixed into the radio stream that is already open, so they start within one audio block
(marker `Battery_Cue_Round_<r>_Slot_<k>_<result>_<channels>_CamMs_<ms>_LinkMs_<ms>`: camera frame -> message sent,
and sent -> received on the GUI PC):

| condition | correct battery | wrong battery |
|---|---|---|
| `audio` | `correct_cue_audio` (positive_sound2.wav) | `incorrect_cue_audio` (the mistake sound) |
| `haptic` | vest `positive_3` (warm swell, back) | vest `negative_2` (sharp staccato, front) |
| `audio_haptic` | both | both |
| baseline | nothing (marker only) | nothing (marker only) |

In training every block uses the cues of its condition (see Training).

Sounds, their 1 s limit (`CUE_AUDIO_MAX_SECONDS`), vest patterns and positions are set in `config.py`; to change
a sound, change the file name there (any length, it is cut to 1 s when played). The vest cues go through the
bHaptics Player websocket like the pre-study scripts (`websocket-client`). The whole-tray reading for the
final verdict still waits until no hand is at the station.

**Camera drop-outs:** the XIMEA camera runs in its own process. If no frame arrives for 3 s (error 10, a hung
driver call, unplugged cable) that process is killed and started again, which reopens the camera; it keeps
retrying until frames are back. The window, the model and the GUI link keep running meanwhile, a red banner on
the camera image says what is happening, and the round state is kept.

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
python live_evaluator.py --record gui     # record each condition itself (no recorder PC)
python live_evaluator.py --record off --record-fps 25   # no video / other video frame rate
```

**Video of the evaluator camera (for the VLM).** The evaluator records its camera to
`recordings/sXX_<condition>_mc050_<date_time>.mp4` (30 fps, `--record-fps` to change). By default
(`--record sync`) it records every GUI condition and uses the same `<date_time>` as `ximea_recorder.py` on the
third PC, so the three videos of a condition (mc050, mq013, webcam) belong together; if the third PC does not
answer within 1.5 s it records alone. If the LSL link to the GUI broke just when a condition started (console:
`Stream transmission broke off ... re-connecting`), the video starts late on the next marker of that condition
instead of not at all (same in `ximea_recorder.py`). `--record gui` ignores the third PC, `--record manual` / **V** records by hand (V works in every mode), `--record off` = no video.
Every camera frame goes into the video, also the ones the model skips; the window shows `REC <file>` while
recording. Markers on the evaluator stream: `Eval_Recording_Start_<file>` (time of the first frame),
`Eval_Recording_Stop_<file>_Frames_<n>_Seconds_<s>`.
To keep the model fast, the video is encoded by a separate background process at lower priority
(`video_writer.py`): the camera thread only copies each frame once into shared memory (about 1 ms) and never
waits. If the encoder falls behind, the previous frame is repeated in the file instead of slowing the model.

The camera PC needs this repo (for `log_files/`, `config.py`, `sequences.py`), `pylsl`, and the
`live_test.py` packages (ultralytics, torch, opencv, XIMEA API). Allow Python through the Windows firewall on both PCs
(private network) or LSL cannot see the other PC.

## Pre-train and training

Order for a participant: **pre-train** -> **training** -> the four conditions -> **sus**.

* **pre-train** (condition menu): learn the feedback cues, adapted from `pre_study/validating_cues.py`.
  A cue is played; the participant presses **←** if it means *right* and **→** if it means *wrong*
  (SPACE plays it again). Three blocks of 40 s: sound, sound + vest, vest (`PRETRAIN_BLOCKS`,
  `PRETRAIN_BLOCK_SECONDS`). The cues are exactly the ones of the paradigm: vest `positive_3` / `negative_2`
  and the audio cue mode chosen on the setup screen (voice or tone); nothing to choose as in the pre-study.
  Saves `logs/pretrain/sXX_pretrain.csv`, one row per cue (block, cue, sound file, vest pattern and side,
  answer, right or wrong, reaction time, replays). A repeated pre-train overwrites the file; ESC stops early
  and saves what was answered. Markers `Pretrain_*`.
* **training menu**: when training is started, a window asks where to start: tutorial slides, radio warm-up,
  battery warm-up or block 1-4 (e.g. to continue after a problem), and whether to run only that part.
  Default = everything in order. Marker `Training_Plan_<parts>`.
* **Warm-ups** (interactive, one task at a time, `screens/warmup_screen.py`):
  *Radio*: the radio alone, `WARMUP_RADIO_PROBLEMS` = 6 instructions; the first 3 are also shown as text while
  spoken and have 10 s to answer, then listen only at the real pace. After each one the coach panel shows what
  the radio said and which keys were right (and why: color or word). Match rounds in between.
  *Battery*: `WARMUP_BATTERY_PUZZLES` = 4 sums on screen (keys 1-4 = Blue / Red / Yellow / Green into the next
  slot, Backspace = undo, live sum), a hint after a mistake (wrong batteries or wrong order) and the answer after
  the second; then delivery practice: D, then the button at point 1, D, then point 2 (wrong button = hint).
  Markers `Warmup_Start_<radio|battery>`, `Warmup_Radio_Problem_*`, `Warmup_Battery_Puzzle_*`,
  `Warmup_Delivery_*`, `Warmup_End_*` (the camera PCs do not record warm-ups).
* **training blocks**: task slides (radio task, checkpoints, battery sum, delivering with D, how the practice works),
  then four blocks of `TRAINING_ROUNDS` = 5 rounds, always in the order baseline -> audio -> audio_haptic -> haptic
  (`TRAINING_CONDITIONS`). Before each block a slide explains its cues; keys **1** / **2** play a sample right /
  wrong cue. Each block uses the cues of its condition and its own battery tasks, and starts further into the
  training radio instructions (before, every block replayed the same first ones). Scoreboard after the last block.
* **Training log files**: `log_files/training_baseline.txt`, `training_audio.txt`, `training_audio_haptics.txt`,
  `training_haptics.txt` (5 pieces each, same for every subject, also on the first page of the answer-key PDF).
  The GUI and the camera PC load the same file, so the camera PC knows the answers and sends the per-battery
  cues. Training is **not evaluated**: the camera PC sends no verdict (`Eval_Result_...` instead of
  `Eval_Verdict_...`), the GUI ignores any verdict in training, and nothing is written to the CSV logs.
  If a file is missing, the GUI falls back to generated tasks (the camera PC then reads the answers from the
  GUI markers). `generate_log_files.py` rebuilds them without changing the subject files.
  Markers `TRAIN_Training_Block_Start|Complete_<i>_<condition>`, `TRAIN_Cue_Slide_Shown_...`, `TRAIN_Cue_Demo_...`.
* Delivery is always the **D** key; the Vosk speech recognition and its `model/` folder were removed.

## Video recording on a third PC (`ximea_recorder.py`)

Records the second XIMEA camera (**MQ013**) with the settings of `old_code/3CAM_Stream`
(exposure 25000 us, gain 8, gamma 0.47, white balance 1.00 / 2.05, no binning) and the **face webcam**, both at
30 fps. Video only, no model. The window shows both cameras live (red dot = recording).

```powershell
python ximea_recorder.py              # records each condition / training block automatically (follows the GUI)
python ximea_recorder.py --manual     # only R starts / stops
python ximea_recorder.py --fps 25     # other frame rate (both cameras and videos)
python ximea_recorder.py --webcam 1 --webcam-size 1920x1080   # which webcam / its resolution (default 0, 1280x720)
python ximea_recorder.py --no-webcam  # MQ013 only
python ximea_recorder.py --out D:\videos
```

* Videos: `recordings/sXX_<condition>_mq013_<date_time>.mp4` and `..._webcam_<date_time>.mp4`. Both start and stop
  together, and `live_evaluator.py` on the camera PC starts / stops its `..._mc050_<date_time>.mp4` at the same
  moment (same `<date_time>`). In a test the three first frames were within 20 ms of each other.
* LSL: one marker stream `ximeasync_mq013`: `Recording_Session_Start_<label>_<date_time>` /
  `Recording_Session_Stop_...` (the evaluator follows these), and per video `Recording_Start_<file>` (stamped with
  the capture time of its first frame) and `Recording_Stop_<file>_Frames_<n>_Seconds_<s>` (end of the last frame).
  Add it in LabRecorder: LSL corrects the clock offset between the PCs. Every video keeps real time (a skipped
  frame is filled with the previous one, an early one is left out), so frame N was captured at start + N / fps.
  `Camera_Lost` / `Camera_Restored`, `Webcam_Lost` / `Webcam_Restored` only appear if a camera drops out.
* The XIMEA camera runs in its own process and is restarted after 3 s without frames; the webcam is reopened if it
  stops. A recording continues in the same file, still in real time. Each video is encoded by its own background
  process, so encoding never delays the capture.
* Start `live_evaluator.py` before the first recording starts: it only hears the start markers sent while it runs.
* The third PC needs this repo, the XIMEA API (`C:\XIMEA\API\Python\v3`), `pylsl`, `opencv-python`, `numpy`,
  the same network as the GUI PC and Python allowed through the firewall.
* `old_code/cam_probe.py` has other MQ013 values (exposure 31000, wb_kb 1.90); change `CAMERA_PRESETS` at the top
  of `ximea_recorder.py` if those are the right ones.

## Questionnaires

* **NASA-TLX after every condition** (baseline, audio, haptic, audio_haptic; not after training):
  scoreboard -> NASA-TLX -> main menu. Six scales, 21 gradations, raw TLX
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
