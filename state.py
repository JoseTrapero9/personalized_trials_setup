"""Runtime state shared between modules. Import the singleton and read/write attributes:
    from state import state
    state.current_condition = 'baseline'"""


class SessionState:
    def __init__(self):
        self.difficulty = "hard"
        self.subject_number = "1"
        self.current_condition = "training"
        self.training_active = False
        self.game_mode = "normal"     # "normal" | "hard"
        self.audio_cue_mode = "voice"  # "voice" ("input correct"/"input incorrect") | "tone"
        self.language = "en"          # "en" | "es" | "de" (radio + participant screens)
        self.training_sequence = []   # battery tasks of the current training block
        self.training_sequence_file = ""      # log_files/training_<condition>.txt of the block ("" = generated)
        self.training_block = 0       # index in config.TRAINING_CONDITIONS
        self.training_condition = "baseline"   # condition of the current training block (its cues are used)
        self.controller = None        # the main window (set in main.py)


state = SessionState()
