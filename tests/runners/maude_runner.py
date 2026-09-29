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
    if not maude.load(str(build_dir / 'test-env.maude')):
        raise RuntimeError("Unable to load test-env.maude")
    m: maude.Module = maude.getModule("TEST-ENV")
    if m is None:
        raise RuntimeError("TEST-ENV module is unavailable")
    if isinstance(test_cfg.arg, dict):
        if set(test_cfg.arg) != {"initial", "predicate"}:
            raise ValueError("Structured Maude arg requires initial and predicate")
        initial = m.parseTerm(test_cfg.arg["initial"])
        predicate = m.parseTerm(test_cfg.arg["predicate"])
        if initial is None or predicate is None:
            raise ValueError(f"Unable to parse initial term/predicate: {test_cfg.arg}")
        # Equality can simplify to false before nested rewrite rules execute.
        # Finish the configuration first, then bind it into the observer term.
        initial.rewrite()
        variable = m.parseTerm("FINAL:Config")
        t = maude.Substitution({variable: initial}).instantiate(predicate)
        t.reduce()
    elif isinstance(test_cfg.arg, str):
        # Legacy arbitrary-term regressions still use the direct rewrite API.
        t = m.parseTerm(test_cfg.arg)
        if t is None:
            raise ValueError(f"Unable to parse test term: {test_cfg.arg}")
        t.rewrite()
    else:
        raise ValueError("Maude arg must be a term string or initial/predicate object")
    result = str(t)
    # Boolean assertions must not accidentally snapshot an unreduced term.
    if test_cfg.expected in ("true", "false") and result not in ("true", "false"):
        raise RuntimeError(f"Predicate did not reduce to Bool: {result}")
    return result