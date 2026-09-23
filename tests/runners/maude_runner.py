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
    t = m.parseTerm(test_cfg.arg)
    t.rewrite()
    return str(t)