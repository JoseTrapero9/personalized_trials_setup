"""Runtime state shared between modules. Import the singleton and read/write attributes:
    from state import state
    state.current_condition = 'baseline'"""


class SessionState:
    def __init__(self):
        self.difficulty = "hard"
        self.subject_number = "1"
        self.current_condition = "training"
        self.training_active = False
        self.language = "en"          # "en" | "es" | "de" (radio + participant screens)
        self.training_sequence = []   # built per session in training mode
        self.controller = None        # the main window (set in main.py)


state = SessionState()
