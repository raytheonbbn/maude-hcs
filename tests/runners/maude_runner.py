import maude
import logging
import contextlib
import os
import sys

from pathlib import Path
from typing import TYPE_CHECKING
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

# prevents circular import
if TYPE_CHECKING:
    from ..utils.context import TestConfig, RunConfig

def maude_runner(test_cfg: "TestConfig", build_dir: Path, run_cfg: "RunConfig", logger: logging.Logger) -> str:
    maude.init()
    maude.load(str(build_dir / 'test-env.maude'))
    m: maude.Module = maude.getModule("TEST-ENV")

    # This is just a maude term to reduce straightforwardly
    if isinstance(test_cfg.arg, str):
        term = m.parseTerm(test_cfg.arg)
        term.rewrite()
        result = str(term)

    elif isinstance(test_cfg.arg, dict):
        assert set(test_cfg.arg.keys()) == set(["initial", "term"]), 'maude test arg must be either a string term or a dict with "initial" and "term" keys'
        initial = m.parseTerm(test_cfg.arg["initial"])
        term = m.parseTerm(test_cfg.arg["term"])
        variable = m.parseTerm("FINAL:Config")

        initial.rewrite()

        subbed = maude.Substitution({variable: initial}).instantiate(term)
        subbed.reduce()
        result = str(subbed)

    else:
        raise ValueError("argument in test config must be either str or dict")

    return result