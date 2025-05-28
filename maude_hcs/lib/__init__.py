from pathlib import Path
import os

class GLOBALS:
    MODEL_TYPES = ['nondet', 'prob']
    MODULES = ['dns']
    TOPLEVELDIR = Path(os.path.dirname(__file__)).parent.parent