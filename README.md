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

Folders that must sit next to `main.py`: `audios/`, `log_files/`, `workpieces/`,
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

## Logs

* LSL markers: `Radio_Problem_Start_<id>_..._Layout_..._Targets_...`, `Radio_Instruction_End_<id>`,
  `Radio_Press_Correct|Wrong|Timeout_...`, `Radio_Problem_Solved|Wrong|Timeout_<id>_RT_..._RTafterInstr_...`,
  `Radio_Problem_Held|Resumed_<id>`, `Radio_Checkpoint_Due`.
* `logs/sXX_<condition>_radio_<time>.csv`: one row per problem (steps, layout, presses, RTs, score).
