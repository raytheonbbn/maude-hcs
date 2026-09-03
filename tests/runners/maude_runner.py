import maude
import pathlib
import logging
import json

from ..utils.setups import Setup

logger = logging.getLogger(__name__)

def maude_runner(setup: Setup, **kwargs):
    filename: str = kwargs["file"]
    path = (setup.directory / filename).resolve()
    maude.load(str(path))
    m: maude.Module = maude.getModule("HCS_TEST")
    t = m.parseTerm("initConfig")
    t.rewrite()
    d = {"term": str(t)}
    return json.dumps(d, indent=4)

def generate_maude():
    pass

def run_maude():
    pass